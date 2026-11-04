"""The ServiceTitan adapter boundary.

Agents depend only on the `ServiceTitanClient` protocol (read-only by design — ADR 0005). A
config-driven factory returns the fixture-backed client (default) or the live OAuth2 client.
"""
from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from app.agents.workforce.models import (
    Appointment,
    DemandSignal,
    JobDurationStat,
    Technician,
    Timesheet,
    TradeEconomics,
)
from app.config import Settings, get_settings


@runtime_checkable
class ServiceTitanClient(Protocol):
    """Read-only surface the Workforce agent needs from a field-service platform."""

    async def get_technicians(self) -> list[Technician]: ...
    async def get_trade_economics(self) -> list[TradeEconomics]: ...
    async def get_appointments(self, start: date, end: date) -> list[Appointment]: ...
    async def get_timesheets(self, start: date, end: date) -> list[Timesheet]: ...
    async def get_job_durations(self) -> list[JobDurationStat]: ...
    async def get_demand_signals(self) -> list[DemandSignal]: ...


def get_servicetitan_client(
    *, as_of: date | None = None, settings: Settings | None = None
) -> ServiceTitanClient:
    settings = settings or get_settings()
    if settings.servicetitan_mode.lower() == "live":
        from app.integrations.servicetitan.live_client import LiveServiceTitanClient

        return LiveServiceTitanClient(settings)

    from app.integrations.servicetitan.fixture_client import FixtureServiceTitanClient

    return FixtureServiceTitanClient(as_of=as_of)
