"""Deterministic Booking engine: qualify -> slot -> value (ADR 0006).

No LLM, no randomness. Decides which inbound intakes are real, bookable leads, the soonest
appropriate slot, and the revenue recovered. The reasoning node narrates; it never decides.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime

from app.agents.booking.models import AvailabilitySlot, BookingData, Intake, ServiceArea, TradeValue

SLOT_CONFIDENCE = 0.9
QUALIFYING_INTENTS = {"service_request", "existing_customer"}
HIGH_INTENT_URGENCY = {"emergency", "same_day"}


# --------------------------------------------------------------------------------------------
# Result types
# --------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class ProposedBooking:
    intake_id: str
    caller_name: str | None
    trade: str
    job_type: str | None
    urgency: str
    after_hours: bool
    proposed_date: date
    estimated_value_cents: int
    confidence: float
    status: str  # 'proposed' (human-in-the-loop confirms the ServiceTitan write)
    reasoning: str


@dataclass(frozen=True)
class UnbookedIntake:
    intake_id: str
    trade: str
    reason: str


@dataclass(frozen=True)
class BookingTotals:
    intakes_received: int
    qualified: int
    proposed_bookings: int
    after_hours_captured: int
    recovered_revenue_cents: int


@dataclass(frozen=True)
class BookingAnalysis:
    as_of: datetime
    proposed_bookings: list[ProposedBooking]
    unbooked: list[UnbookedIntake]
    totals: BookingTotals
    inputs_hash: str


# --------------------------------------------------------------------------------------------
# Pure primitives
# --------------------------------------------------------------------------------------------
def is_qualified(intake: Intake, area: ServiceArea) -> tuple[bool, str]:
    if intake.intent not in QUALIFYING_INTENTS:
        return False, f"unqualified intent: {intake.intent}"
    if intake.trade_requested not in area.trades:
        return False, f"trade not served: {intake.trade_requested}"
    if intake.zip_code is not None and intake.zip_code not in area.zip_codes:
        return False, "out of service area"
    return True, "qualified"


def qualification_score(intake: Intake, area: ServiceArea) -> float:
    score = 0.0
    if intake.intent in QUALIFYING_INTENTS:
        score += 0.4
    if intake.trade_requested in area.trades:
        score += 0.2
    if intake.zip_code is None:
        score += 0.1
    elif intake.zip_code in area.zip_codes:
        score += 0.2
    score += 0.2 if intake.urgency in HIGH_INTENT_URGENCY else 0.1
    return round(min(1.0, score), 3)


def recommend_slot(
    trade: str, availability: list[AvailabilitySlot], as_of_date: date
) -> AvailabilitySlot | None:
    candidates = [
        s for s in availability if s.trade == trade and s.open_slots > 0 and s.slot_date >= as_of_date
    ]
    return min(candidates, key=lambda s: s.slot_date) if candidates else None


def capture_value_cents(trade: str, trade_values: list[TradeValue]) -> int:
    for tv in trade_values:
        if tv.trade == trade:
            return round(tv.avg_job_value * 100)
    return 0


def _booking_confidence(qualification: float) -> float:
    return round(qualification * SLOT_CONFIDENCE, 3)


# --------------------------------------------------------------------------------------------
# Engine
# --------------------------------------------------------------------------------------------
def analyze(data: BookingData) -> BookingAnalysis:
    as_of_date = data.as_of.date()
    proposed: list[ProposedBooking] = []
    unbooked: list[UnbookedIntake] = []
    qualified_count = 0

    for intake in data.intakes:
        ok, reason = is_qualified(intake, data.service_area)
        if not ok:
            unbooked.append(UnbookedIntake(intake.id, intake.trade_requested, reason))
            continue
        qualified_count += 1
        slot = recommend_slot(intake.trade_requested, data.availability, as_of_date)
        if slot is None:
            unbooked.append(UnbookedIntake(intake.id, intake.trade_requested, "no availability"))
            continue
        value = capture_value_cents(intake.trade_requested, data.trade_values)
        qscore = qualification_score(intake, data.service_area)
        proposed.append(
            ProposedBooking(
                intake_id=intake.id,
                caller_name=intake.caller_name,
                trade=intake.trade_requested,
                job_type=intake.job_type,
                urgency=intake.urgency,
                after_hours=intake.after_hours,
                proposed_date=slot.slot_date,
                estimated_value_cents=value,
                confidence=_booking_confidence(qscore),
                status="proposed",
                reasoning=(
                    f"{intake.caller_name or 'Caller'} ({intake.channel}, "
                    f"{'after-hours' if intake.after_hours else 'business hours'}): {intake.urgency} "
                    f"{intake.trade_requested} request, qualified (score {qscore:.2f}); soonest slot "
                    f"{slot.slot_date.isoformat()}. Est. value ~${value / 100:,.0f} recovered."
                ),
            )
        )

    proposed.sort(key=lambda b: b.estimated_value_cents, reverse=True)
    totals = BookingTotals(
        intakes_received=len(data.intakes),
        qualified=qualified_count,
        proposed_bookings=len(proposed),
        after_hours_captured=sum(1 for b in proposed if b.after_hours),
        recovered_revenue_cents=sum(b.estimated_value_cents for b in proposed),
    )
    return BookingAnalysis(
        as_of=data.as_of,
        proposed_bookings=proposed,
        unbooked=unbooked,
        totals=totals,
        inputs_hash=_hash_inputs(data),
    )


def _hash_inputs(data: BookingData) -> str:
    payload = {
        "as_of": data.as_of.isoformat(),
        "intakes": sorted(
            ({**asdict(i), "received_at": i.received_at.isoformat()} for i in data.intakes),
            key=lambda r: r["id"],
        ),
        "service_area": asdict(data.service_area),
        "availability": sorted(
            ({**asdict(s), "slot_date": s.slot_date.isoformat()} for s in data.availability),
            key=lambda r: (r["trade"], r["slot_date"]),
        ),
        "trade_values": sorted((asdict(t) for t in data.trade_values), key=lambda r: r["trade"]),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
