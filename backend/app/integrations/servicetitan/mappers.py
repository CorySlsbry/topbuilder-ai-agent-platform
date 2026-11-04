"""Pure mappers from ServiceTitan API payloads to domain models.

These encode the transformations (ISO datetime parsing, duration -> hours) and are unit-tested. Exact
field names should be verified against a live tenant (ADR 0005), but the logic is correct.
"""
from __future__ import annotations

from datetime import date, datetime, time

from app.agents.workforce.models import Appointment, Timesheet
from app.agents.workforce.payroll import (
    PAY_COMMISSION,
    PAY_HOURLY,
    PAY_PIECE_RATE,
    PieceEarning,
    WorkdayHours,
    Worker,
)


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def map_appointment(row: dict) -> Appointment:
    """ST appointment: {id, jobId, start, end, technicianId, jobType, trade, status}."""
    start = _parse_dt(row["start"])
    end = _parse_dt(row["end"])
    hours = max(0.0, (end - start).total_seconds() / 3600.0)
    tech = row.get("technicianId")
    return Appointment(
        id=str(row["id"]),
        job_id=str(row.get("jobId", "")),
        trade=str(row.get("trade", "unknown")),
        appt_date=start.date(),
        scheduled_hours=round(hours, 2),
        job_type=str(row.get("jobType", "unknown")),
        technician_id=str(tech) if tech is not None else None,
        status=str(row.get("status", "scheduled")),
    )


def map_timesheet(row: dict) -> Timesheet:
    """ST timesheet/gross-pay item: {technicianId, date, regularHours, overtimeHours}."""
    return Timesheet(
        technician_id=str(row["technicianId"]),
        work_date=date.fromisoformat(str(row["date"])[:10]),
        regular_hours=float(row.get("regularHours", 0) or 0),
        overtime_hours=float(row.get("overtimeHours", 0) or 0),
    )


# --------------------------------------------------------------------------------------------
# Payroll mappers (ServiceTitan payroll/job-actions -> the deterministic payroll engine inputs).
#
# Pure, dependency-free, and unit-tested. They translate the client's real pay structure (Alex
# discovery, 2026-06-16): a worker's ServiceTitan ROLE -> the payroll pay class; dispatch/completion
# timestamps -> the COMPUTED clock hours; the technician's pay-form figure -> the CLAIMED hours; and
# piece/commission job amounts -> PieceEarning cents. Exact ST field names are verified against a live
# tenant (ADR 0005); the transformation logic is what is tested here.
# --------------------------------------------------------------------------------------------

# ServiceTitan technician role / pay-type -> our payroll pay class. SERVICE techs are hourly (CA OT),
# INSTALL techs are piece-rate ("paid whatever they quote"), SALES/comfort advisors are commission-only.
_ROLE_TO_PAY_CLASS: dict[str, str] = {
    "service": PAY_HOURLY,
    "hourly": PAY_HOURLY,
    "install": PAY_PIECE_RATE,
    "installer": PAY_PIECE_RATE,
    "piece_rate": PAY_PIECE_RATE,
    "sales": PAY_COMMISSION,
    "comfort_advisor": PAY_COMMISSION,
    "commission": PAY_COMMISSION,
}


def pay_class_for_role(role: str) -> str:
    """Map a ServiceTitan role/pay-type to a payroll pay class. Unknown roles fail safe to hourly
    (the only class that can accrue overtime), so an unmapped worker is never silently under-paid."""
    return _ROLE_TO_PAY_CLASS.get(str(role or "").strip().lower(), PAY_HOURLY)


def map_worker(row: dict) -> Worker:
    """ST technician/payroll-setup row -> Worker.

    Expected shape: {id, name, role, hourly_rate?}. ``hourly_rate`` is distinct from the workforce
    model's fully-loaded ``hourly_cost`` — this is the pay rate, only meaningful for hourly workers.
    """
    return Worker(
        id=str(row["id"]),
        name=str(row.get("name", row["id"])),
        pay_class=pay_class_for_role(row.get("role", "")),
        hourly_rate=float(row.get("hourly_rate", 0.0) or 0.0),
    )


def _clock_to_dt(value: str, work_date: date) -> datetime:
    """Parse a job-action clock value into a datetime on ``work_date``.

    Accepts either a full ISO timestamp (live ST shape, e.g. ``2026-06-01T08:00:00Z``) or a
    time-of-day string (``08:00:00`` / ``08:00``), which is combined with the period-relative date.
    """
    if "T" in value or len(value) > 8:
        return _parse_dt(value)
    return datetime.combine(work_date, time.fromisoformat(value))


def _hours_between(dispatched_at: str, completed_at: str, work_date: date) -> float:
    """Hours from a dispatch (clock-in) to a job-completion (clock-out)."""
    start = _clock_to_dt(dispatched_at, work_date)
    end = _clock_to_dt(completed_at, work_date)
    return round(max(0.0, (end - start).total_seconds() / 3600.0), 2)


def map_workday(row: dict, *, work_date: date) -> WorkdayHours:
    """ST job-action row -> WorkdayHours for ONE worker-day.

    ``computed_hours`` are derived from the dispatch -> completion clock (clock in on dispatch, clock
    out on completion — Alex's "gray area past shift end is overtime"). ``claimed_hours`` is the
    technician's self-reported pay-form figure for that day when present (``None`` otherwise) — the
    pairing the payroll gap is built on. Pay is always from the clock, never the unverified claim.
    """
    claimed = row.get("claimed_hours")
    return WorkdayHours(
        worker_id=str(row["worker_id"]),
        work_date=work_date,
        computed_hours=_hours_between(row["dispatched_at"], row["completed_at"], work_date),
        claimed_hours=float(claimed) if claimed is not None else None,
    )


def map_piece_earning(row: dict) -> PieceEarning:
    """ST piece-rate job amount or sales commission -> PieceEarning (integer cents, ADR 0003)."""
    return PieceEarning(
        worker_id=str(row["worker_id"]),
        job_id=str(row.get("job_id", "")),
        amount_cents=int(row["amount_cents"]),
        kind=str(row.get("kind", "piece")),
    )
