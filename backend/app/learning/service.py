"""Orchestration of the self-learning loop. Composes pure scoring + memory persistence + embeddings.

ADR-0003 boundary: this layer only writes/reads cases, preferences, and narration lessons — it never
computes or mutates a deterministic figure. Every entry point is best-effort: a learning failure must
NEVER break a recommendation run or a feedback submission (wrapped + swallowed).

Online path only (this module): on feedback we label the case and quorum-gate a preference upsert.
Autonomous *rule creation* (nightly reflect→curate→eval→approval-queue) is Phase C — not here.
"""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.learning import governance, scoring
from app.rag.embeddings import get_embedding_provider
from app.repositories import memory

# rating string -> stored case outcome
_OUTCOME = {
    "up": "accepted", "approve": "accepted", "approved": "accepted",
    "down": "rejected", "reject": "rejected", "rejected": "rejected",
    "edit": "edited", "edited": "edited",
    "undo": "undone", "undone": "undone",
}
_EDIT_PREFERENCE_THRESHOLD = 0.25  # only a substantial edit becomes a candidate preference


async def _embed(value: str, settings: Settings) -> list[float] | None:
    try:
        provider = get_embedding_provider(settings)
        vecs = await provider.embed([value])
        return vecs[0] if vecs else None
    except Exception:
        return None


async def record_case(
    session: AsyncSession,
    *,
    agent: str,
    problem_text: str,
    recommendation_summary: str,
    run_id: uuid.UUID | None = None,
    target_ref: str | None = None,
    task_type: str = "run",
    recommendation_kind: str = "",
    problem_features: dict | None = None,
    model_version: str | None = None,
    settings: Settings | None = None,
) -> uuid.UUID | None:
    """Write a new case at decision time (outcome 'pending' until feedback labels it)."""
    settings = settings or get_settings()
    try:
        embedding = await _embed(problem_text, settings)
        case_id = uuid.uuid4()
        await memory.insert_case(
            session, case_id=case_id, agent=agent, task_type=task_type, run_id=run_id,
            target_ref=target_ref, problem_text=problem_text, problem_features=problem_features or {},
            embedding=embedding, recommendation_kind=recommendation_kind,
            recommendation_summary=recommendation_summary, model_version=model_version,
        )
        await memory.insert_event(
            session, agent=agent, operation="record_case",
            target_table="agent_cases", target_id=case_id,
        )
        return case_id
    except Exception:
        return None


async def on_feedback(
    session: AsyncSession,
    *,
    agent: str,
    run_id: uuid.UUID | None,
    rating: str,
    target_ref: str | None = None,
    correction: str | None = None,
    created_by: str | None = None,
    settings: Settings | None = None,
) -> None:
    """Label the run's case from approve/edit/reject/undo and distill a substantial edit into a
    (quorum-gated) preference. Best-effort — swallows errors so feedback submission never fails."""
    settings = settings or get_settings()
    if run_id is None:
        return
    try:
        case = await memory.get_case_by_run(session, run_id=run_id, target_ref=target_ref)
        edit_distance = None
        if (rating or "").lower() in ("edit", "edited") and correction and case:
            edit_distance = scoring.edit_cost(case.get("recommendation_summary") or "", correction)
        eff = scoring.effectiveness(rating, edit_distance=edit_distance)
        outcome = _OUTCOME.get((rating or "").lower(), "pending")
        if case is not None:
            await memory.label_case(
                session, case_id=case["id"], outcome=outcome, effectiveness=eff, edit_cost=edit_distance
            )
            await memory.insert_event(
                session, agent=agent, operation="label", target_table="agent_cases",
                target_id=case["id"], rationale=f"{outcome} eff={eff}",
            )
        # CIPHER: a substantial human edit becomes a candidate preference (only ACTIVE after the eval
        # gate + approval). The "substantial" bar is the bandit-tuned `edit_threshold` knob (Phase C),
        # falling back to the default if governance hasn't tuned it yet.
        threshold = _EDIT_PREFERENCE_THRESHOLD
        try:
            from app.repositories import governance as gov_repo

            threshold = await gov_repo.get_param(
                session, name="edit_threshold", agent=agent, default=_EDIT_PREFERENCE_THRESHOLD
            )
        except Exception:
            threshold = _EDIT_PREFERENCE_THRESHOLD
        if correction and edit_distance is not None and edit_distance > threshold:
            emb = await _embed(correction, settings)
            pref = await memory.upsert_preference(
                session, agent=agent, task_type=(case or {}).get("task_type"),
                preference_text=correction.strip()[:600], embedding=emb,
                proposed_by=created_by or "edit",  # SEC-3: distinct-author quorum
            )
            if pref is not None:
                op = "pref_activate" if pref.get("status") == "active" else "pref_upsert"
                await memory.insert_event(
                    session, agent=agent, operation=op, target_table="agent_preferences",
                    target_id=pref["id"],
                )
    except Exception:
        return  # best-effort


async def retrieve_lessons(
    session: AsyncSession, *, agent: str, query_text: str,
    settings: Settings | None = None, k: int = 3
) -> str:
    """Build the 'lessons from past feedback' block injected into the NARRATION prompt only.

    Returns '' when nothing is learned yet, or on any error (graceful degrade)."""
    settings = settings or get_settings()
    try:
        emb = await _embed(query_text, settings)
        if emb is None:
            return ""
        wins = await memory.search_cases(session, agent=agent, embedding=emb, k=k, min_effectiveness=0.8)
        nearby = await memory.search_cases(session, agent=agent, embedding=emb, k=4, min_effectiveness=None)
        losses = [c for c in nearby if (c.get("effectiveness") or 1.0) <= 0.0][:2]
        # Only ACTIVE prefs reach narration, and only for the canary fraction they've rolled out to
        # (Phase C/D governance). A candidate/quarantined rule is never injected until approved.
        prefs_all = await memory.active_preferences(session, agent=agent, limit=12)
        prefs = [
            p for p in prefs_all
            if governance.in_canary(
                str(p["id"]), str(p.get("tenant_id") or "global"), int(p.get("rollout_pct") or 100)
            )
        ][:3]

        parts: list[str] = []
        if prefs:
            parts.append("Learned preferences (distilled from past human edits):")
            parts += [f"- {p['preference_text']}" for p in prefs if p.get("preference_text")]
        if wins:
            parts.append("Approaches a human APPROVED in similar past situations:")
            parts += [f"- {c['recommendation_summary']}" for c in wins if c.get("recommendation_summary")]
        if losses:
            parts.append("Approaches a human REJECTED or UNDID before — avoid these:")
            parts += [f"- {c['recommendation_summary']}" for c in losses if c.get("recommendation_summary")]
        return "\n".join(parts).strip()
    except Exception:
        return ""
