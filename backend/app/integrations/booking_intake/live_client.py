"""Live booking-intake client — skeleton (ADR 0006). Selected by BOOKING_INTAKE_MODE=live.

The booking brain is ours; the voice layer is bought. In production the intakes are not polled from a
third-party API — they are *pushed*: the voice/telephony provider POSTs a structured intake to our
signature-verified webhook (`routes_webhooks`), which lands it on the per-tenant `event_queue`
(ADR 0005 infra, already built). This client drains that queue; availability is derived from the
ServiceTitan adapter (the same technicians/appointments the Workforce agent reads); the service area
comes from tenant configuration / ServiceTitan business units. Per-field mapping is intentionally left
to verify against a real provider + tenant — mirrors the ServiceTitan/inventory live-client pattern.
"""
from __future__ import annotations

from app.agents.booking.models import AvailabilitySlot, Intake, ServiceArea, TradeValue
from app.config import Settings


class LiveBookingIntakeClient:
    def __init__(self, settings: Settings) -> None:
        self._s = settings

    async def get_intakes(self) -> list[Intake]:
        # Drain structured intakes from the signed-webhook event_queue (voice provider -> webhook).
        # Each event payload (caller, phone, zip, trade, intent, urgency, transcript) -> Intake.
        raise NotImplementedError(
            "Drain booking intakes from event_queue (voice provider -> signed webhook). "
            "See app/api/routes_webhooks.py + ADR 0006."
        )

    async def get_service_area(self) -> ServiceArea:
        # From tenant config / ServiceTitan business-unit service areas + offered trades.
        raise NotImplementedError("Map tenant service area (ServiceTitan business units) -> ServiceArea.")

    async def get_availability(self) -> list[AvailabilitySlot]:
        # Derive open slots per trade/day from the ServiceTitan adapter (technicians + appointments +
        # capacity), reusing app/integrations/servicetitan/client.get_servicetitan_client.
        raise NotImplementedError("Derive AvailabilitySlot[] from the ServiceTitan capacity model.")

    async def get_trade_values(self) -> list[TradeValue]:
        # Average booked-job revenue per trade — from ServiceTitan invoiced-job history.
        raise NotImplementedError("Map ServiceTitan invoiced-job history -> TradeValue (avg job value).")
