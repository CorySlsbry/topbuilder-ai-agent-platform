"""API-facing schemas (spec-shaped) + mappers from the deterministic analytics dataclasses."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.agents.workforce.analytics import OvertimeRisk, UnderstaffingRisk, WorkforceAnalysis


def _usd(cents: int) -> float:
    return round(cents / 100, 2)


class UnderstaffingRiskOut(BaseModel):
    week_start: date
    week_offset: int
    trade_type: str
    gap_count: int
    gap_hours: float
    available_hours: float
    projected_required_hours: float
    economic_impact_usd: float
    confidence: float
    reasoning: str


class OvertimeWeekOut(BaseModel):
    week_offset: int
    week_start: date
    scheduled_hours: float
    overtime_hours: float
    confidence: float


class OvertimeRiskOut(BaseModel):
    technician_id: str
    technician_name: str
    trade: str
    projected_overtime_hours: float
    economic_impact_usd: float
    recent_overtime_hours: float
    weeks: list[OvertimeWeekOut]
    mitigation_strategy: str
    mitigation_candidates: list[str]
    confidence: float
    reasoning: str


class TradeUtilizationOut(BaseModel):
    trade: str
    week_offset: int
    available_hours: float
    projected_required_hours: float
    utilization: float


class WorkforceTotals(BaseModel):
    weeks_short: int
    total_understaffing_impact_usd: float
    technicians_in_overtime: int
    total_overtime_premium_usd: float


class WorkforceRunResult(BaseModel):
    run_id: uuid.UUID | None = None
    agent: str = "workforce"
    source_system: str = "ServiceTitan"  # the tenant's field-service system of record (fsm_provider)
    analysis_timestamp: datetime
    as_of: date
    horizon_days: int
    understaffing_risks: list[UnderstaffingRiskOut]
    overtime_risks: list[OvertimeRiskOut]
    utilization: list[TradeUtilizationOut]
    totals: WorkforceTotals
    reasoning_logs: str
    inputs_hash: str


def mitigation_strategy(risk: OvertimeRisk) -> str:
    if risk.mitigation_candidates:
        return (
            "Redistribute peak-week load to same-trade technicians with spare capacity "
            f"({', '.join(risk.mitigation_candidates)}) before approving overtime."
        )
    return (
        "No same-trade slack in the horizon; pre-approve temporary labor or defer non-urgent "
        "jobs to the following week."
    )


def _understaffing_out(risk: UnderstaffingRisk) -> UnderstaffingRiskOut:
    return UnderstaffingRiskOut(
        week_start=risk.week_start,
        week_offset=risk.week_offset,
        trade_type=risk.trade,
        gap_count=risk.gap_count,
        gap_hours=risk.gap_hours,
        available_hours=risk.available_hours,
        projected_required_hours=risk.projected_required_hours,
        economic_impact_usd=_usd(risk.economic_impact_cents),
        confidence=risk.confidence,
        reasoning=risk.reasoning,
    )


def _overtime_out(risk: OvertimeRisk) -> OvertimeRiskOut:
    return OvertimeRiskOut(
        technician_id=risk.technician_id,
        technician_name=risk.technician_name,
        trade=risk.trade,
        projected_overtime_hours=risk.projected_overtime_hours,
        economic_impact_usd=_usd(risk.economic_impact_cents),
        recent_overtime_hours=risk.recent_overtime_hours,
        weeks=[
            OvertimeWeekOut(
                week_offset=w.week_offset,
                week_start=w.week_start,
                scheduled_hours=w.scheduled_hours,
                overtime_hours=w.overtime_hours,
                confidence=w.confidence,
            )
            for w in risk.weeks
        ],
        mitigation_strategy=mitigation_strategy(risk),
        mitigation_candidates=risk.mitigation_candidates,
        confidence=risk.confidence,
        reasoning=risk.reasoning,
    )


def build_result(
    analysis: WorkforceAnalysis,
    *,
    narrative: str,
    analysis_timestamp: datetime,
    run_id: uuid.UUID | None = None,
    source_system: str = "ServiceTitan",
) -> WorkforceRunResult:
    understaffing = [_understaffing_out(r) for r in analysis.understaffing_risks]
    overtime = [_overtime_out(r) for r in analysis.overtime_risks]
    totals = WorkforceTotals(
        weeks_short=len(understaffing),
        total_understaffing_impact_usd=round(sum(r.economic_impact_usd for r in understaffing), 2),
        technicians_in_overtime=len(overtime),
        total_overtime_premium_usd=round(sum(r.economic_impact_usd for r in overtime), 2),
    )
    return WorkforceRunResult(
        run_id=run_id,
        source_system=source_system,
        analysis_timestamp=analysis_timestamp,
        as_of=analysis.as_of,
        horizon_days=analysis.horizon_days,
        understaffing_risks=understaffing,
        overtime_risks=overtime,
        utilization=[
            TradeUtilizationOut(
                trade=u.trade,
                week_offset=u.week_offset,
                available_hours=u.available_hours,
                projected_required_hours=u.projected_required_hours,
                utilization=u.utilization,
            )
            for u in analysis.utilization
        ],
        totals=totals,
        reasoning_logs=narrative,
        inputs_hash=analysis.inputs_hash,
    )
