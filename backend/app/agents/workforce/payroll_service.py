"""Orchestration entry point for the payroll advisory run (part of the Workforce agent).

Assembles the pay-period inputs, runs the pure ``compute_payroll`` engine (deterministic, ADR 0003),
narrates the result, then persists it atomically inside a single tenant-scoped transaction — the same
shape as ``workforce/service.py`` and ``booking/service.py``. Worker pays are persisted as advisory
recommendations; nothing is written back to ServiceTitan here (the manual "payroll adjustment" goes
through the human-approved action gate, ADR 0007). Compute and persistence are separated so a compute
failure is recorded in its own transaction rather than rolled back with everything else.
"""
from __future__ import annotations

import dataclasses
import uuid
from datetime import UTC, date, datetime
from time import perf_counter

from app.agents import _telemetry
from app.agents.workforce import payroll_reasoning
from app.agents.workforce.payroll import PayrollRun, compute_payroll
from app.agents.workforce.payroll_data import assemble_payroll_data
from app.agents.workforce.payroll_schemas import PayrollRunResult, build_result
from app.config import get_settings
from app.db import tenant_session
from app.integrations.providers.registry import display_name
from app.repositories import runs
from app.repositories import tenant_settings as tenant_settings_repo
from app.security import Principal

AGENT = "payroll"
# Payroll is a fixed pay-period window, not a forecast horizon; we record the period length in the
# shared `horizon_days` column for run bookkeeping (idempotency keys off `inputs_hash`).
DEFAULT_PERIOD_DAYS = 7
# Coarse, situation-independent retrieval query (the high-value learned signal — CIPHER preferences
# distilled from past human edits — is general). The graph stays pure: the service retrieves, the
# narration layer only narrates.
_LESSON_QUERY = (
    "Payroll advisory narrative: gross pay by worker, California overtime, piece-rate and commission "
    "classes, claimed-vs-clocked pay-form discrepancies, payroll-adjustment review queue."
)


def _recommendation_rows(run: PayrollRun) -> list[dict]:
    """One advisory recommendation per worker; flagged (needs-review) workers carry no economic
    impact figure (the gap is an hours discrepancy, not a dollar impact — ADR 0003)."""
    return [
        {
            "kind": "worker_pay_review" if wp.needs_review else "worker_pay",
            "payload": dataclasses.asdict(wp),
            "confidence": None,
            "economic_impact_cents": wp.gross_pay_cents,
        }
        for wp in run.worker_pays
    ]


def _reasoning_rows(run: PayrollRun) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = [
        (
            "compute:summary",
            f"inputs_hash={run.inputs_hash}; workers={len(run.worker_pays)}; "
            f"total_gross_cents={run.total_gross_cents}; flagged={run.flagged_count}",
        )
    ]
    rows += [(f"worker:{wp.worker_id}", wp.reasoning) for wp in run.worker_pays]
    return rows


def _situation_brief(run: PayrollRun) -> str:
    """A numbers-light description of the SITUATION for case retrieval — never the authoritative
    figures (those live only in the deterministic engine, per ADR 0003)."""
    classes = sorted({wp.pay_class for wp in run.worker_pays})
    return (
        f"Payroll advisory run; {len(run.worker_pays)} worker(s) across pay classes "
        f"({', '.join(classes) or 'none'}); {run.flagged_count} pay-form discrepancy(ies) needing a "
        "payroll-adjustment review."
    )


