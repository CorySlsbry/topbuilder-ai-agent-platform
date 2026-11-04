"""Golden-set evaluation gate for candidate learned rules (Phase C/D).

A candidate rule may only become active if it passes, in order:
  1) rule_safety_check       — deterministic red-flag guardrail (always runs, offline)
  2) the ADR-0003 invariant  — injecting the rule must not drop any authoritative figure a golden
                               case requires (the figures that survived WITHOUT the rule must survive WITH it)
  3) the golden set          — every golden case's must_include kept / must_avoid absent

Offline (DISABLE_LLM) the narration stand-in is the situation text itself, so the gate leans on the
safety check + structural golden checks; with the LLM on, it is a real narration-regression test.
Every evaluation is written to `eval_runs` (this is an audited product).
"""
from __future__ import annotations

import json

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.learning import governance
from app.repositories import governance as gov_repo


async def _render(agent: str, situation_text: str, settings: Settings, *, rule: str) -> str:
    """Narrate a golden situation, optionally applying a candidate rule. Numbers must be preserved."""
    if settings.disable_llm or not settings.anthropic_api_key:
        # Deterministic offline stand-in: the situation IS the narrative (figures preserved by
        # construction), so the safety check + structural golden checks are what gate offline.
        return situation_text
    try:
        from app.assistant.llm_client import build_llm_client

        client = build_llm_client(settings)
        guidance = f"\nApply this style rule where relevant: {rule}" if rule else ""
        resp = await client.messages.create(
            model=settings.workforce_reasoning_model,
            max_tokens=400,
            system=[{"type": "text", "text": (
                "You narrate a financial/ops situation for a contractor. Quote EVERY figure exactly as "
                "given — never alter, round, or omit a number." + guidance
            )}],
            messages=[{"role": "user", "content": f"Situation:\n{situation_text}\nWrite a 2-sentence summary."}],
        )
        return "\n".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip() or situation_text
    except Exception:
        return situation_text


async def evaluate_candidate(
    session: AsyncSession, *, preference: dict, settings: Settings | None = None
) -> dict:
    """Run the full gate on one candidate preference and persist an eval_run. Returns the verdict."""
    settings = settings or get_settings()
    agent = preference["agent"]
    rule = preference.get("preference_text") or ""

    safety_ok, reasons = governance.rule_safety_check(rule)
    golden = await gov_repo.list_golden(session, agent=agent)
    total = len(golden)
    passed = 0
    invariant_ok = True
    cases_detail: list[dict] = []
    # SEC-3: the gate can only TEST a rule's effect when a real model narrates it. Offline (no LLM)
    # the golden narration is the situation verbatim, so an empty rule and a poisoned rule score
    # identically — the eval is not meaningful. A non-empty rule evaluated offline is therefore NOT
    # auto-passable; it must wait for a human approval (the real backstop) or an online eval.
    online = not (settings.disable_llm or not settings.anthropic_api_key)
    evaluatable = online or not (rule or "").strip()

    if safety_ok:
        for gc in golden:
            inc = list(gc.get("must_include") or [])
            avoid = list(gc.get("must_avoid") or [])
            with_rule = await _render(agent, gc["situation_text"], settings, rule=rule)
            base = await _render(agent, gc["situation_text"], settings, rule="")
            ok, fails = governance.golden_match(with_rule, inc, avoid)
            # ADR-0003 invariant: figures present WITHOUT the rule must remain present WITH it.
            base_ok, _ = governance.golden_match(base, inc, [])
            with_ok, _ = governance.golden_match(with_rule, inc, [])
            inv = (not base_ok) or with_ok
            invariant_ok = invariant_ok and inv
            passed += 1 if ok else 0
            cases_detail.append({"id": str(gc["id"]), "ok": ok, "invariant": inv, "fails": fails})

    score = governance.eval_score(passed, total)
    verdict = governance.eval_verdict(
        safety_ok=safety_ok, invariant_ok=invariant_ok, score=score, evaluatable=evaluatable
    )
    detail = {
        "safety_ok": safety_ok, "safety_reasons": reasons, "cases": cases_detail,
        "evaluatable": evaluatable, "online": online,
    }

    await gov_repo.insert_eval_run(
        session, preference_id=preference.get("id"), agent=agent, golden_total=total,
        golden_passed=passed, score=score, invariant_ok=invariant_ok, verdict=verdict, detail=detail,
    )
    if preference.get("id") is not None:
        await gov_repo.record_eval(session, preference_id=preference["id"], score=score, total=total, passed=passed)

    return {
        "verdict": verdict, "score": score, "safety_ok": safety_ok,
        "invariant_ok": invariant_ok, "golden_total": total, "golden_passed": passed,
        "reasons": reasons, "detail": json.loads(json.dumps(detail)),
    }
