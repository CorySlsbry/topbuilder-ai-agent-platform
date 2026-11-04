"""Deterministic Financial Forecasting engine (GAAP percentage-of-completion).

No LLM, no randomness — every figure is reproducible (ADR 0003). The reasoning node narrates these
numbers; it never recomputes them.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date

from app.agents.financial.models import FinancialData

HORIZONS = (30, 60, 90)
CASH_HORIZON_FACTORS = {30: 1.0, 60: 0.9, 90: 0.8}
SAMPLE_SATURATION = 100  # payment-history samples before the cash confidence saturates
MARGIN_EROSION_THRESHOLD = 0.05
COST_OVERRUN_THRESHOLD = 0.05


# --------------------------------------------------------------------------------------------
# Result types
# --------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class JobProfitability:
    job_id: str
    name: str
    customer_segment: str
    earned_revenue: float
    actual_cost: float
    margin_to_date: float
    budget_margin: float
    profitability_index: float
    billing_position: float  # + overbilled / - underbilled
    confidence: float
    reasoning: str


@dataclass(frozen=True)
class CashFlowBucket:
    horizon_days: int
    inflows: float
    outflows: float
    projected_cash: float
    confidence: float


@dataclass(frozen=True)
class LeakageWarning:
    job_id: str
    name: str
    kind: str  # 'cost_overrun' | 'margin_erosion'
    severity_cents: int
    detail: str
    confidence: float


@dataclass(frozen=True)
class SegmentMargin:
    segment: str
    earned_revenue: float
    cost: float
    margin: float


@dataclass(frozen=True)
class FinancialAnalysis:
    as_of: date
    starting_cash: float
    job_profitability: list[JobProfitability]
    cash_flow: list[CashFlowBucket]
    leakage: list[LeakageWarning]
    segment_margins: list[SegmentMargin]
    inputs_hash: str


# --------------------------------------------------------------------------------------------
# Pure primitives
# --------------------------------------------------------------------------------------------
def earned_revenue(contract_value: float, percent_complete: float) -> float:
    return contract_value * percent_complete


def margin_to_date(earned: float, actual_cost: float) -> float:
    return (earned - actual_cost) / earned if earned > 0 else 0.0


def budget_margin(contract_value: float, budgeted_cost: float) -> float:
    return (contract_value - budgeted_cost) / contract_value if contract_value > 0 else 0.0


def profitability_index(margin_to_date_: float, budget_margin_: float) -> float:
    return margin_to_date_ / budget_margin_ if budget_margin_ > 0 else 0.0


def billing_position(billed_to_date: float, earned: float) -> float:
    return billed_to_date - earned


def cost_overrun_ratio(actual_cost: float, budgeted_cost: float, percent_complete: float) -> float:
    budgeted_to_date = budgeted_cost * percent_complete
    return actual_cost / budgeted_to_date if budgeted_to_date > 0 else 0.0


def _job_confidence(percent_complete: float) -> float:
    return round(min(1.0, 0.4 + 0.6 * percent_complete), 3)


def _bucket_of(offset_days: float) -> int | None:
    for h in HORIZONS:
        if offset_days <= h:
            return h
    return None


# --------------------------------------------------------------------------------------------
# Engine
# --------------------------------------------------------------------------------------------
def analyze(data: FinancialData) -> FinancialAnalysis:
    target = data.target_gross_margin

    # --- job profitability + leakage ---
    jobs_out: list[JobProfitability] = []
    leakage: list[LeakageWarning] = []
    seg_earned: dict[str, float] = defaultdict(float)
    seg_cost: dict[str, float] = defaultdict(float)

    for job in data.jobs:
        earned = earned_revenue(job.contract_value, job.percent_complete)
        mtd = margin_to_date(earned, job.actual_cost_to_date)
        bm = budget_margin(job.contract_value, job.budgeted_cost)
        pi = profitability_index(mtd, bm)
        bill_pos = billing_position(job.billed_to_date, earned)
        conf = _job_confidence(job.percent_complete)

        seg_earned[job.customer_segment] += earned
        seg_cost[job.customer_segment] += job.actual_cost_to_date

        jobs_out.append(
            JobProfitability(
                job_id=job.id,
                name=job.name,
                customer_segment=job.customer_segment,
                earned_revenue=round(earned, 2),
                actual_cost=round(job.actual_cost_to_date, 2),
                margin_to_date=round(mtd, 4),
                budget_margin=round(bm, 4),
                profitability_index=round(pi, 4),
                billing_position=round(bill_pos, 2),
                confidence=conf,
                reasoning=(
                    f"{job.name} ({job.customer_segment}): {job.percent_complete:.0%} complete, "
                    f"earned ${earned:,.0f} vs cost ${job.actual_cost_to_date:,.0f} -> margin "
                    f"{mtd:.1%} (budget {bm:.1%}, index {pi:.2f}). "
                    f"{'Over' if bill_pos >= 0 else 'Under'}billed ${abs(bill_pos):,.0f}."
                ),
            )
        )

        overrun = cost_overrun_ratio(job.actual_cost_to_date, job.budgeted_cost, job.percent_complete)
        is_overrun = overrun > 1.0 + COST_OVERRUN_THRESHOLD
        is_erosion = mtd < target - MARGIN_EROSION_THRESHOLD
        if is_overrun or is_erosion:
            overrun_cents = max(0, round((job.actual_cost_to_date - job.budgeted_cost * job.percent_complete) * 100))
            erosion_cents = max(0, round((target - mtd) * earned * 100))
            if overrun_cents >= erosion_cents:
                kind, severity = "cost_overrun", overrun_cents
            else:
                kind, severity = "margin_erosion", erosion_cents
            leakage.append(
                LeakageWarning(
                    job_id=job.id,
                    name=job.name,
                    kind=kind,
                    severity_cents=severity,
                    detail=(
                        f"{job.name}: actual cost ${job.actual_cost_to_date:,.0f} vs "
                        f"budgeted-to-date ${job.budgeted_cost * job.percent_complete:,.0f} "
                        f"(overrun x{overrun:.2f}); margin {mtd:.1%} vs target {target:.1%}. "
                        f"Estimated exposure ~${severity / 100:,.0f}."
                    ),
                    confidence=conf,
                )
            )

    # --- cash flow 30/60/90 ---
    velocity = {v.customer_segment: v.avg_days_to_pay for v in data.payment_velocity}
    total_sample = sum(v.sample_size for v in data.payment_velocity)
    data_factor = min(1.0, total_sample / SAMPLE_SATURATION) if total_sample else 0.0

    inflow_by: dict[int, float] = {h: 0.0 for h in HORIZONS}
    outflow_by: dict[int, float] = {h: 0.0 for h in HORIZONS}
    for inv in data.ar_invoices:
        if inv.paid:
            continue
        offset = (inv.issued - data.as_of).days + velocity.get(inv.customer_segment, 30)
        bucket = _bucket_of(offset)
        if bucket is not None:
            inflow_by[bucket] += inv.amount
    for bill in data.ap_bills:
        if bill.paid:
            continue
        bucket = _bucket_of((bill.due - data.as_of).days)
        if bucket is not None:
            outflow_by[bucket] += bill.amount

    cash_flow: list[CashFlowBucket] = []
    running = data.starting_cash
    for h in HORIZONS:
        running += inflow_by[h] - outflow_by[h]
        cash_flow.append(
            CashFlowBucket(
                horizon_days=h,
                inflows=round(inflow_by[h], 2),
                outflows=round(outflow_by[h], 2),
                projected_cash=round(running, 2),
                confidence=round(CASH_HORIZON_FACTORS[h] * data_factor, 3),
            )
        )

    # --- segment margins ---
    segment_margins = [
        SegmentMargin(
            segment=seg,
            earned_revenue=round(seg_earned[seg], 2),
            cost=round(seg_cost[seg], 2),
            margin=round(margin_to_date(seg_earned[seg], seg_cost[seg]), 4),
        )
        for seg in sorted(seg_earned)
    ]

    jobs_out.sort(key=lambda j: j.profitability_index)
    leakage.sort(key=lambda w: w.severity_cents, reverse=True)

    return FinancialAnalysis(
        as_of=data.as_of,
        starting_cash=data.starting_cash,
        job_profitability=jobs_out,
        cash_flow=cash_flow,
        leakage=leakage,
        segment_margins=segment_margins,
        inputs_hash=_hash_inputs(data),
    )


def _hash_inputs(data: FinancialData) -> str:
    payload = {
        "as_of": data.as_of.isoformat(),
        "starting_cash": data.starting_cash,
        "target": data.target_gross_margin,
        "jobs": sorted((asdict(j) for j in data.jobs), key=lambda r: r["id"]),
        "ar": sorted(
            ({**asdict(i), "issued": i.issued.isoformat(), "due": i.due.isoformat()} for i in data.ar_invoices),
            key=lambda r: r["id"],
        ),
        "ap": sorted(
            ({**asdict(b), "due": b.due.isoformat()} for b in data.ap_bills), key=lambda r: r["id"]
        ),
        "velocity": sorted((asdict(v) for v in data.payment_velocity), key=lambda r: r["customer_segment"]),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
