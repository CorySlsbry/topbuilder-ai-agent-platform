"""API schemas (spec-shaped) + mapper for the Routing / Dispatch agent."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.agents.routing.analytics import RoutingAnalysis
from app.agents.routing.triage import TriageAnalysis


def _fmt(minutes: int) -> str:
    h, m = divmod(int(minutes), 60)
    return f"{h:02d}:{m:02d}"


class RoutingSuggestionOut(BaseModel):
    job_id: str
    customer_name: str
    trade: str
    required_skill: str
    tech_id: str
    tech_name: str
    sequence: int
    drive_minutes: int
    arrival: str  # HH:MM
    confidence: float
    reasoning: str


class UnassignedJobOut(BaseModel):
    job_id: str
    trade: str
    reason: str


class RoutingTotals(BaseModel):
    jobs: int
    assigned: int
    unassigned: int
    techs_used: int
    drive_minutes_optimized: int
    drive_minutes_baseline: int
    drive_minutes_saved: int
    hours_saved: float


class RoutingRunResult(BaseModel):
    run_id: uuid.UUID | None = None
    agent: str = "routing"
    source_system: str = "ServiceTitan"  # the tenant's field-service system of record (fsm_provider)
    analysis_timestamp: datetime
    as_of: date
    suggestions: list[RoutingSuggestionOut]
    unassigned: list[UnassignedJobOut]
    totals: RoutingTotals
    reasoning_logs: str
    inputs_hash: str


def build_result(
    analysis: RoutingAnalysis,
    *,
    narrative: str,
    analysis_timestamp: datetime,
    run_id: uuid.UUID | None = None,
    source_system: str = "ServiceTitan",
) -> RoutingRunResult:
    suggestions = [
        RoutingSuggestionOut(
            job_id=s.job_id, customer_name=s.customer_name, trade=s.trade,
            required_skill=s.required_skill, tech_id=s.tech_id, tech_name=s.tech_name,
            sequence=s.sequence, drive_minutes=s.drive_minutes, arrival=_fmt(s.arrival_min),
            confidence=s.confidence, reasoning=s.reasoning,
        )
        for s in analysis.suggestions
    ]
    unassigned = [
        UnassignedJobOut(job_id=u.job_id, trade=u.trade, reason=u.reason) for u in analysis.unassigned
    ]
    t = analysis.totals
    totals = RoutingTotals(
        jobs=t.jobs, assigned=t.assigned, unassigned=t.unassigned, techs_used=t.techs_used,
        drive_minutes_optimized=t.drive_minutes_optimized,
        drive_minutes_baseline=t.drive_minutes_baseline,
        drive_minutes_saved=t.drive_minutes_saved,
        hours_saved=round(t.drive_minutes_saved / 60, 1),
    )
    return RoutingRunResult(
        run_id=run_id,
        source_system=source_system,
        analysis_timestamp=analysis_timestamp,
        as_of=analysis.as_of,
        suggestions=suggestions,
        unassigned=unassigned,
        totals=totals,
        reasoning_logs=narrative,
        inputs_hash=analysis.inputs_hash,
    )


# --------------------------------------------------------------------------------------------
# Triage (P1/P2/P3 + revenue-rank + 3-day board) schemas
# --------------------------------------------------------------------------------------------
class TechRankOut(BaseModel):
    tech_id: str
    tech_name: str
    drive_minutes: int
    avg_ticket: float          # dollars (cents -> dollars at the API boundary)
    conversion_pct: int
    revenue_score: int         # 0..100
    score: int                 # 0..100 overall rank score
    reason: str


class TriagedJobOut(BaseModel):
    job_id: str
    customer_name: str
    trade: str
    required_skill: str
    job_type: str
    priority: int              # 1=P1, 2=P2, 3=P3
    priority_label: str
    severity_source: str
    revenue: float             # dollars
    recommended_tech_id: str | None
    recommended_tech_name: str | None
    candidates: list[TechRankOut]
    assignable: bool
    reason: str


class BoardDayOut(BaseModel):
    day: date
    capacity_minutes: int
    booked_minutes: int
    free_minutes: int
    over_capacity_minutes: int
    utilization_pct: int
    job_count: int
    unavailable_tech_ids: list[str]


class TriageTotalsOut(BaseModel):
    jobs: int
    p1: int
    p2: int
    p3: int
    assignable: int
    needs_human: int


class TriageRunResult(BaseModel):
    run_id: uuid.UUID | None = None
    agent: str = "routing"
    kind: str = "triage"
    source_system: str = "ServiceTitan"
    analysis_timestamp: datetime
    as_of: date
    triaged: list[TriagedJobOut]
    board: list[BoardDayOut]
    unassigned_queue: list[str]
    totals: TriageTotalsOut
    reasoning_logs: str
    inputs_hash: str


def build_triage_result(
    analysis: TriageAnalysis,
    *,
    narrative: str,
    analysis_timestamp: datetime,
    run_id: uuid.UUID | None = None,
    source_system: str = "ServiceTitan",
) -> TriageRunResult:
    triaged = [
        TriagedJobOut(
            job_id=j.job_id, customer_name=j.customer_name, trade=j.trade,
            required_skill=j.required_skill, job_type=j.job_type, priority=j.priority,
            priority_label=j.priority_label, severity_source=j.severity_source,
            revenue=round(j.revenue_cents / 100, 2),
            recommended_tech_id=j.recommended_tech_id,
            recommended_tech_name=j.recommended_tech_name,
            candidates=[
                TechRankOut(
                    tech_id=c.tech_id, tech_name=c.tech_name, drive_minutes=c.drive_minutes,
                    avg_ticket=round(c.avg_ticket_cents / 100, 2), conversion_pct=c.conversion_pct,
                    revenue_score=c.revenue_score_bp // 100, score=c.score_bp // 100, reason=c.reason,
                )
                for c in j.candidates
            ],
            assignable=j.assignable, reason=j.reason,
        )
        for j in analysis.triaged
    ]
    board = [
        BoardDayOut(
            day=date.fromisoformat(d.day), capacity_minutes=d.capacity_min,
            booked_minutes=d.booked_min, free_minutes=d.free_min,
            over_capacity_minutes=d.over_capacity_min, utilization_pct=d.utilization_pct,
            job_count=d.job_count, unavailable_tech_ids=d.unavailable_tech_ids,
        )
        for d in analysis.board
    ]
    t = analysis.totals
    totals = TriageTotalsOut(
        jobs=t.jobs, p1=t.p1, p2=t.p2, p3=t.p3, assignable=t.assignable, needs_human=t.needs_human,
    )
    return TriageRunResult(
        run_id=run_id, source_system=source_system, analysis_timestamp=analysis_timestamp,
        as_of=analysis.as_of, triaged=triaged, board=board,
        unassigned_queue=analysis.unassigned_queue, totals=totals, reasoning_logs=narrative,
        inputs_hash=analysis.inputs_hash,
    )
