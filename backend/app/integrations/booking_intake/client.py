"""The booking-intake adapter boundary.

The Booking agent owns the *decision* brain, not the voice layer (ADR 0006). The voice/telephony
provider (Retell/Vapi/Twilio/SMS/web form) answers the live call and hands us a STRUCTURED intake;
this adapter is the read-only surface that yields those intakes plus the availability + economics the
deterministic engine needs. A config-driven factory returns the fixture-backed client (default) or
the live client (intakes drained from the signed-webhook event_queue; availability from ServiceTitan).
"""
from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from app.agents.booking.models import AvailabilitySlot, Intake, ServiceArea, TradeValue
from app.config import Settings, get_settings


@runtime_checkable
class BookingIntakeClient(Protocol):
    """Read-only surface the Booking agent needs to qualify, slot, and value inbound intakes."""

    async def get_intakes(self) -> list[Intake]: ...
    async def get_service_area(self) -> ServiceArea: ...
    async def get_availability(self) -> list[AvailabilitySlot]: ...
    async def get_trade_values(self) -> list[TradeValue]: ...


def get_booking_intake_client(
    *, as_of: datetime | None = None, settings: Settings | None = None
) -> BookingIntakeClient:
    settings = settings or get_settings()
    if settings.booking_intake_mode.lower() == "live":
        from app.integrations.booking_intake.live_client import LiveBookingIntakeClient

        return LiveBookingIntakeClient(settings)

    from app.integrations.booking_intake.fixture_client import FixtureBookingIntakeClient

    return FixtureBookingIntakeClient(as_of=as_of)
