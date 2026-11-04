"""Assemble a WorkforceData bundle from a ServiceTitanClient (DB-free, so it's easy to preview)."""
from __future__ import annotations

from datetime import date, timedelta

from app.agents.workforce.models import WorkforceData
from app.integrations.servicetitan.client import ServiceTitanClient

HISTORY_DAYS = 14


async def assemble_workforce_data(
    client: ServiceTitanClient, *, as_of: date, horizon_days: int
) -> WorkforceData:
    start = as_of
    end = as_of + timedelta(days=horizon_days)
    history_start = as_of - timedelta(days=HISTORY_DAYS)

    return WorkforceData(
        as_of=as_of,
        horizon_days=horizon_days,
        technicians=await client.get_technicians(),
        appointments=await client.get_appointments(start, end),
        timesheets=await client.get_timesheets(history_start, as_of),
        job_durations=await client.get_job_durations(),
        demand_signals=await client.get_demand_signals(),
        trade_economics=await client.get_trade_economics(),
    )
