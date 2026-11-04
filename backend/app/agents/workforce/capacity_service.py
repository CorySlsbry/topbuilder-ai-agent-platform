"""Orchestration entry point for the rolling-capacity advisory run (part of the Workforce agent).

Wires the existing, pure ``capacity.py`` engine (``estimate_tech_durations`` +
``project_tech_overtime``) into a usable, demo-able, persisted surface — the same shape as
``workforce/service.py`` and ``payroll_service.py``:

  1. assemble the inputs from the ServiceTitan adapter boundary (``capacity_data.assemble_capacity_data``;
     fixture by default, fail-closed live skeleton),
  2. run the deterministic engine to get the rolling per-(tech, job_type) durations + the upcoming-week
     overtime projection with same-trade redistribution suggestions (``build_capacity_run`` — pure),
  3. narrate it (``capacity_reasoning.explain`` — never recomputes a figure, ADR 0003),
  4. persist it atomically inside one tenant-scoped transaction under ``agent="capacity"`` (the agent
     column is free-text, so no migration — like Booking), with idempotency keyed off a stable
     ``inputs_hash``. A distinct agent label keeps capacity's run history, idempotency, recommendations
     and learning cases cleanly separated from the main workforce-analysis runs (both surface in the
     Workforce department).

Advisory only: nothing is written back to ServiceTitan here. A staffing/redistribution action would go
through the human-approved action gate (ADR 0007). Learning READ/WRITE hooks run in their own isolated,
best-effort sessions so a learning failure can never roll back the run.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from time import perf_counter

from app.agents import _telemetry
from app.agents.workforce import capacity_reasoning
from app.agents.workforce.capacity import (
    TechJobTypeDuration,
    TechWeekProjection,
    estimate_tech_durations,
    project_tech_overtime,
)
from app.agents.workforce.capacity_data import CapacityData, assemble_capacity_data
from app.agents.workforce.capacity_schemas import CapacityRunResult, build_result
from app.config import get_settings
from app.db import tenant_session
from app.integrations.providers.registry import display_name
from app.repositories import runs
from app.repositories import tenant_settings as tenant_settings_repo
from app.security import Principal

AGENT = "capacity"  # free-text agent label (no migration), distinct from the workforce-analysis runs
# A capacity run reports an UPCOMING-WEEK projection; we record 7 in the shared `horizon_days` column
# for run bookkeeping. Idempotency keys off `inputs_hash`.
CAPACITY_PERIOD_DAYS = 7
# Coarse, situation-independent retrieval query (the high-value learned signal — CIPHER preferences
# distilled from past human edits — is general). The service retrieves; the narration layer narrates.
_LESSON_QUERY = (
    "Rolling capacity advisory narrative: per-technician learned job durations, who is faster or slower "
    "than the job-type baseline, projected weekly overtime, same-trade redistribution to absorb it."
)


@dataclass(frozen=True)
class CapacityRun:
    """The deterministic engine output for one capacity analysis (pure — easy to test + narrate)."""

    as_of: date
    durations: list[TechJobTypeDuration]
    projections: list[TechWeekProjection]
    inputs_hash: str


def _inputs_hash(data: CapacityData) -> str:
    """Stable hash over the engine inputs, so identical inputs reuse the persisted run (idempotency)."""
    payload = {
        "as_of": data.as_of.isoformat(),
        "completed": sorted(
            [
                [j.technician_id, j.job_type, j.trade, j.actual_hours, j.completed_date.isoformat()]
                for j in data.completed_jobs
            ]
        ),
        "assigned": sorted(
            [[a.technician_id, a.job_type, a.trade] for a in data.assigned_jobs]
        ),
        "technicians": sorted(
            [[t.id, t.trade, t.contracted_weekly_hours] for t in data.technicians]
        ),
        "baselines": dict(sorted(data.baselines.items())),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def build_capacity_run(data: CapacityData) -> CapacityRun:
    """Run the pure engine over assembled inputs and package the result (no DB, no LLM, deterministic).

    ``durations`` are sorted (technician_id, job_type) and ``projections`` keep the engine's
    overtime-first order, so the persisted/serialized output is stable for the demo and for tests.
    """
    durations_map = estimate_tech_durations(
        data.completed_jobs, data.baselines, as_of=data.as_of
    )
    durations = sorted(durations_map.values(), key=lambda d: (d.technician_id, d.job_type))
    projections = project_tech_overtime(
        data.technicians, data.assigned_jobs, durations_map, data.baselines
    )
    return CapacityRun(
        as_of=data.as_of,
        durations=durations,
        projections=projections,
        inputs_hash=_inputs_hash(data),
    )


def _recommendation_rows(run: CapacityRun) -> list[dict]:
    """One advisory recommendation per projected-overtime technician (the actionable signal). The
    economic impact (avoidable OT $) is not asserted here — capacity surfaces hours, not a dollar
    figure (ADR 0003); a dollar impact would be computed by the workforce overtime engine separately."""
    return [
        {
            "kind": "overtime_projection",
            "payload": {
                "technician_id": p.technician_id,
                "trade": p.trade,
                "job_count": p.job_count,
                "projected_hours": p.projected_hours,
                "contracted_hours": p.contracted_hours,
                "overtime_hours": p.overtime_hours,
                "redistribute_to": list(p.redistribute_to),
                "reasoning": p.reasoning,
            },
            "confidence": p.confidence,
            "economic_impact_cents": None,
        }
        for p in run.projections
        if p.overtime_hours > 0
    ]


def _reasoning_rows(run: CapacityRun) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = [
        (
            "compute:summary",
            f"inputs_hash={run.inputs_hash}; duration_pairs={len(run.durations)}; "
            f"techs={len(run.projections)}; "
            f"over_capacity={sum(1 for p in run.projections if p.overtime_hours > 0)}",
        )
    ]
    rows += [
        (
            f"duration:{d.technician_id}:{d.job_type}",
            f"estimate {d.estimate_hours}h vs baseline {d.baseline_hours}h "
            f"(delta {d.efficiency_delta_hours:+}h, n={d.sample_size})",
        )
        for d in run.durations
    ]
    rows += [(f"projection:{p.technician_id}", p.reasoning) for p in run.projections]
    return rows


def _situation_brief(run: CapacityRun) -> str:
    """A numbers-light description of the SITUATION for case retrieval — never the authoritative
    figures (those live only in the deterministic engine, per ADR 0003)."""
    over = [p for p in run.projections if p.overtime_hours > 0]
    trades = sorted({p.trade for p in over})
    return (
        f"Rolling-capacity advisory run; {len(run.durations)} learned (technician, job-type) "
        f"duration(s) across {len(run.projections)} technician(s); {len(over)} technician(s) project "
        f"into overtime next week ({', '.join(trades) or 'none'})."
    )


async def run_capacity_analysis(
    principal: Principal, *, as_of: date | None = None, force: bool = False
) -> CapacityRunResult:
    settings = get_settings()
    as_of = as_of or date.today()
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

    telemetry = _telemetry.start_collection()  # per-run narration cost (NULL on template path)
    try:
        run = build_capacity_run(assemble_capacity_data(as_of=as_of, settings=settings))
        narrative = await capacity_reasoning.explain(
            run.durations, run.projections, settings, lessons=lessons, provider=provider
        )
    except Exception as exc:  # record the failure in its own transaction, then re-raise
        duration_ms = int((perf_counter() - started) * 1000)
        async with tenant_session(principal.tenant_id) as session:
            failed_id = uuid.uuid4()
            await runs.create_run(
                session, run_id=failed_id, agent=AGENT, status="failed",
                horizon_days=CAPACITY_PERIOD_DAYS, inputs_hash=None, created_by=principal.user_id,
                duration_ms=duration_ms, error=str(exc), result=None,
            )
            await runs.insert_audit(
                session, actor=str(principal.user_id), action="capacity.run.failed",
                target=str(failed_id), detail={"error": str(exc)},
            )
        raise

    duration_ms = int((perf_counter() - started) * 1000)
    run_id = uuid.uuid4()
    result = build_result(
        as_of=run.as_of,
        durations=run.durations,
        projections=run.projections,
        inputs_hash=run.inputs_hash,
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
                return CapacityRunResult.model_validate(existing)
        await runs.create_run(
            session, run_id=run_id, agent=AGENT, status="succeeded",
            horizon_days=CAPACITY_PERIOD_DAYS, inputs_hash=run.inputs_hash,
            created_by=principal.user_id, duration_ms=duration_ms,
            result=result.model_dump(mode="json"), **telemetry.as_run_fields(),
        )
        await runs.add_recommendations(session, run_id=run_id, rows=_recommendation_rows(run))
        await runs.add_reasoning(session, run_id=run_id, rows=_reasoning_rows(run))
        await runs.insert_audit(
            session, actor=str(principal.user_id), action="capacity.run", target=str(run_id),
            detail={
                "inputs_hash": run.inputs_hash,
                "duration_pairs": len(run.durations),
                "techs": len(run.projections),
                "techs_over_capacity": sum(1 for p in run.projections if p.overtime_hours > 0),
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
                recommendation_kind="capacity_advisory",
                problem_features={
                    "duration_pairs": len(run.durations),
                    "techs_over_capacity": sum(1 for p in run.projections if p.overtime_hours > 0),
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
