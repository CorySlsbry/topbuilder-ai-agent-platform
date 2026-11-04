"""Live ServiceTitan dispatch client — skeleton (ADR 0005). Selected by DISPATCH_MODE=servicetitan.

Reuses ServiceTitan OAuth. Jobs come from the Jobs/Appointments API; technician home bases + skills
from the Technicians API; real lat/lon is projected to zone coords (or replaced by a drive-time matrix
from a routing provider). Left to verify against a real tenant — mirrors the other live-client skeletons.
"""
from __future__ import annotations

from datetime import date

from app.agents.routing.models import DispatchJob, FieldTech
from app.config import Settings


class ServiceTitanDispatchClient:
    def __init__(self, settings: Settings) -> None:
        self._s = settings

    async def get_jobs(self, as_of: date) -> list[DispatchJob]:
        # GET /jpm/v2/tenant/{tenant}/appointments (+ jobs) for `as_of` -> DispatchJob (project lat/lon).
        raise NotImplementedError("Map ServiceTitan appointments -> DispatchJob (lat/lon -> zone coords).")

    async def get_technicians(self) -> list[FieldTech]:
        # GET /settings/v2/tenant/{tenant}/technicians -> FieldTech (home base + skills + shift).
        raise NotImplementedError("Map ServiceTitan technicians -> FieldTech (home base + skills + shift).")

    async def get_triage_jobs(self, as_of: date) -> list[DispatchJob]:
        # GET jpm appointments/jobs for the 3-day window -> DispatchJob with `severity` (from job
        # type/priority), `scheduled_date`, and `revenue_cents` (estimate/booked value). Fail closed.
        raise NotImplementedError(
            "Map ServiceTitan jobs -> triage DispatchJob (severity, scheduled_date, revenue_cents)."
        )

    async def get_triage_technicians(self) -> list[FieldTech]:
        # GET technicians + the Dispatch-Pro revenue/conversion table -> FieldTech with
        # avg_ticket_cents + conversion_pct (the revenue signals the dispatcher is comp'd on). Fail closed.
        raise NotImplementedError(
            "Map ServiceTitan technicians + Dispatch-Pro revenue -> FieldTech (avg_ticket, conversion)."
        )
