"""Fixture-backed booking-intake client.

Loads a realistic batch of inbound intakes and materializes their `received_at` relative to `as_of`
(stored as `hours_ago`) and availability `slot_date`s relative to `as_of` (stored as `day_offset`),
so the demo is always forward-looking with zero credentials. The qualification/value of an intake is
NOT time-dependent (`after_hours` is an explicit field), so results are stable whenever you run it.
"""
from __future__ import annotations

import json
import pathlib
from datetime import datetime, timedelta

from app.agents.booking.models import AvailabilitySlot, Intake, ServiceArea, TradeValue

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"


def _load(name: str):
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


class FixtureBookingIntakeClient:
    def __init__(self, as_of: datetime | None = None) -> None:
        self.as_of = as_of or datetime.now()
        self._intakes = _load("intakes.json")
        self._service_area = _load("service_area.json")
        self._availability = _load("availability.json")
        self._trade_values = _load("trade_values.json")

    async def get_intakes(self) -> list[Intake]:
        out: list[Intake] = []
        for row in self._intakes:
            received_at = self.as_of - timedelta(hours=float(row.get("hours_ago", 0)))
            out.append(
                Intake(
                    id=row["id"],
                    received_at=received_at,
                    after_hours=bool(row["after_hours"]),
                    channel=row["channel"],
                    trade_requested=row["trade_requested"],
                    intent=row["intent"],
                    urgency=row["urgency"],
                    caller_name=row.get("caller_name"),
                    phone=row.get("phone"),
                    zip_code=row.get("zip_code"),
                    job_type=row.get("job_type"),
                    transcript=row.get("transcript"),
                )
            )
        return out

    async def get_service_area(self) -> ServiceArea:
        return ServiceArea(
            zip_codes=list(self._service_area["zip_codes"]),
            trades=list(self._service_area["trades"]),
        )

    async def get_availability(self) -> list[AvailabilitySlot]:
        return [
            AvailabilitySlot(
                trade=row["trade"],
                slot_date=(self.as_of + timedelta(days=int(row["day_offset"]))).date(),
                open_slots=int(row["open_slots"]),
            )
            for row in self._availability
        ]

    async def get_trade_values(self) -> list[TradeValue]:
        return [
            TradeValue(trade=row["trade"], avg_job_value=float(row["avg_job_value"]))
            for row in self._trade_values
        ]
