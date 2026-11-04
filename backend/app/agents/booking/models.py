"""Domain models for the 24/7 Booking agent (dependency-free, stdlib only).

The voice/telephony layer is external (ADR 0006); these model the *structured intake* it (or an
SMS/web form) hands us, plus the availability + economics the booking engine needs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass(frozen=True)
class Intake:
    id: str
    received_at: datetime
    after_hours: bool
    channel: str  # phone | sms | web
    trade_requested: str  # hvac | plumbing | electrical | ... | unknown
    intent: str  # service_request | existing_customer | spam | wrong_number | sales
    urgency: str  # emergency | same_day | routine
    caller_name: str | None = None
    phone: str | None = None
    zip_code: str | None = None
    job_type: str | None = None
    transcript: str | None = None


@dataclass(frozen=True)
class ServiceArea:
    zip_codes: list[str]
    trades: list[str]


@dataclass(frozen=True)
class AvailabilitySlot:
    trade: str
    slot_date: date
    open_slots: int


@dataclass(frozen=True)
class TradeValue:
    trade: str
    avg_job_value: float  # expected revenue of a booked job in this trade


@dataclass(frozen=True)
class BookingData:
    as_of: datetime
    intakes: list[Intake]
    service_area: ServiceArea
    availability: list[AvailabilitySlot]
    trade_values: list[TradeValue] = field(default_factory=list)
