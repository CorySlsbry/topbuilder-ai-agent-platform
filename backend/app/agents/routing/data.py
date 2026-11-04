"""Assemble a DispatchData bundle from a DispatchClient (DB-free)."""
from __future__ import annotations

from datetime import date

from app.agents.routing.models import DispatchData
from app.integrations.dispatch.client import DispatchClient


async def assemble_dispatch_data(client: DispatchClient, *, as_of: date) -> DispatchData:
    return DispatchData(
        as_of=as_of,
        jobs=await client.get_jobs(as_of),
        technicians=await client.get_technicians(),
    )


async def assemble_triage_data(client: DispatchClient, *, as_of: date) -> DispatchData:
    """The triage feed: the unassigned-job queue + technicians carrying revenue signals (avg ticket /
    conversion). Falls back to the drive-time feed if the client predates the triage methods."""
    get_jobs = getattr(client, "get_triage_jobs", client.get_jobs)
    get_techs = getattr(client, "get_triage_technicians", client.get_technicians)
    return DispatchData(
        as_of=as_of,
        jobs=await get_jobs(as_of),
        technicians=await get_techs(),
    )
