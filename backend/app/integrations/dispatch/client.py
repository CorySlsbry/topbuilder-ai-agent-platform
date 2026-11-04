"""The dispatch adapter boundary for the Routing agent (read-only; ADR 0005)."""
from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from app.agents.routing.models import DispatchJob, FieldTech
from app.config import Settings, get_settings


@runtime_checkable
class DispatchClient(Protocol):
    async def get_jobs(self, as_of: date) -> list[DispatchJob]: ...
    async def get_technicians(self) -> list[FieldTech]: ...
    # Triage source: the unassigned-job queue + techs with revenue signals (avg ticket / conversion).
    # Defaults to the same job/tech feed; the fixture client overrides with a Summit-shaped set.
    async def get_triage_jobs(self, as_of: date) -> list[DispatchJob]: ...
    async def get_triage_technicians(self) -> list[FieldTech]: ...


def get_dispatch_client(
    *, as_of: date | None = None, settings: Settings | None = None
) -> DispatchClient:
    settings = settings or get_settings()
    if settings.dispatch_mode.lower() == "servicetitan":
        from app.integrations.dispatch.servicetitan_dispatch_client import ServiceTitanDispatchClient

        return ServiceTitanDispatchClient(settings)

    from app.integrations.dispatch.fixture_client import FixtureDispatchClient

    return FixtureDispatchClient()
