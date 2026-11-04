"""Assemble a BookingData bundle from a BookingIntakeClient (DB-free, so it's easy to preview)."""
from __future__ import annotations

from datetime import datetime

from app.agents.booking.models import BookingData
from app.integrations.booking_intake.client import BookingIntakeClient


async def assemble_booking_data(client: BookingIntakeClient, *, as_of: datetime) -> BookingData:
    return BookingData(
        as_of=as_of,
        intakes=await client.get_intakes(),
        service_area=await client.get_service_area(),
        availability=await client.get_availability(),
        trade_values=await client.get_trade_values(),
    )
