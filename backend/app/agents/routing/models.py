"""Domain models for the Routing / Dispatch agent (dependency-free, stdlib only).

Locations are modeled as integer service-area **zone coordinates** `(x, y)` with Manhattan distance —
deterministic and hand-computable for tests. The live ServiceTitan adapter maps real lat/lon → zone
coords (or a drive-time matrix from a routing API). Times are minutes-of-day (e.g. 480 = 08:00).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class FieldTech:
    id: str
    name: str
    skills: list[str]          # trades/skills this tech can perform
    home_x: int
    home_y: int
    shift_start_min: int       # minutes-of-day
    shift_end_min: int
    # --- revenue signal (Summit dispatcher is comp'd on revenue; defaults keep existing
    # fixtures/tests valid). avg_ticket_cents = tech's average completed-job revenue; conversion_pct =
    # share of dispatched jobs the tech closes (0-100). Together they rank "who books the most $".
    avg_ticket_cents: int = 0
    conversion_pct: int = 0


# Priority levels. P1 = emergency (e.g. "no heat") -> dispatched first; P2 = same-day comfort;
# P3 = maintenance / flexible. Lower number = higher urgency (P1 < P2 < P3 sorts emergencies first).
P1, P2, P3 = 1, 2, 3
PRIORITY_LABELS = {P1: "P1", P2: "P2", P3: "P3"}


@dataclass(frozen=True)
class DispatchJob:
    id: str
    customer_name: str
    trade: str
    job_type: str
    x: int
    y: int
    duration_min: int
    priority: int              # higher = more urgent (sorted first) — legacy drive-time engine signal
    required_skill: str
    window_start_min: int      # earliest the tech may arrive
    window_end_min: int        # latest the tech may arrive
    status: str = "scheduled"
    # --- triage signals (defaults preserve every existing fixture/test). `severity` is the explicit
    # dispatcher label when ST/the call-taker provides one ("emergency"/"no_heat"/"comfort"/
    # "maintenance"); when blank the engine derives P1/P2/P3 from job_type keywords.
    severity: str = ""
    # The day this job sits on for the 3-day call board (ISO date string). Blank => the run's as_of day.
    scheduled_date: str = ""
    revenue_cents: int = 0     # estimated/booked job revenue (for revenue-rank context)


@dataclass(frozen=True)
class DispatchData:
    as_of: date
    jobs: list[DispatchJob]
    technicians: list[FieldTech] = field(default_factory=list)
