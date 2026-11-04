"""Orchestration entry point for the Routing / Dispatch agent."""
from __future__ import annotations

import dataclasses
import uuid
from datetime import date, datetime, timezone
from time import perf_counter

from app.agents import _telemetry
from app.agents.routing.analytics import RoutingAnalysis
from app.agents.routing.data import assemble_triage_data
from app.agents.routing.graph import ROUTING_GRAPH
from app.agents.routing.reasoning import explain_triage
from app.agents.routing.schemas import RoutingRunResult, TriageRunResult, build_result, build_triage_result
from app.agents.routing.triage import TriageAnalysis, analyze_triage
from app.config import get_settings
from app.db import tenant_session
from app.integrations.dispatch.client import get_dispatch_client
from app.integrations.providers.registry import display_name
from app.repositories import runs
from app.repositories import tenant_settings as tenant_settings_repo
from app.security import Principal

AGENT = "routing"
TRIAGE_AGENT = "routing_triage"  # free-text agent slug (NO migration) — coexists with drive-time runs
HORIZON_DAYS = 1  # a single dispatch day
TRIAGE_HORIZON_DAYS = 3  # the 3-day call board

_TRIAGE_LESSON_QUERY = (
    "Dispatch triage advisory brief: P1/P2/P3 priority matrix, emergency jobs first, technician "
    "skill match and revenue ranking, 3-day call board capacity, jobs needing a human."
)
# Coarse, situation-independent retrieval query. The high-value learned signal — CIPHER preferences
# distilled from past human edits — is general (e.g. "lead with the drive-time saved, name the
# unassigned trades"), so a domain-anchored query surfaces it well; case win/loss recall is already
# agent-scoped. Keeps the graph pure (no DB session inside it): the service retrieves, the reason node
# only narrates.
_LESSON_QUERY = (
    "Routing / dispatch advisory brief: technician assignments, drive-time saved, unassigned jobs "
    "needing a human, trades coverage, recommended dispatch plan."
)


def _recommendation_rows(analysis: RoutingAnalysis) -> list[dict]:
    rows: list[dict] = []
    for s in analysis.suggestions:
        rows.append({"kind": "route_assignment", "payload": dataclasses.asdict(s),
                     "confidence": s.confidence, "economic_impact_cents": None})
    for u in analysis.unassigned:
        rows.append({"kind": "unassigned_job", "payload": dataclasses.asdict(u),
                     "confidence": None, "economic_impact_cents": None})
    return rows


def _reasoning_rows(analysis: RoutingAnalysis, reasoning_source: str) -> list[tuple[str, str]]:
    rows = [
        (
            "analyze:summary",
            f"inputs_hash={analysis.inputs_hash}; jobs={analysis.totals.jobs}; "
            f"assigned={analysis.totals.assigned}; unassigned={analysis.totals.unassigned}; "
            f"drive_saved_min={analysis.totals.drive_minutes_saved}; reasoning_source={reasoning_source}",
        )
    ]
    rows += [(f"assign:{s.job_id}", s.reasoning) for s in analysis.suggestions]
    rows += [(f"unassigned:{u.job_id}", u.reason) for u in analysis.unassigned]
    return rows


def _situation_brief(analysis: RoutingAnalysis) -> str:
    """A numbers-light description of the SITUATION (drivers/counts) for case retrieval — never the
    authoritative figures (those live only in the deterministic engine, per ADR 0003)."""
    t = analysis.totals
    trades = ", ".join(sorted({u.trade for u in analysis.unassigned})) or "none"
    return (
        f"Routing/dispatch run; {t.jobs} job(s); {t.assigned} assigned across {t.techs_used} "
        f"technician(s); {t.unassigned} unassigned (trades needing a human: {trades})."
    )


