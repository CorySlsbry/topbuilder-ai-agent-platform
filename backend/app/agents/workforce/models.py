"""Domain models for the Workforce agent.

These are FSM-agnostic, dependency-free dataclasses (stdlib only) so the analytics engine and its
tests stay pure. The ServiceTitan adapter populates them; the analytics engine consumes them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class Technician:
    id: str
    name: str
    trade: str
    contracted_weekly_hours: float
    hourly_cost: float          # fully-loaded labor cost, $/hr
    overtime_multiplier: float  # e.g. 1.5 for time-and-a-half
    active: bool = True


@dataclass(frozen=True)
class TradeEconomics:
    trade: str
    billable_rate: float        # $/hr billed to the customer
    availability_factor: float  # fraction of contracted hours actually billable (PTO/admin/travel)


@dataclass(frozen=True)
class Appointment:
    id: str
    job_id: str
    trade: str
    appt_date: date
    scheduled_hours: float
    job_type: str
    technician_id: str | None = None  # None => unassigned (still real demand)
    status: str = "scheduled"


@dataclass(frozen=True)
class Timesheet:
    technician_id: str
    work_date: date
    regular_hours: float
    overtime_hours: float


@dataclass(frozen=True)
class JobDurationStat:
    job_type: str
    trade: str
    mean_hours: float
    stddev_hours: float
    sample_size: int
    completion_rate: float  # 0..1 historical first-visit completion


@dataclass(frozen=True)
class DemandSignal:
    trade: str
    week_offset: int        # 0 = current week, 1 = next week, ...
    demand_index: float     # 1.0 = baseline booked demand; >1 expects additional inbound


@dataclass(frozen=True)
class WorkforceData:
    """Everything the Workforce agent needs for one analysis, assembled by the service."""

    as_of: date
    horizon_days: int
    technicians: list[Technician]
    appointments: list[Appointment]
    timesheets: list[Timesheet]
    job_durations: list[JobDurationStat]
    demand_signals: list[DemandSignal]
    trade_economics: list[TradeEconomics] = field(default_factory=list)