async def run_payroll_analysis(
    principal: Principal,
    *,
    period_start: date | None = None,
    period_end: date | None = None,
    force: bool = False,
) -> PayrollRunResult:
    settings = get_settings()
    period_start = period_start or date.today()
    started = perf_counter()

    # Self-learning READ: pull distilled lessons to steer NARRATION only (ADR-0003: never figures).
    # Isolated session + best-effort -> '' on any error (byte-identical to pre-learning behavior).
    lessons = ""
    try:
        from app.learning import service as learning

        async with tenant_session(principal.tenant_id) as ls:
            lessons = await learning.retrieve_lessons(
                ls, agent=AGENT, query_text=_LESSON_QUERY, settings=settings
            )
    except Exception:
        lessons = ""

    # Provider resolution (best-effort): NARRATION + source_system metadata only, never a figure.
    provider = "ServiceTitan"
    try:
        async with tenant_session(principal.tenant_id) as ps:
            provider = display_name(await tenant_settings_repo.get_fsm_provider(ps))
    except Exception:
        provider = "ServiceTitan"

    period_days = DEFAULT_PERIOD_DAYS
    telemetry = _telemetry.start_collection()  # per-run narration cost (NULL on template path)
    try:
        run = compute_payroll(
            assemble_payroll_data(
                period_start=period_start, period_end=period_end, settings=settings
            )
        )
        period_days = (run.period_end - run.period_start).days + 1
        narrative = await payroll_reasoning.explain(
            run, settings, lessons=lessons, provider=provider
        )
    except Exception as exc:  # record the failure in its own transaction, then re-raise
        duration_ms = int((perf_counter() - started) * 1000)
        async with tenant_session(principal.tenant_id) as session:
            failed_id = uuid.uuid4()
            await runs.create_run(
                session, run_id=failed_id, agent=AGENT, status="failed", horizon_days=period_days,
                inputs_hash=None, created_by=principal.user_id, duration_ms=duration_ms,
                error=str(exc), result=None,
            )
            await runs.insert_audit(
                session, actor=str(principal.user_id), action="payroll.run.failed",
                target=str(failed_id), detail={"error": str(exc)},
            )
        raise

    duration_ms = int((perf_counter() - started) * 1000)
    run_id = uuid.uuid4()
    result = build_result(
        run,
        narrative=narrative,
        analysis_timestamp=datetime.now(UTC),
        run_id=run_id,
        source_system=provider,
    )

    async with tenant_session(principal.tenant_id) as session:
        if not force:
            existing = await runs.get_existing_result_by_hash(
                session, agent=AGENT, inputs_hash=run.inputs_hash
            )
            if existing is not None:
                return PayrollRunResult.model_validate(existing)
        await runs.create_run(
            session, run_id=run_id, agent=AGENT, status="succeeded", horizon_days=period_days,
            inputs_hash=run.inputs_hash, created_by=principal.user_id, duration_ms=duration_ms,
            result=result.model_dump(mode="json"), **telemetry.as_run_fields(),
        )
        await runs.add_recommendations(session, run_id=run_id, rows=_recommendation_rows(run))
        await runs.add_reasoning(session, run_id=run_id, rows=_reasoning_rows(run))
        await runs.insert_audit(
            session, actor=str(principal.user_id), action="payroll.run", target=str(run_id),
            detail={
                "inputs_hash": run.inputs_hash,
                "workers": len(run.worker_pays),
                "flagged_count": run.flagged_count,
                "total_gross_cents": run.total_gross_cents,
            },
        )

    # Self-learning WRITE: record this run as a CASE (outcome 'pending' until feedback labels it).
    # Best-effort + ISOLATED session so a learning failure can never roll back the run persisted above.
    try:
        from app.learning import service as learning

        async with tenant_session(principal.tenant_id) as ls:
            await learning.record_case(
                ls,
                agent=AGENT,
                run_id=run_id,
                problem_text=_situation_brief(run),
                recommendation_summary=(narrative or "")[:600],
                recommendation_kind="payroll_advisory",
                problem_features={
                    "workers": len(run.worker_pays),
                    "flagged_count": run.flagged_count,
                },
                settings=settings,
            )
    except Exception:
        pass

    return result


def proposed_adjustment_params(
    result: PayrollRunResult, worker_id: str, *, run_id: uuid.UUID | None = None
) -> dict:
    """Build the ``payroll_adjustment`` action params for a flagged worker from a run result.

    Pure helper (tested): finds the worker in the result and packages the clock/claimed hours + the
    period for the human-approved adjustment. Raises if the worker isn't flagged for review, so the
    gate is never asked to post an adjustment for a worker whose hours already reconcile.
    """
    match = next((wp for wp in result.worker_pays if wp.worker_id == worker_id), None)
    if match is None:
        raise ValueError(f"worker '{worker_id}' is not in this payroll run")
    if not match.needs_review:
        raise ValueError(f"worker '{worker_id}' has no pay-form discrepancy to adjust")
    return {
        "worker_id": match.worker_id,
        "worker_name": match.worker_name,
        "period_start": result.period_start.isoformat(),
        "period_end": result.period_end.isoformat(),
        "claimed_hours": match.claimed_hours,
        "computed_hours": match.computed_hours,
        "hours_discrepancy": match.hours_discrepancy,
        "run_id": str(run_id) if run_id else (str(result.run_id) if result.run_id else None),
    }


async def get_latest_result(principal: Principal) -> dict | None:
    async with tenant_session(principal.tenant_id) as session:
        return await runs.get_latest_result(session, agent=AGENT)


async def get_result_by_id(principal: Principal, run_id: uuid.UUID) -> dict | None:
    async with tenant_session(principal.tenant_id) as session:
        return await runs.get_result_by_id(session, run_id=run_id)


async def list_recent_runs(principal: Principal, *, limit: int = 20) -> list[dict]:
    async with tenant_session(principal.tenant_id) as session:
        return await runs.list_runs(session, agent=AGENT, limit=limit)