async def run_routing_analysis(
    principal: Principal, *, as_of: date | None = None, force: bool = False
) -> RoutingRunResult:
    settings = get_settings()
    as_of = as_of or date.today()
    client = get_dispatch_client(as_of=as_of, settings=settings)
    started = perf_counter()

    # Self-learning READ: pull distilled lessons (preferences + past wins/losses) to steer the
    # NARRATION only (ADR-0003: never the figures). Isolated session + best-effort → '' on any error,
    # which is byte-identical to the pre-learning behavior.
    lessons = ""
    try:
        from app.learning import service as learning

        async with tenant_session(principal.tenant_id) as ls:
            lessons = await learning.retrieve_lessons(
                ls, agent=AGENT, query_text=_LESSON_QUERY, settings=settings
            )
    except Exception:
        lessons = ""

    # Provider resolution (best-effort): which field-service system this tenant runs on
    # (tenant_settings.fsm_provider). Steers NARRATION + the source_system metadata string only —
    # never a figure (ADR 0003). Any failure (missing table/row) -> the ServiceTitan flagship default.
    provider = "ServiceTitan"
    try:
        async with tenant_session(principal.tenant_id) as ps:
            provider = display_name(await tenant_settings_repo.get_fsm_provider(ps))
    except Exception:
        provider = "ServiceTitan"

    telemetry = _telemetry.start_collection()  # per-run narration cost (NULL on template path)
    try:
        state = await ROUTING_GRAPH.ainvoke(
            {
                "as_of": as_of,
                "settings": settings,
                "client": client,
                "lessons": lessons,
                "provider": provider,
            }
        )
    except Exception as exc:
        duration_ms = int((perf_counter() - started) * 1000)
        async with tenant_session(principal.tenant_id) as session:
            failed_id = uuid.uuid4()
            await runs.create_run(
                session, run_id=failed_id, agent=AGENT, status="failed", horizon_days=HORIZON_DAYS,
                inputs_hash=None, created_by=principal.user_id, duration_ms=duration_ms,
                error=str(exc), result=None,
            )
            await runs.insert_audit(
                session, actor=str(principal.user_id), action="routing.run.failed",
                target=str(failed_id), detail={"error": str(exc)},
            )
        raise

    analysis: RoutingAnalysis = state["analysis"]
    narrative: str = state["narrative"]
    reasoning_source: str = state.get("reasoning_source", "template")
    duration_ms = int((perf_counter() - started) * 1000)
    run_id = uuid.uuid4()
    result = build_result(
        analysis,
        narrative=narrative,
        analysis_timestamp=datetime.now(timezone.utc),
        run_id=run_id,
        source_system=provider,
    )

    async with tenant_session(principal.tenant_id) as session:
        if not force:
            existing = await runs.get_existing_result_by_hash(
                session, agent=AGENT, inputs_hash=analysis.inputs_hash
            )
            if existing is not None:
                return RoutingRunResult.model_validate(existing)
        await runs.create_run(
            session, run_id=run_id, agent=AGENT, status="succeeded", horizon_days=HORIZON_DAYS,
            inputs_hash=analysis.inputs_hash, created_by=principal.user_id, duration_ms=duration_ms,
            result=result.model_dump(mode="json"), **telemetry.as_run_fields(),
        )
        await runs.add_recommendations(session, run_id=run_id, rows=_recommendation_rows(analysis))
        await runs.add_reasoning(session, run_id=run_id, rows=_reasoning_rows(analysis, reasoning_source))
        await runs.insert_audit(
            session, actor=str(principal.user_id), action="routing.run", target=str(run_id),
            detail={"inputs_hash": analysis.inputs_hash, "jobs": analysis.totals.jobs,
                    "drive_saved_min": analysis.totals.drive_minutes_saved, "reasoning_source": reasoning_source},
        )

    # Self-learning: record this run as a CASE (outcome 'pending' until feedback labels it). Best-effort
    # + ISOLATED session so a learning failure can never roll back the run we just persisted above.
    try:
        from app.learning import service as learning

        async with tenant_session(principal.tenant_id) as ls:
            await learning.record_case(
                ls,
                agent=AGENT,
                run_id=run_id,
                problem_text=_situation_brief(analysis),
                recommendation_summary=(narrative or "")[:600],
                recommendation_kind="routing_advisory",
                problem_features={
                    "jobs": analysis.totals.jobs,
                    "assigned": analysis.totals.assigned,
                    "unassigned": analysis.totals.unassigned,
                },
                settings=settings,
            )
    except Exception:
        pass

    return result


async def get_latest_result(principal: Principal) -> dict | None:
    async with tenant_session(principal.tenant_id) as session:
        return await runs.get_latest_result(session, agent=AGENT)


async def get_result_by_id(principal: Principal, run_id: uuid.UUID) -> dict | None:
    async with tenant_session(principal.tenant_id) as session:
        return await runs.get_result_by_id(session, run_id=run_id)


async def list_recent_runs(principal: Principal, *, limit: int = 20) -> list[dict]:
    async with tenant_session(principal.tenant_id) as session:
        return await runs.list_runs(session, agent=AGENT, limit=limit)


# --------------------------------------------------------------------------------------------
# Triage (P1/P2/P3 + revenue-rank + 3-day board)
# --------------------------------------------------------------------------------------------
def _triage_recommendation_rows(analysis: TriageAnalysis) -> list[dict]:
    rows: list[dict] = []
    for j in analysis.triaged:
        rows.append({
            "kind": "triage_assignment" if j.assignable else "triage_needs_human",
            "payload": dataclasses.asdict(j), "confidence": None,
            "economic_impact_cents": j.revenue_cents or None,
        })
    return rows


def _triage_reasoning_rows(analysis: TriageAnalysis, reasoning_source: str) -> list[tuple[str, str]]:
    t = analysis.totals
    rows = [(
        "triage:summary",
        f"inputs_hash={analysis.inputs_hash}; jobs={t.jobs}; p1={t.p1}; p2={t.p2}; p3={t.p3}; "
        f"assignable={t.assignable}; needs_human={t.needs_human}; reasoning_source={reasoning_source}",
    )]
    rows += [(f"triage:{j.job_id}", j.reason) for j in analysis.triaged]
    rows += [(f"board:{d.day}",
              f"{d.job_count} job(s); {d.booked_min}/{d.capacity_min}min; util {d.utilization_pct}%")
             for d in analysis.board]
    return rows


