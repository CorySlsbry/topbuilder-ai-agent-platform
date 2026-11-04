"""API-facing schemas (spec-shaped) + mapper for the 24/7 Booking agent.

Every dollar figure is derived from the deterministic engine's *cents* (ADR 0003); this layer only
formats and rolls up. The headline metric — `after_hours_recovered_usd` — is the revenue from jobs
booked off after-hours intakes that would otherwise have been missed calls.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.agents.booking.analytics import BookingAnalysis


def _usd(cents: int) -> float:
    return round(cents / 100, 2)


class ProposedBookingOut(BaseModel):
    intake_id: str
    caller_name: str | None
    trade: str
    job_type: str | None
    urgency: str
    after_hours: bool
    proposed_date: date
    estimated_value_usd: float
    confidence: float
    status: str  # 'proposed' — writing it back to ServiceTitan is human-in-the-loop (ADR 0006)
    reasoning: str


class UnbookedIntakeOut(BaseModel):
    intake_id: str
    trade: str
    reason: str


class BookingTotals(BaseModel):
    intakes_received: int
    qualified: int
    proposed_bookings: int
    screened_out: int
    after_hours_captured: int
    recovered_revenue_usd: float
    after_hours_recovered_usd: float


class BookingRunResult(BaseModel):
    run_id: uuid.UUID | None = None
    agent: str = "booking"
    source_system: str = "ServiceTitan"  # the tenant's field-service system of record (fsm_provider)
    analysis_timestamp: datetime
    as_of: datetime
    proposed_bookings: list[ProposedBookingOut]
    unbooked: list[UnbookedIntakeOut]
    totals: BookingTotals
    reasoning_logs: str
    inputs_hash: str


def build_result(
    analysis: BookingAnalysis,
    *,
    narrative: str,
    analysis_timestamp: datetime,
    run_id: uuid.UUID | None = None,
    source_system: str = "ServiceTitan",
) -> BookingRunResult:
    proposed = [
        ProposedBookingOut(
            intake_id=b.intake_id,
            caller_name=b.caller_name,
            trade=b.trade,
            job_type=b.job_type,
            urgency=b.urgency,
            after_hours=b.after_hours,
            proposed_date=b.proposed_date,
            estimated_value_usd=_usd(b.estimated_value_cents),
            confidence=b.confidence,
            status=b.status,
            reasoning=b.reasoning,
        )
        for b in analysis.proposed_bookings
    ]
    unbooked = [
        UnbookedIntakeOut(intake_id=u.intake_id, trade=u.trade, reason=u.reason)
        for u in analysis.unbooked
    ]
    after_hours_recovered_cents = sum(
        b.estimated_value_cents for b in analysis.proposed_bookings if b.after_hours
    )
    t = analysis.totals
    totals = BookingTotals(
        intakes_received=t.intakes_received,
        qualified=t.qualified,
        proposed_bookings=t.proposed_bookings,
        screened_out=len(unbooked),
        after_hours_captured=t.after_hours_captured,
        recovered_revenue_usd=_usd(t.recovered_revenue_cents),
        after_hours_recovered_usd=_usd(after_hours_recovered_cents),
    )
    return BookingRunResult(
        run_id=run_id,
        source_system=source_system,
        analysis_timestamp=analysis_timestamp,
        as_of=analysis.as_of,
        proposed_bookings=proposed,
        unbooked=unbooked,
        totals=totals,
        reasoning_logs=narrative,
        inputs_hash=analysis.inputs_hash,
    )
