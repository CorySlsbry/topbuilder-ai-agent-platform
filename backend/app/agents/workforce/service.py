"""Orchestration entry point for the Workforce agent.

Runs the LangGraph agent (compute, no DB) and then persists the result atomically inside a single
tenant-scoped transaction. Compute and persistence are separated so a compute failure can be
recorded in its own transaction rather than rolled back with everything else.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from time import perf_counter

from app.agents import _telemetry
from app.agents.workforce.analytics import WorkforceAnalysis
from app.agents.workforce.graph import WORKFORCE_GRAPH
from app.agents.workforce.schemas import WorkforceRunResult, build_result
from app.config import get_settings
from app.db import tenant_session
from app.integrations.providers.registry import display_name
from app.integrations.servicetitan.client import get_servicetitan_client
from app.repositories import runs
from app.repositories import tenant_settings as tenant_settings_repo
from app.security import Principal

AGENT = "workforce"
DEFAULT_HORIZON_DAYS = 21
MIN_HORIZON_DAYS = 7
MAX_HORIZON_DAYS = 28
# Coarse, situation-independent retrieval query. The high-value learned signal — CIPHER preferences
# distilled from past human edits — is general (e.g. "lead with the dollar impact, not the hours"), so a
# domain-anchored query surfaces it well; case win/loss recall is already agent-scoped. Keeps the graph
# pure (no DB session inside it): the service retrieves, the reason node only narrates.
_LESSON_QUERY = (
    "Workforce advisory narrative: understaffing risk by trade-week, avoidable overtime by "
    "technician, utilization, mitigation candidates, recommended staffing action."
)


def _situation_brief(analysis: WorkforceAnalysis) -> str:
    """A numbers-light description of the SITUATION (drivers/counts) for case retrieval — never the
    authoritative figures (those live only in the deterministic engine, per ADR 0003)."""
    trades = sorted({r.trade for r in analysis.understaffing_risks})
    return (
        f"Workforce advisory run; {len(analysis.understaffing_risks)} understaffing trade-week(s) "
        f"({', '.join(trades) or 'none'}); {len(analysis.overtime_risks)} technician(s) at "
        f"overtime risk."
    )


async def run_workforce_analysis(
    principal: Principal,
    *,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
    as_of: date | None = None,
    force: bool = False,
) -> WorkforceRunResult:
    settings = get_settings()
    as_of = as_of or date.today()
    horizon_days = max(MIN_HORIZON_DAYS, min(MAX_HORIZON_DAYS, horizon_days))
    client = get_servicetitan_client(as_of=as_of, settings=settings)
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

    # Begin per-run LLM telemetry on THIS task; the reasoning node's model call records into it and we
    # read it back after the graph completes. Template-path runs leave it at zero -> NULL columns.
    telemetry = _telemetry.start_collection()
    try:
        state = await WORKFORCE_GRAPH.ainvoke(
            {
                "as_of": as_of,
                "horizon_days": horizon_days,
                "settings": settings,
                "client": client,
                "lessons": lessons,
                "provider": provider,
            }
        )
    except Exception as exc:  # record the failure in its own transaction, then re-raise
        duration_ms = int((perf_counter() - started) * 1000)
        async with tenant_session(principal.tenant_id) as session:
            failed_id = uuid.uuid4()
            await runs.create_run(
                session,
                run_id=failed_id,
                agent=AGENT,
                status="failed",
                horizon_days=horizon_days,
                inputs_hash=None,
                created_by=principal.user_id,
                duration_ms=duration_ms,
                error=str(exc),
                result=None,
            )
            await runs.insert_audit(
                session,
                actor=str(principal.user_id),
                action="workforce.run.failed",
                target=str(failed_id),
                detail={"error": str(exc), "horizon_days": horizon_days},
            )
        raise

    analysis: WorkforceAnalysis = state["analysis"]
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
                return WorkforceRunResult.model_validate(existing)
        await runs.create_run(
            session,
            run_id=run_id,
            agent=AGENT,
            status="succeeded",
            horizon_days=horizon_days,
            inputs_hash=analysis.inputs_hash,
            created_by=principal.user_id,
            duration_ms=duration_ms,
            error=None,
            result=result.model_dump(mode="json"),
            **telemetry.as_run_fields(),
        )
        await runs.insert_recommendations(session, run_id=run_id, analysis=analysis)
        await runs.insert_reasoning_logs(
            session, run_id=run_id, analysis=analysis, reasoning_source=reasoning_source
        )
        await runs.insert_audit(
            session,
            actor=str(principal.user_id),
            action="workforce.run",
            target=str(run_id),
            detail={
                "horizon_days": horizon_days,
                "inputs_hash": analysis.inputs_hash,
                "appointments": len(state["data"].appointments),
                "reasoning_source": reasoning_source,
            },
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
                recommendation_kind="workforce_advisory",
                problem_features={
                    "understaffing": len(analysis.understaffing_risks),
                    "overtime": len(analysis.overtime_risks),
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
