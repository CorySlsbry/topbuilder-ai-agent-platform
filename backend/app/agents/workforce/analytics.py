"""Deterministic workforce analytics — the numbers behind every recommendation.

No LLM, no randomness: identical inputs always yield identical figures and confidence scores
(ADR 0003). The agent's reasoning node turns these structured results into prose; it never
recomputes them.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta

from app.agents.workforce import confidence as conf
from app.agents.workforce.models import WorkforceData

# A same-trade technician whose average weekly schedule is below this fraction of contracted hours
# is considered to have spare capacity to absorb a colleague's overtime.
MITIGATION_SLACK = 0.9


# --------------------------------------------------------------------------------------------
# Result types
# --------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class UnderstaffingRisk:
    trade: str
    week_offset: int
    week_start: date
    available_hours: float
    booked_hours: float
    projected_required_hours: float
    gap_hours: float
    gap_count: int
    economic_impact_cents: int
    confidence: float
    reasoning: str


@dataclass(frozen=True)
class OvertimeWeek:
    week_offset: int
    week_start: date
    scheduled_hours: float
    overtime_hours: float
    confidence: float


@dataclass(frozen=True)
class OvertimeRisk:
    technician_id: str
    technician_name: str
    trade: str
    projected_overtime_hours: float
    economic_impact_cents: int
    recent_overtime_hours: float
    weeks: list[OvertimeWeek]
    mitigation_candidates: list[str]
    confidence: float
    reasoning: str


@dataclass(frozen=True)
class TradeUtilization:
    trade: str
    week_offset: int
    available_hours: float
    projected_required_hours: float
    utilization: float


@dataclass(frozen=True)
class WorkforceAnalysis:
    as_of: date
    horizon_days: int
    understaffing_risks: list[UnderstaffingRisk]
    overtime_risks: list[OvertimeRisk]
    utilization: list[TradeUtilization]
    inputs_hash: str


# --------------------------------------------------------------------------------------------
# Pure primitives (property-tested)
# --------------------------------------------------------------------------------------------
def project_overtime_hours(scheduled_hours: float, contracted_hours: float) -> float:
    return max(0.0, scheduled_hours - contracted_hours)


def overtime_premium_cents(hours: float, hourly_cost: float, overtime_multiplier: float) -> int:
    """The *avoidable extra* cost of overtime vs. regular pay, in integer cents."""
    return int(round(hours * hourly_cost * (overtime_multiplier - 1.0) * 100))


def gap_count(gap_hours: float, added_capacity_per_tech: float) -> int:
    """How many additional technician-weeks are needed to close the gap."""
    if added_capacity_per_tech <= 0 or gap_hours <= 0:
        return 0
    return math.ceil(gap_hours / added_capacity_per_tech)


def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _week_of(as_of: date, when: date) -> int:
    return (when - as_of).days // 7


# --------------------------------------------------------------------------------------------
# Engine
# --------------------------------------------------------------------------------------------
def analyze(data: WorkforceData, *, weeks: int | None = None) -> WorkforceAnalysis:
    horizon_weeks = weeks if weeks is not None else max(1, math.ceil(data.horizon_days / 7))

    active = [t for t in data.technicians if t.active]
    trades = sorted({t.trade for t in active})
    econ_by_trade = {e.trade: e for e in data.trade_economics}
    demand_by = {(d.trade, d.week_offset): d.demand_index for d in data.demand_signals}

    roster_by_trade: dict[str, list] = defaultdict(list)
    for tech in active:
        roster_by_trade[tech.trade].append(tech)

    # Aggregate historical duration support per trade (sample volume + sample-weighted completion).
    samples_by_trade: dict[str, int] = defaultdict(int)
    completion_wsum_by_trade: dict[str, float] = defaultdict(float)
    for jd in data.job_durations:
        samples_by_trade[jd.trade] += jd.sample_size
        completion_wsum_by_trade[jd.trade] += jd.sample_size * jd.completion_rate

    def trade_support(trade: str) -> tuple[int, float]:
        n = samples_by_trade.get(trade, 0)
        completion = completion_wsum_by_trade[trade] / n if n else 0.0
        return n, completion

    # Recent overtime (history strictly before as_of) — context for the narrative.
    recent_ot: dict[str, float] = defaultdict(float)
    for ts in data.timesheets:
        if ts.work_date < data.as_of:
            recent_ot[ts.technician_id] += ts.overtime_hours

    # Bucket scheduled hours by (trade, week) and (technician, week).
    booked_tw: dict[tuple[str, int], float] = defaultdict(float)
    count_tw: dict[tuple[str, int], int] = defaultdict(int)
    sched_tech_w: dict[tuple[str, int], float] = defaultdict(float)
    for ap in data.appointments:
        w = _week_of(data.as_of, ap.appt_date)
        if not 0 <= w < horizon_weeks:
            continue
        booked_tw[(ap.trade, w)] += ap.scheduled_hours
        count_tw[(ap.trade, w)] += 1
        if ap.technician_id:
            sched_tech_w[(ap.technician_id, w)] += ap.scheduled_hours

    utilization: list[TradeUtilization] = []
    understaffing: list[UnderstaffingRisk] = []

    for trade in trades:
        roster = roster_by_trade[trade]
        econ = econ_by_trade.get(trade)
        availability = econ.availability_factor if econ else 0.85
        billable = econ.billable_rate if econ else 0.0
        avg_contracted = _avg([t.contracted_weekly_hours for t in roster])
        avg_cost = _avg([t.hourly_cost for t in roster])
        capacity = sum(t.contracted_weekly_hours for t in roster) * availability
        added_per_tech = avg_contracted * availability
        contribution = max(0.0, billable - avg_cost)
        samples, completion = trade_support(trade)

        for w in range(horizon_weeks):
            booked = booked_tw.get((trade, w), 0.0)
            idx = demand_by.get((trade, w), 1.0)
            projected = booked * idx
            week_start = data.as_of + timedelta(days=7 * w)
            util = projected / capacity if capacity > 0 else 0.0
            utilization.append(
                TradeUtilization(trade, w, round(capacity, 2), round(projected, 2), round(util, 4))
            )

            gap = max(0.0, projected - capacity)
            if gap <= 1e-6:
                continue
            gc = gap_count(gap, added_per_tech)
            impact = int(round(gap * contribution * 100))
            cfd = conf.understaffing_confidence(w, samples, completion)
            reasoning = (
                f"{trade.upper()} week of {week_start.isoformat()}: "
                f"{count_tw.get((trade, w), 0)} booked job(s) totaling {booked:.1f}h; "
                f"seasonal demand index {idx:.2f} -> projected {projected:.1f}h vs available "
                f"{capacity:.1f}h ({len(roster)} techs x {avg_contracted:.0f}h x "
                f"{availability:.0%} avail). Shortfall {gap:.1f}h ~= {gc} technician-week(s). "
                f"Confidence from {samples} historical duration samples "
                f"(weighted completion {completion:.0%})."
            )
            understaffing.append(
                UnderstaffingRisk(
                    trade=trade,
                    week_offset=w,
                    week_start=week_start,
                    available_hours=round(capacity, 2),
                    booked_hours=round(booked, 2),
                    projected_required_hours=round(projected, 2),
                    gap_hours=round(gap, 2),
                    gap_count=gc,
                    economic_impact_cents=impact,
                    confidence=cfd,
                    reasoning=reasoning,
                )
            )

    overtime: list[OvertimeRisk] = []
    for tech in active:
        weeks_ot: list[OvertimeWeek] = []
        total_ot = 0.0
        impact = 0
        for w in range(horizon_weeks):
            sched = sched_tech_w.get((tech.id, w), 0.0)
            ot = project_overtime_hours(sched, tech.contracted_weekly_hours)
            if ot <= 1e-6:
                continue
            weeks_ot.append(
                OvertimeWeek(
                    week_offset=w,
                    week_start=data.as_of + timedelta(days=7 * w),
                    scheduled_hours=round(sched, 2),
                    overtime_hours=round(ot, 2),
                    confidence=conf.overtime_confidence(w),
                )
            )
            total_ot += ot
            impact += overtime_premium_cents(ot, tech.hourly_cost, tech.overtime_multiplier)

        if total_ot <= 1e-6:
            continue

        candidates = [
            other.id
            for other in roster_by_trade[tech.trade]
            if other.id != tech.id
            and _avg([sched_tech_w.get((other.id, w), 0.0) for w in range(horizon_weeks)])
            < other.contracted_weekly_hours * MITIGATION_SLACK
        ]
        cfd = sum(ow.overtime_hours * ow.confidence for ow in weeks_ot) / total_ot
        detail = ", ".join(
            f"wk{ow.week_offset} {ow.scheduled_hours:.0f}h sched/{ow.overtime_hours:.1f}h OT"
            for ow in weeks_ot
        )
        reasoning = (
            f"{tech.name} ({tech.trade}) projected {total_ot:.1f} overtime hour(s) across "
            f"{len(weeks_ot)} week(s): {detail}. Avoidable OT premium ~= ${impact / 100:,.0f}."
        )
        if candidates:
            reasoning += f" Same-trade capacity to absorb load: {', '.join(candidates)}."
        else:
            reasoning += " No same-trade slack; consider temporary labor or schedule deferral."
        if recent_ot.get(tech.id):
            reasoning += f" Recent trend: {recent_ot[tech.id]:.1f}h OT logged in the prior 2 weeks."

        overtime.append(
            OvertimeRisk(
                technician_id=tech.id,
                technician_name=tech.name,
                trade=tech.trade,
                projected_overtime_hours=round(total_ot, 2),
                economic_impact_cents=impact,
                recent_overtime_hours=round(recent_ot.get(tech.id, 0.0), 2),
                weeks=weeks_ot,
                mitigation_candidates=candidates,
                confidence=round(cfd, 3),
                reasoning=reasoning,
            )
        )

    understaffing.sort(key=lambda r: r.economic_impact_cents, reverse=True)
    overtime.sort(key=lambda r: r.economic_impact_cents, reverse=True)

    return WorkforceAnalysis(
        as_of=data.as_of,
        horizon_days=data.horizon_days,
        understaffing_risks=understaffing,
        overtime_risks=overtime,
        utilization=utilization,
        inputs_hash=_hash_inputs(data, horizon_weeks),
    )


def _hash_inputs(data: WorkforceData, weeks: int) -> str:
    """Stable SHA-256 over the inputs that affect the result — for audit + idempotency."""
    payload = {
        "as_of": data.as_of.isoformat(),
        "weeks": weeks,
        "technicians": sorted((asdict(t) for t in data.technicians), key=lambda r: r["id"]),
        "trade_economics": sorted((asdict(e) for e in data.trade_economics), key=lambda r: r["trade"]),
        "appointments": sorted(
            (
                {**asdict(ap), "appt_date": ap.appt_date.isoformat()}
                for ap in data.appointments
            ),
            key=lambda r: r["id"],
        ),
        "timesheets": sorted(
            ({**asdict(ts), "work_date": ts.work_date.isoformat()} for ts in data.timesheets),
            key=lambda r: (r["technician_id"], r["work_date"]),
        ),
        "job_durations": sorted((asdict(j) for j in data.job_durations), key=lambda r: r["job_type"]),
        "demand_signals": sorted(
            (asdict(d) for d in data.demand_signals), key=lambda r: (r["trade"], r["week_offset"])
        ),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
