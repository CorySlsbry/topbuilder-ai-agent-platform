"""Deterministic payroll engine for the Workforce agent.

Pure, dependency-free (stdlib only), no LLM, no randomness: identical inputs always yield
identical figures (ADR 0003). The agent's reasoning node narrates these; it never recomputes them.

Models the real pay structure of the client (Summit Heat Pumps), captured in the Alex discovery
call (2026-06-16, see ``docs/ALEX_DISCOVERY_2026-06-16.md``):

  * SERVICE technicians  -> ``hourly``; eligible for overtime.
  * INSTALL technicians   -> ``piece_rate`` ("they get paid whatever they quote anyways"); no hourly OT.
  * SALES / comfort advisors -> ``commission`` only.

Overtime defaults to **British Columbia (the client's jurisdiction — Vancouver Island, BC)**. BC's
ESA daily/weekly thresholds are identical to the "California" rules Alex described on the call, so the
math is unchanged; the difference is the canonical WEEK and the absence of a 7th-day premium. Verified
against the BC Employment Standards Act (Part 4, s.40) overtime guidance, June 2026:

  * Daily:  hours 8-12 in a workday      -> 1.5x  (overtime)
  *         hours over 12 in a workday   -> 2.0x  (double time)
  * Weekly: hours over 40 in a week      -> 1.5x  (overtime), counting ONLY the first 8 hours worked
            each day toward the 40 (so daily-OT hours are never double-counted -> no pyramiding).
  * The BC week for overtime is **Sunday-Saturday** by default; an employer's established workweek can
    differ, so ``PayrollData.workweek_starts_on`` overrides it. Multi-week pay periods are split per week.

  Jurisdiction note (``PayrollData.jurisdiction``): ``"BC"`` (default) uses the Sunday-Saturday week and
  has NO 7th-consecutive-day premium (BC has no such rule). ``"CA"`` shares the same daily/weekly
  thresholds but its week defaults to the pay-period start weekday, and California's 7th-consecutive-
  workday premium is NOT modeled (out of the stated scope). Stat-holiday pay and averaging agreements
  (BC ESA s.37) are out of scope — they are not computed here.

The engine also surfaces the **payroll gap** Alex described: a technician self-reports hours on a
completed-job pay form (his example: *"he says it took him 16 hours, but did it really?"*) that the
payroll clerk must verify before pushing the manual **payroll adjustment**. ``compute_payroll`` pairs
each worker's CLAIMED hours (pay-form) against the COMPUTED clock hours (dispatch -> completion) and
flags any divergence beyond a tolerance, so the proposed adjustment can be reviewed in approval mode
(then posted through the existing action gate, never written silently).
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta

# --------------------------------------------------------------------------------------------
# Overtime thresholds + defaults (BC ESA; overridable per worker / per call)
# --------------------------------------------------------------------------------------------
DAILY_OT_THRESHOLD = 8.0      # hours/day above which time is 1.5x
DAILY_DT_THRESHOLD = 12.0     # hours/day above which time is 2.0x (double time)
WEEKLY_OT_THRESHOLD = 40.0    # straight-time hours/week (first 8h/day) above which time is 1.5x
DEFAULT_OT_MULTIPLIER = 1.5
DEFAULT_DT_MULTIPLIER = 2.0

# Jurisdiction (drives only the default workweek anchor + the 7th-day note; daily/weekly math is shared).
JURISDICTION_BC = "BC"        # British Columbia — the client's jurisdiction (default)
JURISDICTION_CA = "CA"        # California — same thresholds; week defaults to the pay-period start
SUNDAY_WEEKDAY = 6            # BC ESA overtime week is Sunday-Saturday (Mon=0 .. Sun=6)

# A claimed-vs-clocked gap larger than this (hours) is surfaced for human review.
HOURS_DISCREPANCY_TOLERANCE = 0.5

# Pay classifications (free-text on the model so new classes need no migration).
PAY_HOURLY = "hourly"
PAY_PIECE_RATE = "piece_rate"
PAY_COMMISSION = "commission"


# --------------------------------------------------------------------------------------------
# Pure primitives (property-tested)
# --------------------------------------------------------------------------------------------
def daily_overtime_split(
    hours: float,
    *,
    ot_threshold: float = DAILY_OT_THRESHOLD,
    dt_threshold: float = DAILY_DT_THRESHOLD,
) -> tuple[float, float, float]:
    """Split one workday's hours into ``(regular, overtime, doubletime)`` per CA daily rules.

    The three buckets always sum back to ``max(0, hours)``.
    """
    h = max(0.0, hours)
    regular = min(h, ot_threshold)
    doubletime = max(0.0, h - dt_threshold)
    overtime = max(0.0, min(h, dt_threshold) - ot_threshold)
    return regular, overtime, doubletime


def apply_weekly_overtime(
    regular_hours: float, *, threshold: float = WEEKLY_OT_THRESHOLD
) -> tuple[float, float]:
    """Reclassify straight-time hours above the weekly threshold as 1.5x overtime (no pyramiding).

    Returns ``(regular_after, weekly_overtime)``. Only the straight-time (already non-OT) hours are
    passed in, so daily overtime is never double-counted.
    """
    if regular_hours <= threshold:
        return regular_hours, 0.0
    return threshold, regular_hours - threshold


def gross_pay_cents(
    regular_hours: float,
    overtime_hours: float,
    doubletime_hours: float,
    hourly_rate: float,
    *,
    overtime_multiplier: float = DEFAULT_OT_MULTIPLIER,
    doubletime_multiplier: float = DEFAULT_DT_MULTIPLIER,
) -> int:
    """Gross hourly pay in integer cents (regular + OT premium + double-time premium)."""
    dollars = (
        regular_hours * hourly_rate
        + overtime_hours * hourly_rate * overtime_multiplier
        + doubletime_hours * hourly_rate * doubletime_multiplier
    )
    return int(round(dollars * 100))


def hours_discrepancy(claimed_hours: float, computed_hours: float) -> float:
    """Signed gap in hours. Positive => the worker CLAIMED more than the clock shows."""
    return round(claimed_hours - computed_hours, 2)


def _workweek_start(d: date, anchor_weekday: int) -> date:
    """Start date of the employer's 7-day workweek containing ``d`` — the most recent
    ``anchor_weekday`` (0=Mon .. 6=Sun) on or before ``d``. Weekly overtime is evaluated per workweek."""
    return d - timedelta(days=(d.weekday() - anchor_weekday) % 7)


# --------------------------------------------------------------------------------------------
# Domain models (stdlib-only; populated by the ServiceTitan adapter, consumed by the engine)
# --------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Worker:
    id: str
    name: str
    pay_class: str  # PAY_HOURLY | PAY_PIECE_RATE | PAY_COMMISSION
    hourly_rate: float = 0.0
    overtime_multiplier: float = DEFAULT_OT_MULTIPLIER
    doubletime_multiplier: float = DEFAULT_DT_MULTIPLIER


@dataclass(frozen=True)
class WorkdayHours:
    """One worker's hours for one calendar day.

    ``computed_hours`` come from clock in/out (dispatch -> completion). ``claimed_hours`` is the
    technician's self-reported pay-form figure for that day; ``None`` when nothing was reported.
    """

    worker_id: str
    work_date: date
    computed_hours: float
    claimed_hours: float | None = None


@dataclass(frozen=True)
class PieceEarning:
    """A piece-rate job amount or a sales commission, in integer cents."""

    worker_id: str
    job_id: str
    amount_cents: int
    kind: str = "piece"  # "piece" | "commission"


@dataclass(frozen=True)
class PayPeriod:
    start: date
    end: date


@dataclass(frozen=True)
class PayrollData:
    """Everything the payroll engine needs for one pay period, assembled by the service."""

    period: PayPeriod
    workers: list[Worker]
    workdays: list[WorkdayHours]
    piece_earnings: list[PieceEarning] = field(default_factory=list)
    discrepancy_tolerance: float = HOURS_DISCREPANCY_TOLERANCE
    # Overtime jurisdiction — "BC" (default, the client's location) or "CA". Drives only the default
    # workweek anchor (BC = Sunday-Saturday; CA = the pay-period start weekday). The daily/weekly rates
    # are identical either way.
    jurisdiction: str = JURISDICTION_BC
    # The employer's explicit workweek anchor (0=Mon .. 6=Sun). None => derive from ``jurisdiction``:
    # BC -> Sunday(6); CA -> the pay-period start weekday (so a single 7-day period is one workweek).
    workweek_starts_on: int | None = None


# --------------------------------------------------------------------------------------------
# Result types
# --------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class WorkerPay:
    worker_id: str
    worker_name: str
    pay_class: str
    regular_hours: float
    overtime_hours: float
    doubletime_hours: float
    computed_hours: float
    claimed_hours: float | None
    hours_discrepancy: float  # claimed - computed (0.0 when nothing was claimed)
    needs_review: bool        # claimed hours diverge from the clock beyond tolerance
    gross_pay_cents: int
    reasoning: str


@dataclass(frozen=True)
class PayrollRun:
    period_start: date
    period_end: date
    worker_pays: list[WorkerPay]
    total_gross_cents: int
    flagged_count: int  # workers whose pay-form hours need a human adjustment review
    inputs_hash: str


# --------------------------------------------------------------------------------------------
# Engine
# --------------------------------------------------------------------------------------------
def compute_payroll(data: PayrollData) -> PayrollRun:
    days_by_worker: dict[str, list[WorkdayHours]] = defaultdict(list)
    for wd in data.workdays:
        days_by_worker[wd.worker_id].append(wd)

    pieces_by_worker: dict[str, list[PieceEarning]] = defaultdict(list)
    for pe in data.piece_earnings:
        pieces_by_worker[pe.worker_id].append(pe)

    if data.workweek_starts_on is not None:
        anchor = data.workweek_starts_on
    elif data.jurisdiction == JURISDICTION_BC:
        anchor = SUNDAY_WEEKDAY  # BC ESA overtime week = Sunday-Saturday
    else:
        anchor = data.period.start.weekday()  # CA / other: the pay-period start weekday

    worker_pays: list[WorkerPay] = []
    for worker in data.workers:
        days = days_by_worker.get(worker.id, [])
        computed_total = round(sum(d.computed_hours for d in days), 2)

        claimed_present = any(d.claimed_hours is not None for d in days)
        claimed_total = (
            round(sum(d.claimed_hours or 0.0 for d in days), 2) if claimed_present else None
        )
        discrepancy = (
            hours_discrepancy(claimed_total, computed_total) if claimed_total is not None else 0.0
        )
        needs_review = claimed_total is not None and abs(discrepancy) > data.discrepancy_tolerance

        if worker.pay_class == PAY_HOURLY:
            reg, ot, dt = _hourly_hours(days, anchor)
            gross = gross_pay_cents(
                reg,
                ot,
                dt,
                worker.hourly_rate,
                overtime_multiplier=worker.overtime_multiplier,
                doubletime_multiplier=worker.doubletime_multiplier,
            )
            reasoning = _hourly_reasoning(worker, reg, ot, dt, gross)
        else:
            reg = ot = dt = 0.0
            gross = sum(pe.amount_cents for pe in pieces_by_worker.get(worker.id, []))
            reasoning = _piece_reasoning(worker, pieces_by_worker.get(worker.id, []), gross)

        if needs_review:
            reasoning += (
                f" PAYROLL GAP: pay-form claims {claimed_total:.1f}h but clock in/out shows "
                f"{computed_total:.1f}h ({discrepancy:+.1f}h) — review before posting the adjustment."
            )

        worker_pays.append(
            WorkerPay(
                worker_id=worker.id,
                worker_name=worker.name,
                pay_class=worker.pay_class,
                regular_hours=round(reg, 2),
                overtime_hours=round(ot, 2),
                doubletime_hours=round(dt, 2),
                computed_hours=computed_total,
                claimed_hours=claimed_total,
                hours_discrepancy=discrepancy,
                needs_review=needs_review,
                gross_pay_cents=gross,
                reasoning=reasoning,
            )
        )

    # Flagged first (highest discrepancy), then by gross — the review queue ordering.
    worker_pays.sort(key=lambda wp: (not wp.needs_review, -abs(wp.hours_discrepancy), -wp.gross_pay_cents))

    return PayrollRun(
        period_start=data.period.start,
        period_end=data.period.end,
        worker_pays=worker_pays,
        total_gross_cents=sum(wp.gross_pay_cents for wp in worker_pays),
        flagged_count=sum(1 for wp in worker_pays if wp.needs_review),
        inputs_hash=_hash_inputs(data),
    )


def _hourly_hours(days: list[WorkdayHours], anchor_weekday: int) -> tuple[float, float, float]:
    """Apply daily then weekly overtime (BC ESA) across the worker's days, grouped by the employer's
    workweek (anchored on ``anchor_weekday``). Weekly OT counts only each day's first 8h (the daily
    ``regular`` bucket), so the >40h rule never double-counts daily OT and isn't mis-split for a
    non-Sunday week."""
    reg_total = ot_total = dt_total = 0.0
    by_week: dict[date, list[WorkdayHours]] = defaultdict(list)
    for d in days:
        by_week[_workweek_start(d.work_date, anchor_weekday)].append(d)

    for week_days in by_week.values():
        week_reg = 0.0
        for d in week_days:
            reg, ot, dt = daily_overtime_split(d.computed_hours)
            week_reg += reg
            ot_total += ot
            dt_total += dt
        reg_after, weekly_ot = apply_weekly_overtime(week_reg)
        reg_total += reg_after
        ot_total += weekly_ot
    return reg_total, ot_total, dt_total


def _hourly_reasoning(worker: Worker, reg: float, ot: float, dt: float, gross: int) -> str:
    parts = [f"{reg:.1f}h regular"]
    if ot:
        parts.append(f"{ot:.1f}h OT @ {worker.overtime_multiplier:g}x")
    if dt:
        parts.append(f"{dt:.1f}h double-time @ {worker.doubletime_multiplier:g}x")
    return (
        f"{worker.name} (hourly @ ${worker.hourly_rate:,.2f}/h): "
        + ", ".join(parts)
        + f" -> gross ${gross / 100:,.2f}."
    )


def _piece_reasoning(worker: Worker, pieces: list[PieceEarning], gross: int) -> str:
    label = "commission" if worker.pay_class == PAY_COMMISSION else "piece-rate"
    return (
        f"{worker.name} ({label}): {len(pieces)} job(s) -> gross ${gross / 100:,.2f} "
        f"(no hourly overtime for {label} workers)."
    )


def _hash_inputs(data: PayrollData) -> str:
    """Stable SHA-256 over the inputs that affect the result — for audit + idempotency."""
    payload = {
        "period": [data.period.start.isoformat(), data.period.end.isoformat()],
        "tolerance": data.discrepancy_tolerance,
        "jurisdiction": data.jurisdiction,
        "workweek_starts_on": data.workweek_starts_on,
        "workers": sorted((asdict(w) for w in data.workers), key=lambda r: r["id"]),
        "workdays": sorted(
            ({**asdict(d), "work_date": d.work_date.isoformat()} for d in data.workdays),
            key=lambda r: (r["worker_id"], r["work_date"]),
        ),
        "piece_earnings": sorted(
            (asdict(p) for p in data.piece_earnings), key=lambda r: (r["worker_id"], r["job_id"])
        ),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
