"""Orchestration entry point for the Financial Forecasting agent."""
from __future__ import annotations

import dataclasses
import uuid
from datetime import date, datetime, timezone
from time import perf_counter

from app.agents import _telemetry
from app.agents.financial.analytics import FinancialAnalysis
from app.agents.financial.graph import FINANCIAL_GRAPH
from app.agents.financial.schemas import FinancialRunResult, build_result
from app.config import get_settings
from app.db import tenant_session
from app.integrations.accounting.client import get_accounting_client
from app.integrations.providers.registry import display_name
from app.repositories import runs
from app.repositories import tenant_settings as tenant_settings_repo
from app.security import Principal

AGENT = "financial"
HORIZON_DAYS = 90
# Coarse, situation-independent retrieval query. The high-value learned signal — CIPHER preferences
# distilled from past human edits — is general (e.g. "lead with the dollar exposure, not the %"), so a
# domain-anchored query surfaces it well; case win/loss recall is already agent-scoped. Keeps the graph
# pure (no DB session inside it): the service retrieves, the reason node only narrates.
_LESSON_QUERY = (
    "Financial advisory narrative: cash-flow forecast, margin leakage, eroding project "
    "profitability, lowest-margin segment, recommended action."
)


def _recommendation_rows(analysis: FinancialAnalysis) -> list[dict]:
    rows = [
        {
            "kind": "leakage",
            "payload": dataclasses.asdict(w),
            "confidence": w.confidence,
            "economic_impact_cents": w.severity_cents,
        }
        for w in analysis.leakage
    ]
    rows += [
        {
            "kind": "wip",
            "payload": dataclasses.asdict(j),
            "confidence": j.confidence,
            "economic_impact_cents": None,
        }
        for j in analysis.job_profitability
    ]
    return rows


def _reasoning_rows(analysis: FinancialAnalysis, reasoning_source: str) -> list[tuple[str, str]]:
    rows = [
        (
            "analyze:summary",
            f"inputs_hash={analysis.inputs_hash}; jobs={len(analysis.job_profitability)}; "
            f"leakage={len(analysis.leakage)}; reasoning_source={reasoning_source}",
        )
    ]
    rows += [(f"leakage:{w.job_id}", w.detail) for w in analysis.leakage]
    rows += [(f"wip:{j.job_id}", j.reasoning) for j in analysis.job_profitability]
    return rows


def _situation_brief(analysis: FinancialAnalysis) -> str:
    """A numbers-light description of the SITUATION (drivers/counts) for case retrieval — never the
    authoritative figures (those live only in the deterministic engine, per ADR 0003)."""
    segment = (
        min(analysis.segment_margins, key=lambda s: s.margin).segment
        if analysis.segment_margins
        else "n/a"
    )
    eroding = sum(1 for j in analysis.job_profitability if j.profitability_index < 1.0)
    return (
        f"Financial advisory run; {len(analysis.leakage)} margin-leakage item(s); "
        f"{eroding} eroding project(s); lowest-margin segment {segment}."
    )


async def run_financial_analysis(
    principal: Principal, *, as_of: date | None = None, force: bool = False
) -> FinancialRunResult:
    settings = get_settings()
    as_of = as_of or date.today()
    client = get_accounting_client(as_of=as_of, settings=settings)
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
        state = await FINANCIAL_GRAPH.ainvoke(
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
                session,
                run_id=failed_id,
                agent=AGENT,
                status="failed",
                horizon_days=HORIZON_DAYS,
                inputs_hash=None,
                created_by=principal.user_id,
                duration_ms=duration_ms,
                error=str(exc),
                result=None,
            )
            await runs.insert_audit(
                session,
                actor=str(principal.user_id),
                action="financial.run.failed",
                target=str(failed_id),
                detail={"error": str(exc)},
            )
        raise

    analysis: FinancialAnalysis = state["analysis"]
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
                return FinancialRunResult.model_validate(existing)
        await runs.create_run(
            session,
            run_id=run_id,
            agent=AGENT,
            status="succeeded",
            horizon_days=HORIZON_DAYS,
            inputs_hash=analysis.inputs_hash,
            created_by=principal.user_id,
            duration_ms=duration_ms,
            result=result.model_dump(mode="json"),
            **telemetry.as_run_fields(),
        )
        await runs.add_recommendations(session, run_id=run_id, rows=_recommendation_rows(analysis))
        await runs.add_reasoning(
            session, run_id=run_id, rows=_reasoning_rows(analysis, reasoning_source)
        )
        await runs.insert_audit(
            session,
            actor=str(principal.user_id),
            action="financial.run",
            target=str(run_id),
            detail={
                "inputs_hash": analysis.inputs_hash,
                "leakage": len(analysis.leakage),
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
                recommendation_kind="financial_advisory",
                problem_features={
                    "leakage": len(analysis.leakage),
                    "eroding": sum(1 for j in analysis.job_profitability if j.profitability_index < 1.0),
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
