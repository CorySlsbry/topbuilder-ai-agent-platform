"""API-facing schemas (spec-shaped) + mapper for the Financial agent."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.agents.financial.analytics import FinancialAnalysis


class JobProfitabilityOut(BaseModel):
    job_id: str
    name: str
    customer_segment: str
    earned_revenue: float
    actual_cost: float
    margin_to_date: float
    budget_margin: float
    profitability_index: float
    billing_position: float
    confidence: float
    reasoning: str


class CashFlowBucketOut(BaseModel):
    horizon_days: int
    inflows: float
    outflows: float
    projected_cash: float
    confidence: float


class LeakageWarningOut(BaseModel):
    job_id: str
    name: str
    kind: str
    severity_usd: float
    detail: str
    confidence: float


class SegmentMarginOut(BaseModel):
    segment: str
    earned_revenue: float
    cost: float
    margin: float


class FinancialTotals(BaseModel):
    projects_at_risk: int
    total_leakage_usd: float
    cash_30_day: float
    cash_90_day: float
    lowest_margin_segment: str | None


class FinancialRunResult(BaseModel):
    run_id: uuid.UUID | None = None
    agent: str = "financial"
    source_system: str = "ServiceTitan"  # the tenant's field-service system of record (fsm_provider)
    analysis_timestamp: datetime
    as_of: date
    starting_cash: float
    wip_profitability: list[JobProfitabilityOut]
    cash_flow_projection: list[CashFlowBucketOut]
    leakage_warnings: list[LeakageWarningOut]
    segment_margins: list[SegmentMarginOut]
    totals: FinancialTotals
    reasoning_logs: str
    inputs_hash: str


def build_result(
    analysis: FinancialAnalysis,
    *,
    narrative: str,
    analysis_timestamp: datetime,
    run_id: uuid.UUID | None = None,
    source_system: str = "ServiceTitan",
) -> FinancialRunResult:
    wip = [JobProfitabilityOut(**vars(j)) for j in analysis.job_profitability]
    cash = [CashFlowBucketOut(**vars(b)) for b in analysis.cash_flow]
    leakage = [
        LeakageWarningOut(
            job_id=w.job_id,
            name=w.name,
            kind=w.kind,
            severity_usd=round(w.severity_cents / 100, 2),
            detail=w.detail,
            confidence=w.confidence,
        )
        for w in analysis.leakage
    ]
    segments = [SegmentMarginOut(**vars(s)) for s in analysis.segment_margins]
    cash_by = {b.horizon_days: b.projected_cash for b in analysis.cash_flow}
    worst = min(analysis.segment_margins, key=lambda s: s.margin).segment if analysis.segment_margins else None

    totals = FinancialTotals(
        projects_at_risk=len(leakage),
        total_leakage_usd=round(sum(w.severity_usd for w in leakage), 2),
        cash_30_day=cash_by.get(30, analysis.starting_cash),
        cash_90_day=cash_by.get(90, analysis.starting_cash),
        lowest_margin_segment=worst,
    )
    return FinancialRunResult(
        run_id=run_id,
        source_system=source_system,
        analysis_timestamp=analysis_timestamp,
        as_of=analysis.as_of,
        starting_cash=analysis.starting_cash,
        wip_profitability=wip,
        cash_flow_projection=cash,
        leakage_warnings=leakage,
        segment_margins=segments,
        totals=totals,
        reasoning_logs=narrative,
        inputs_hash=analysis.inputs_hash,
    )
