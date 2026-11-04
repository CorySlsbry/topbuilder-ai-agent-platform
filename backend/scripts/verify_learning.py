"""Standalone verification of the self-learning loop against REAL Postgres (no pytest needed).

Runs INSIDE the api container (which has asyncpg + sqlalchemy + the app), so the DB integration path
is exercised even though the host Python lacks the deps. Mirrors tests/test_learning_loop.py:

  record CASE -> human EDIT labels it + seeds a quarantined PREFERENCE -> quorum(3) activates it ->
  retrieval surfaces it -> a second tenant sees NONE of it.

Idempotent: it deletes its own apex/financial rows first, so it can be re-run. Exit 0 = PASS.
"""
from __future__ import annotations

import asyncio
import sys
import uuid

from sqlalchemy import text

from app.config import get_settings
from app.db import tenant_session
from app.demo import DEMO_TENANTS
from app.learning import eval_harness
from app.learning import service as learning
from app.repositories import governance as gov
from app.repositories import memory, runs

CORRECTION = "Always lead with the dollar exposure, then name the single highest-impact action."


async def _cleanup(tenant) -> None:
    async with tenant_session(tenant) as s:
        await s.execute(text("DELETE FROM agent_preferences WHERE agent='financial'"))
        await s.execute(
            text("DELETE FROM agent_cases WHERE agent='financial' AND recommendation_kind='financial_advisory'")
        )
        await s.execute(text("DELETE FROM learning_events WHERE agent='financial'"))
        await s.execute(text("DELETE FROM agent_runs WHERE agent='financial' AND inputs_hash LIKE 'verify-%'"))


async def _lessons(tenant, settings) -> str:
    async with tenant_session(tenant) as s:
        return await learning.retrieve_lessons(
            s, agent="financial", query_text="margin leakage cash flow", settings=settings
        )


async def main() -> int:
    settings = get_settings()
    apex = DEMO_TENANTS["apex"].tenant_id
    summit = DEMO_TENANTS["summit"].tenant_id
    checks: list[tuple[str, bool]] = []

    def check(name: str, cond: bool) -> None:
        checks.append((name, bool(cond)))
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}")

    await _cleanup(apex)
    await _cleanup(summit)

    run_id = uuid.uuid4()

    # 0) a real agent_runs row must exist first — agent_cases.run_id is an FK to agent_runs(id).
    #    (In production, financial/service.py creates this run immediately before record_case.)
    async with tenant_session(apex) as s:
        await runs.create_run(
            s, run_id=run_id, agent="financial", status="succeeded", horizon_days=90,
            inputs_hash=f"verify-{run_id.hex[:12]}", created_by=DEMO_TENANTS["apex"].admin_user_id,
            duration_ms=1, result=None,
        )

    # 1) record a case
    async with tenant_session(apex) as s:
        case_id = await learning.record_case(
            s, agent="financial", run_id=run_id,
            problem_text="Financial advisory run; 2 margin-leakage item(s); 1 eroding project.",
            recommendation_summary="Flagged 2 leakage items; recommended a change order on the Bell job.",
            recommendation_kind="financial_advisory", settings=settings,
        )
    check("record_case inserts a vector(3072) case under RLS", case_id is not None)

    # 2) substantial edit -> label + seed preference
    async with tenant_session(apex) as s:
        await learning.on_feedback(
            s, agent="financial", run_id=run_id, rating="edit", correction=CORRECTION, settings=settings,
        )
    async with tenant_session(apex) as s:
        case = await memory.get_case_by_run(s, run_id=run_id)
    check("case labeled 'edited'", bool(case) and case["outcome"] == "edited")
    check("edit_cost recorded > 0.25 (substantial)", bool(case) and (case["edit_cost"] or 0) > 0.25)
    check("effectiveness ~ 0.0 for a big edit", bool(case) and abs((case["effectiveness"] or 0)) < 1e-6)

    # 3) quorum gate: 1 edit stays quarantined (not even a candidate yet)
    async with tenant_session(apex) as s:
        q = await gov.list_preferences(s, agent="financial", status="quarantined")
        actives0 = await memory.active_preferences(s, agent="financial")
    check("after 1 edit: quarantined (not a candidate)", any(q) and actives0 == [])

    # two more corroborations -> CANDIDATE (Phase C gate: quorum no longer auto-activates)
    for _ in range(2):
        async with tenant_session(apex) as s:
            await learning.on_feedback(
                s, agent="financial", run_id=run_id, rating="edit", correction=CORRECTION, settings=settings,
            )
    async with tenant_session(apex) as s:
        cands = await gov.list_preferences(s, agent="financial", status="candidate")
        actives1 = await memory.active_preferences(s, agent="financial")
    check("quorum (>=3) -> CANDIDATE, not auto-active",
          any("dollar exposure" in (p["preference_text"] or "") for p in cands))
    check("candidate is NOT yet active (gate holds)", actives1 == [])
    check("retrieval ignores an unapproved candidate",
          "dollar exposure" not in (await _lessons(apex, settings)))

    # 4) eval-gate + human approval -> ACTIVE, then retrieval surfaces it
    cand = cands[0]
    async with tenant_session(apex) as s:
        ev = await eval_harness.evaluate_candidate(s, preference=cand, settings=settings)
    check("eval gate verdict = pass (safety + no golden regressions)", ev["verdict"] == "pass")
    async with tenant_session(apex) as s:
        approved = await gov.approve_preference(s, preference_id=cand["id"], reviewed_by=None, rollout_pct=100)
    check("approve -> ACTIVE", bool(approved) and approved["status"] == "active")
    check("retrieve_lessons surfaces the APPROVED preference", "dollar exposure" in (await _lessons(apex, settings)))

    # 5) tenant isolation
    async with tenant_session(summit) as s:
        summit_case = await memory.get_case_by_run(s, run_id=run_id)
        summit_actives = await memory.active_preferences(s, agent="financial")
        summit_lessons = await learning.retrieve_lessons(
            s, agent="financial", query_text="margin leakage cash flow", settings=settings,
        )
    check("isolation: Summit cannot see Apex's case", summit_case is None)
    check("isolation: Summit cannot see Apex's preference", summit_actives == [])
    check("isolation: Summit's lessons exclude Apex's preference", "dollar exposure" not in summit_lessons)

    passed = sum(1 for _, ok in checks if ok)
    total = len(checks)
    print(f"\nLEARNING LOOP: {passed}/{total} checks passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
