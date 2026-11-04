"""Nightly consolidation for the self-learning layer (Phase C).

reflect (mine resolved cases) → propose candidate rules from loss clusters → run every candidate
through the eval gate → optionally auto-approve (canaried) if the tenant opts in → snapshot drift →
bandit-tune the governance thresholds. Pure scoring lives in governance.py; this is orchestration,
best-effort, and ISOLATED-session-safe (never raises into a request).

ADR 0003/0008: it only ever mints/evaluates narration RULES and tunes THRESHOLDS — never a figure.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.learning import eval_harness, governance
from app.learning import service as learning_service
from app.repositories import governance as gov_repo
from app.repositories import memory

WINDOW_CASES = 200


async def _propose_from_losses(agent: str, losses: list[dict], settings: Settings) -> list[str]:
    """Distill 'avoid' rules from clustered losses. LLM when available; conservative/no-op offline."""
    if not losses or settings.disable_llm or not settings.anthropic_api_key:
        return []
    try:
        from app.assistant.llm_client import build_llm_client

        sample = "\n".join(f"- {l.get('recommendation_summary','')[:160]}" for l in losses[:12])
        client = build_llm_client(settings)
        resp = await client.messages.create(
            model=settings.workforce_reasoning_model,
            max_tokens=300,
            system=[{"type": "text", "text": (
                "You improve how an advisory agent PHRASES recommendations. Given summaries a human "
                "rejected or undid, propose at most 2 short, general style rules to avoid repeating the "
                "mistake. Never mention specific numbers. One rule per line, no numbering."
            )}],
            messages=[{"role": "user", "content": f"Rejected/undone summaries for the {agent} agent:\n{sample}"}],
        )
        text_out = "\n".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        return [ln.strip("-• ").strip() for ln in text_out.splitlines() if len(ln.strip("-• ").strip()) >= 8][:2]
    except Exception:
        return []


async def consolidate(session: AsyncSession, *, agent: str, settings: Settings | None = None) -> dict:
    """Run one agent's consolidation pass. Returns a report (also persists eval_runs + drift)."""
    settings = settings or get_settings()
    report: dict = {"agent": agent, "proposed": [], "evaluated": [], "auto_approved": 0, "drift": None}
    try:
        cases = await memory.recent_resolved_cases(session, agent=agent, limit=WINDOW_CASES)
        total = len(cases)
        edits = sum(1 for c in cases if (c.get("outcome") == "edited"))
        rejects = sum(1 for c in cases if c.get("outcome") in ("rejected", "undone"))
        effs = [c["effectiveness"] for c in cases if c.get("effectiveness") is not None]
        avg_eff = round(sum(effs) / len(effs), 6) if effs else None
        edit_rate = round(edits / total, 6) if total else 0.0
        reject_rate = round(rejects / total, 6) if total else 0.0

        # 1) propose new candidate rules from loss clusters, then eval-gate every fresh candidate
        losses = [c for c in cases if (c.get("effectiveness") or 1.0) <= 0.0]
        for rule_text in await _propose_from_losses(agent, losses, settings):
            emb = await learning_service._embed(rule_text, settings)
            pref = await memory.upsert_preference(
                session, agent=agent, task_type=None, preference_text=rule_text,
                embedding=emb, proposed_by="nightly",
            )
            if pref:
                report["proposed"].append(rule_text[:120])

        # 2) run the eval gate over all current candidates. SEC-3: auto-approve removes the human
        # backstop, so it requires a DEPLOY-level opt-in (settings.learning_auto_approve_enabled) —
        # a tenant-settable param can NO LONGER enable it. Default: human approval is mandatory.
        tenant_auto = await gov_repo.get_param(session, name="auto_approve_on_eval", agent=agent, default=0.0)
        auto_allowed = settings.learning_auto_approve_enabled and tenant_auto >= 1.0
        canary_pct = int(await gov_repo.get_param(session, name="canary_pct", agent=agent, default=20.0))
        for cand in await gov_repo.list_preferences(session, agent=agent, status="candidate"):
            ev = await eval_harness.evaluate_candidate(session, preference=cand, settings=settings)
            report["evaluated"].append({"id": str(cand["id"]), "verdict": ev["verdict"], "score": ev["score"]})
            if ev["verdict"] == "pass" and auto_allowed:
                approved = await gov_repo.approve_preference(
                    session, preference_id=cand["id"], reviewed_by=None, rollout_pct=canary_pct
                )
                if approved:
                    report["auto_approved"] += 1
                    await memory.insert_event(
                        session, agent=agent, operation="pref_auto_approve",
                        target_table="agent_preferences", target_id=cand["id"],
                        rationale=f"eval pass score={ev['score']} canary={canary_pct}%",
                    )

        # 3) drift snapshot
        flagged = governance.drift_flag(
            edit_rate=edit_rate, reject_rate=reject_rate, avg_effectiveness=(avg_eff if avg_eff is not None else 1.0)
        )
        drift = await gov_repo.insert_drift(
            session, agent=agent, window_days=30, sample_size=total, edit_rate=edit_rate,
            reject_rate=reject_rate, avg_effectiveness=avg_eff, flagged=flagged,
        )
        report["drift"] = {"sample": total, "edit_rate": edit_rate, "reject_rate": reject_rate,
                           "avg_effectiveness": avg_eff, "flagged": flagged}

        # 4) bandit-tune the edit-distillation threshold: do well -> be choosier; do poorly -> learn more
        if total >= 5 and avg_eff is not None:
            reward = max(-1.0, min(1.0, avg_eff * 2 - 1))
            current = await gov_repo.get_param(session, name="edit_threshold", agent=agent, default=0.25)
            tuned = governance.bandit_update(current, reward=reward, lo=0.1, hi=0.6)
            await gov_repo.set_param(session, name="edit_threshold", value=tuned, agent=agent)
            report["edit_threshold"] = tuned
    except Exception as exc:  # best-effort — a consolidation hiccup must never break anything
        report["error"] = str(exc)[:200]
    return report
