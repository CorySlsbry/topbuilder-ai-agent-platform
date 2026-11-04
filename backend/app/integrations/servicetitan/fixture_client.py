"""Fixture-backed ServiceTitan client.

Loads realistic JSON fixtures and materializes appointment/timesheet dates *relative to `as_of`*
(stored as day offsets) so the demo is always forward-looking. This is the working data path for
the slice — zero credentials required.
"""
from __future__ import annotations

import json
import pathlib
from datetime import date, timedelta

from app.agents.workforce.models import (
    Appointment,
    DemandSignal,
    JobDurationStat,
    Technician,
    Timesheet,
    TradeEconomics,
)

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"


def _load(name: str) -> list[dict]:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


class FixtureServiceTitanClient:
    def __init__(self, as_of: date | None = None) -> None:
        self.as_of = as_of or date.today()
        self._technicians = _load("technicians.json")
        self._trade_economics = _load("trade_economics.json")
        self._appointments = _load("appointments.json")
        self._timesheets = _load("timesheets.json")
        self._job_durations = _load("job_durations.json")
        self._demand = _load("demand_index.json")

    async def get_technicians(self) -> list[Technician]:
        return [Technician(**row) for row in self._technicians]

    async def get_trade_economics(self) -> list[TradeEconomics]:
        return [TradeEconomics(**row) for row in self._trade_economics]

    async def get_appointments(self, start: date, end: date) -> list[Appointment]:
        out: list[Appointment] = []
        for row in self._appointments:
            appt_date = self.as_of + timedelta(days=int(row["day_offset"]))
            if start <= appt_date < end:
                out.append(
                    Appointment(
                        id=row["id"],
                        job_id=row["job_id"],
                        trade=row["trade"],
                        appt_date=appt_date,
                        scheduled_hours=float(row["scheduled_hours"]),
                        job_type=row["job_type"],
                        technician_id=row.get("technician_id"),
                        status=row.get("status", "scheduled"),
                    )
                )
        return out

    async def get_timesheets(self, start: date, end: date) -> list[Timesheet]:
        out: list[Timesheet] = []
        for row in self._timesheets:
            work_date = self.as_of + timedelta(days=int(row["day_offset"]))
            if start <= work_date < end:
                out.append(
                    Timesheet(
                        technician_id=row["technician_id"],
                        work_date=work_date,
                        regular_hours=float(row["regular_hours"]),
                        overtime_hours=float(row["overtime_hours"]),
                    )
                )
        return out

    async def get_job_durations(self) -> list[JobDurationStat]:
        return [JobDurationStat(**row) for row in self._job_durations]

    async def get_demand_signals(self) -> list[DemandSignal]:
        return [DemandSignal(**row) for row in self._demand]
