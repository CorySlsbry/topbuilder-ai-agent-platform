"""Self-learning loop, end-to-end against Postgres (RLS-scoped):

  record a CASE  ->  a human EDIT labels it + distills a candidate PREFERENCE  ->  the quorum gate
  holds it quarantined until 3 corroborations  ->  it activates  ->  retrieval surfaces it for the
  NARRATION prompt only  ->  another tenant sees NONE of it.

ADR-0003 boundary is structural: this layer only ever touches narration memory (cases/preferences),
never a deterministic figure — so there is no number here to corrupt by learning.
"""
from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.integration


async def test_record_label_distill_quorum_retrieve_and_isolation() -> None:
    from app import db
    from app.config import get_settings
    from app.db import tenant_session
    from app.demo import DEMO_TENANTS
    from app.learning import eval_harness
    from app.learning import service as learning
    from app.repositories import governance as gov
    from app.repositories import memory, runs

    settings = get_settings()
    apex = DEMO_TENANTS["apex"].tenant_id
    summit = DEMO_TENANTS["summit"].tenant_id
    correction = "Always lead with the dollar exposure, then name the single highest-impact action."
    try:
        run_id = uuid.uuid4()

        # 0) A real agent_runs row must exist first — agent_cases.run_id is an FK to agent_runs(id).
        async with tenant_session(apex) as s:
            await runs.create_run(
                s, run_id=run_id, agent="financial", status="succeeded", horizon_days=90,
                inputs_hash=f"itest-{run_id.hex[:12]}", created_by=DEMO_TENANTS["apex"].admin_user_id,
                duration_ms=1, result=None,
            )

        # 1) A run records a CASE (outcome 'pending' until feedback labels it).
        async with tenant_session(apex) as s:
            case_id = await learning.record_case(
                s, agent="financial", run_id=run_id,
                problem_text="Financial advisory run; 2 margin-leakage item(s); 1 eroding project.",
                recommendation_summary="Flagged 2 leakage items; recommended a change order on the Bell job.",
                recommendation_kind="financial_advisory", settings=settings,
            )
        assert case_id is not None  # embedding insert (vector(3072)) succeeded under RLS

        # 2) A substantial human EDIT labels the case AND seeds a quarantined preference.
        async with tenant_session(apex) as s:
            await learning.on_feedback(
                s, agent="financial", run_id=run_id, rating="edit",
                correction=correction, settings=settings,
            )
        async with tenant_session(apex) as s:
            case = await memory.get_case_by_run(s, run_id=run_id)
        assert case is not None
        assert case["outcome"] == "edited"
        assert case["edit_cost"] is not None and case["edit_cost"] > 0.25  # a substantial edit
        assert case["effectiveness"] == pytest.approx(0.0, abs=1e-6)       # big edit -> ~0 effectiveness

        # 3) Quorum gate: one edit is NOT enough — the preference stays quarantined (no behavior change).
        async with tenant_session(apex) as s:
            assert await memory.active_preferences(s, agent="financial") == []

        # Two more identical corrections reach quorum (support>=3) -> the preference becomes a CANDIDATE
        # (Phase C governance: quorum no longer AUTO-activates — it must clear the eval gate + approval).
        for _ in range(2):
            async with tenant_session(apex) as s:
                await learning.on_feedback(
                    s, agent="financial", run_id=run_id, rating="edit",
                    correction=correction, settings=settings,
                )
        async with tenant_session(apex) as s:
            candidates = await gov.list_preferences(s, agent="financial", status="candidate")
            assert any("dollar exposure" in (p["preference_text"] or "") for p in candidates)
            assert await memory.active_preferences(s, agent="financial") == []  # candidate != active

        # An unapproved candidate is NOT injected into narration.
        async with tenant_session(apex) as s:
            assert "dollar exposure" not in await learning.retrieve_lessons(
                s, agent="financial", query_text="margin leakage cash flow", settings=settings,
            )

        # 4) Eval gate + human approval -> ACTIVE; only then does retrieval surface it.
        cand = candidates[0]
        async with tenant_session(apex) as s:
            verdict = await eval_harness.evaluate_candidate(s, preference=cand, settings=settings)
            assert verdict["verdict"] == "pass" and verdict["safety_ok"] and verdict["invariant_ok"]
            approved = await gov.approve_preference(
                s, preference_id=cand["id"], reviewed_by=None, rollout_pct=100
            )
            assert approved is not None and approved["status"] == "active"
        async with tenant_session(apex) as s:
            lessons = await learning.retrieve_lessons(
                s, agent="financial", query_text="margin leakage cash flow", settings=settings,
            )
        assert "dollar exposure" in lessons

        # 5) Tenant isolation: Summit sees none of Apex's learned memory (case OR preference).
        async with tenant_session(summit) as s:
            assert await memory.get_case_by_run(s, run_id=run_id) is None
            assert await memory.active_preferences(s, agent="financial") == []
            summit_lessons = await learning.retrieve_lessons(
                s, agent="financial", query_text="margin leakage cash flow", settings=settings,
            )
        assert "dollar exposure" not in summit_lessons
    finally:
        await db.get_engine().dispose()
        db.get_engine.cache_clear()
        db.get_sessionmaker.cache_clear()
