"""API-facing schemas + mapper for the rolling-capacity advisory run.

This layer only formats and rolls up the deterministic engine output (ADR 0003) — it never recomputes.
The per-(technician, job_type) ``estimate_hours`` is the engine's credibility-blended rolling
moving-target; ``efficiency_delta_hours`` (estimate - baseline) and the derived ``pace`` read
("faster"/"slower"/"on baseline") say whether the tech beats the job-type baseline. The week
projection flags techs whose assigned week exceeds their contracted hours and names same-trade techs
with slack who could absorb the overflow.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.agents.workforce.capacity import TechJobTypeDuration, TechWeekProjection

# A learned estimate within this many hours of the job-type baseline reads as "on baseline" rather
# than faster/slower (so noise around the line is not over-claimed). Narration-only threshold.
PACE_TOLERANCE_HOURS = 0.25


def pace_read(efficiency_delta_hours: float, *, tolerance: float = PACE_TOLERANCE_HOURS) -> str:
    """A plain-language read of the efficiency delta: negative => faster than the job-type baseline."""
    if efficiency_delta_hours < -tolerance:
        return "faster"
    if efficiency_delta_hours > tolerance:
        return "slower"
    return "on baseline"


class TechDurationOut(BaseModel):
    technician_id: str
    job_type: str
    trade: str
    estimate_hours: float
    rolling_hours: float
    baseline_hours: float
    sample_size: int
    confidence: float
    efficiency_delta_hours: float  # estimate - baseline; negative => faster than baseline
    pace: str                      # "faster" | "slower" | "on baseline"


class TechWeekProjectionOut(BaseModel):
    technician_id: str
    trade: str
    job_count: int
    projected_hours: float
    contracted_hours: float
    overtime_hours: float
    confidence: float
    redistribute_to: list[str]
    reasoning: str


class CapacityTotals(BaseModel):
    technicians: int
    duration_pairs: int          # number of (tech, job_type) learned estimates
    techs_over_capacity: int     # techs projected into overtime next week
    total_overtime_hours: float  # summed projected overtime across all techs


class CapacityRunResult(BaseModel):
    run_id: uuid.UUID | None = None
    agent: str = "capacity"  # free-text label, surfaced inside the Workforce department
    source_system: str = "ServiceTitan"  # the tenant's field-service system of record (fsm_provider)
    analysis_timestamp: datetime
    as_of: date
    durations: list[TechDurationOut]
    projections: list[TechWeekProjectionOut]
    totals: CapacityTotals
    reasoning_logs: str
    inputs_hash: str


def _duration_out(d: TechJobTypeDuration) -> TechDurationOut:
    return TechDurationOut(
        technician_id=d.technician_id,
        job_type=d.job_type,
        trade=d.trade,
        estimate_hours=d.estimate_hours,
        rolling_hours=d.rolling_hours,
        baseline_hours=d.baseline_hours,
        sample_size=d.sample_size,
        confidence=d.confidence,
        efficiency_delta_hours=d.efficiency_delta_hours,
        pace=pace_read(d.efficiency_delta_hours),
    )


def _projection_out(p: TechWeekProjection) -> TechWeekProjectionOut:
    return TechWeekProjectionOut(
        technician_id=p.technician_id,
        trade=p.trade,
        job_count=p.job_count,
        projected_hours=p.projected_hours,
        contracted_hours=p.contracted_hours,
        overtime_hours=p.overtime_hours,
        confidence=p.confidence,
        redistribute_to=list(p.redistribute_to),
        reasoning=p.reasoning,
    )


def build_result(
    *,
    as_of: date,
    durations: list[TechJobTypeDuration],
    projections: list[TechWeekProjection],
    inputs_hash: str,
    narrative: str,
    analysis_timestamp: datetime,
    run_id: uuid.UUID | None = None,
    source_system: str = "ServiceTitan",
) -> CapacityRunResult:
    duration_out = [_duration_out(d) for d in durations]
    projection_out = [_projection_out(p) for p in projections]
    totals = CapacityTotals(
        technicians=len(projection_out),
        duration_pairs=len(duration_out),
        techs_over_capacity=sum(1 for p in projection_out if p.overtime_hours > 0),
        total_overtime_hours=round(sum(p.overtime_hours for p in projection_out), 2),
    )
    return CapacityRunResult(
        run_id=run_id,
        source_system=source_system,
        analysis_timestamp=analysis_timestamp,
        as_of=as_of,
        durations=duration_out,
        projections=projection_out,
        totals=totals,
        reasoning_logs=narrative,
        inputs_hash=inputs_hash,
    )
