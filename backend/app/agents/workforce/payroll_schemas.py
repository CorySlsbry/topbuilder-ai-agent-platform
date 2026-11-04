"""API-facing schemas + mapper for the payroll advisory run.

Every dollar figure is the deterministic engine's *cents* surfaced as USD (ADR 0003); this layer only
formats and rolls up — it never recomputes. ``flagged_count`` workers are the ones whose self-reported
pay-form hours diverge from the clock beyond tolerance, i.e. the payroll-adjustment review queue.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.agents.workforce.payroll import PayrollRun, WorkerPay


def _usd(cents: int) -> float:
    return round(cents / 100, 2)


class WorkerPayOut(BaseModel):
    worker_id: str
    worker_name: str
    pay_class: str  # hourly | piece_rate | commission
    regular_hours: float
    overtime_hours: float
    doubletime_hours: float
    computed_hours: float
    claimed_hours: float | None
    hours_discrepancy: float  # claimed - computed
    needs_review: bool
    gross_pay_usd: float
    reasoning: str


class PayrollTotals(BaseModel):
    workers: int
    total_gross_usd: float
    flagged_count: int


class PayrollRunResult(BaseModel):
    run_id: uuid.UUID | None = None
    agent: str = "payroll"
    source_system: str = "ServiceTitan"  # the tenant's field-service system of record (fsm_provider)
    analysis_timestamp: datetime
    period_start: date
    period_end: date
    worker_pays: list[WorkerPayOut]
    totals: PayrollTotals
    reasoning_logs: str
    inputs_hash: str


def _worker_pay_out(wp: WorkerPay) -> WorkerPayOut:
    return WorkerPayOut(
        worker_id=wp.worker_id,
        worker_name=wp.worker_name,
        pay_class=wp.pay_class,
        regular_hours=wp.regular_hours,
        overtime_hours=wp.overtime_hours,
        doubletime_hours=wp.doubletime_hours,
        computed_hours=wp.computed_hours,
        claimed_hours=wp.claimed_hours,
        hours_discrepancy=wp.hours_discrepancy,
        needs_review=wp.needs_review,
        gross_pay_usd=_usd(wp.gross_pay_cents),
        reasoning=wp.reasoning,
    )


def build_result(
    run: PayrollRun,
    *,
    narrative: str,
    analysis_timestamp: datetime,
    run_id: uuid.UUID | None = None,
    source_system: str = "ServiceTitan",
) -> PayrollRunResult:
    worker_pays = [_worker_pay_out(wp) for wp in run.worker_pays]
    totals = PayrollTotals(
        workers=len(worker_pays),
        total_gross_usd=_usd(run.total_gross_cents),
        flagged_count=run.flagged_count,
    )
    return PayrollRunResult(
        run_id=run_id,
        source_system=source_system,
        analysis_timestamp=analysis_timestamp,
        period_start=run.period_start,
        period_end=run.period_end,
        worker_pays=worker_pays,
        totals=totals,
        reasoning_logs=narrative,
        inputs_hash=run.inputs_hash,
    )