def _triage_situation_brief(analysis: TriageAnalysis) -> str:
    t = analysis.totals
    return (
        f"Dispatch triage run; {t.jobs} job(s) ({t.p1} P1 / {t.p2} P2 / {t.p3} P3); "
        f"{t.assignable} with a recommended tech, {t.needs_human} needing a human."
    )


async def run_triage_analysis(
    principal: Principal, *, as_of: date | None = None, force: bool = False
) -> TriageRunResult:
    settings = get_settings()
    as_of = as_of or date.today()
    client = get_dispatch_client(as_of=as_of, settings=settings)
    started = perf_counter()

    # Self-learning READ (narration-only, ADR-0003) — isolated session, best-effort.
    lessons = ""
    try:
        from app.learning import service as learning

        async with tenant_session(principal.tenant_id) as ls:
            lessons = await learning.retrieve_lessons(
                ls, agent=TRIAGE_AGENT, query_text=_TRIAGE_LESSON_QUERY, settings=settings
            )
    except Exception:
        lessons = ""

    provider = "ServiceTitan"
    try:
        async with tenant_session(principal.tenant_id) as ps:
            provider = display_name(await tenant_settings_repo.get_fsm_provider(ps))
    except Exception:
        provider = "ServiceTitan"

    telemetry = _telemetry.start_collection()  # per-run narration cost (NULL on template path)
    try:
        data = await assemble_triage_data(client, as_of=as_of)
        analysis = analyze_triage(data, board_days=TRIAGE_HORIZON_DAYS)
        reasoning_source = "template" if (settings.disable_llm or not settings.anthropic_api_key) else "llm"
        narrative = await explain_triage(analysis, settings, lessons=lessons, provider=provider)
    except Exception as exc:
        duration_ms = int((perf_counter() - started) * 1000)
        async with tenant_session(principal.tenant_id) as session:
            failed_id = uuid.uuid4()
            await runs.create_run(
                session, run_id=failed_id, agent=TRIAGE_AGENT, status="failed",
                horizon_days=TRIAGE_HORIZON_DAYS, inputs_hash=None, created_by=principal.user_id,
                duration_ms=duration_ms, error=str(exc), result=None,
            )
            await runs.insert_audit(
                session, actor=str(principal.user_id), action="routing.triage.failed",
                target=str(failed_id), detail={"error": str(exc)},
            )
        raise

    duration_ms = int((perf_counter() - started) * 1000)
    run_id = uuid.uuid4()
    result = build_triage_result(
        analysis, narrative=narrative, analysis_timestamp=datetime.now(timezone.utc),
        run_id=run_id, source_system=provider,
    )

    async with tenant_session(principal.tenant_id) as session:
        if not force:
            existing = await runs.get_existing_result_by_hash(
                session, agent=TRIAGE_AGENT, inputs_hash=analysis.inputs_hash
            )
            if existing is not None:
                return TriageRunResult.model_validate(existing)
        await runs.create_run(
            session, run_id=run_id, agent=TRIAGE_AGENT, status="succeeded",
            horizon_days=TRIAGE_HORIZON_DAYS, inputs_hash=analysis.inputs_hash,
            created_by=principal.user_id, duration_ms=duration_ms,
            result=result.model_dump(mode="json"), **telemetry.as_run_fields(),
        )
        await runs.add_recommendations(session, run_id=run_id, rows=_triage_recommendation_rows(analysis))
        await runs.add_reasoning(session, run_id=run_id, rows=_triage_reasoning_rows(analysis, reasoning_source))
        await runs.insert_audit(
            session, actor=str(principal.user_id), action="routing.triage", target=str(run_id),
            detail={"inputs_hash": analysis.inputs_hash, "jobs": analysis.totals.jobs,
                    "p1": analysis.totals.p1, "needs_human": analysis.totals.needs_human,
                    "reasoning_source": reasoning_source},
        )

    # Self-learning WRITE (best-effort, isolated session).
    try:
        from app.learning import service as learning

        async with tenant_session(principal.tenant_id) as ls:
            await learning.record_case(
                ls, agent=TRIAGE_AGENT, run_id=run_id,
                problem_text=_triage_situation_brief(analysis),
                recommendation_summary=(narrative or "")[:600],
                recommendation_kind="triage_advisory",
                problem_features={"jobs": analysis.totals.jobs, "p1": analysis.totals.p1,
                                  "needs_human": analysis.totals.needs_human},
                settings=settings,
            )
    except Exception:
        pass

    return result


async def get_latest_triage(principal: Principal) -> dict | None:
    async with tenant_session(principal.tenant_id) as session:
        return await runs.get_latest_result(session, agent=TRIAGE_AGENT)
