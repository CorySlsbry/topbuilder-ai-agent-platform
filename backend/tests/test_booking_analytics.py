"""Unit + property tests for the deterministic Booking engine (qualify -> slot -> value)."""
from __future__ import annotations

from datetime import date, datetime

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.agents.booking import analytics as a
from app.agents.booking.models import (
    AvailabilitySlot,
    BookingData,
    Intake,
    ServiceArea,
    TradeValue,
)

AS_OF = datetime(2026, 6, 6, 19, 0)  # Saturday 7pm — after hours
AREA = ServiceArea(zip_codes=["85001", "85002"], trades=["hvac", "plumbing", "electrical"])


class TestPrimitives:
    def test_qualified_clean_lead(self) -> None:
        intake = Intake("x", AS_OF, True, "phone", "hvac", "service_request", "emergency", zip_code="85001")
        ok, _ = a.is_qualified(intake, AREA)
        assert ok is True

    @pytest.mark.parametrize("intent", ["spam", "wrong_number", "sales"])
    def test_unqualified_intent(self, intent: str) -> None:
        intake = Intake("x", AS_OF, True, "phone", "hvac", intent, "routine", zip_code="85001")
        ok, reason = a.is_qualified(intake, AREA)
        assert ok is False and intent.split("_")[0] in reason.lower()

    def test_unqualified_out_of_area(self) -> None:
        intake = Intake("x", AS_OF, True, "phone", "hvac", "service_request", "routine", zip_code="99999")
        ok, reason = a.is_qualified(intake, AREA)
        assert ok is False and "area" in reason.lower()

    @pytest.mark.parametrize(
        "urgency, zip_code, expected",
        [("emergency", "85001", 1.0), ("routine", "85001", 0.9), ("routine", None, 0.8)],
    )
    def test_qualification_score(self, urgency: str, zip_code: str | None, expected: float) -> None:
        intake = Intake("x", AS_OF, True, "phone", "hvac", "service_request", urgency, zip_code=zip_code)
        assert a.qualification_score(intake, AREA) == pytest.approx(expected)

    def test_recommend_slot_returns_earliest(self) -> None:
        avail = [
            AvailabilitySlot("hvac", date(2026, 6, 7), 3),
            AvailabilitySlot("hvac", date(2026, 6, 6), 2),
            AvailabilitySlot("hvac", date(2026, 6, 8), 0),  # full — ignored
        ]
        slot = a.recommend_slot("hvac", avail, date(2026, 6, 6))
        assert slot is not None and slot.slot_date == date(2026, 6, 6)

    def test_recommend_slot_none_when_full(self) -> None:
        assert a.recommend_slot("hvac", [AvailabilitySlot("hvac", date(2026, 6, 6), 0)], date(2026, 6, 6)) is None


def _scenario() -> BookingData:
    intakes = [
        Intake("I1", AS_OF, True, "phone", "hvac", "service_request", "emergency", caller_name="Jane", zip_code="85001", job_type="ac_repair"),
        Intake("I2", AS_OF, True, "phone", "plumbing", "service_request", "routine", caller_name="Bob", zip_code="85002"),
        Intake("I3", AS_OF, True, "phone", "unknown", "spam", "routine"),
        Intake("I4", AS_OF, True, "phone", "hvac", "service_request", "emergency", zip_code="99999"),
        Intake("I5", AS_OF, True, "phone", "electrical", "service_request", "same_day", caller_name="Sue", zip_code="85001"),
    ]
    availability = [
        AvailabilitySlot("hvac", date(2026, 6, 6), 2),
        AvailabilitySlot("hvac", date(2026, 6, 7), 3),
        AvailabilitySlot("plumbing", date(2026, 6, 8), 2),
        AvailabilitySlot("electrical", date(2026, 6, 9), 1),
    ]
    trade_values = [TradeValue("hvac", 450), TradeValue("plumbing", 350), TradeValue("electrical", 500)]
    return BookingData(AS_OF, intakes, AREA, availability, trade_values)


class TestAnalyze:
    def test_totals(self) -> None:
        t = a.analyze(_scenario()).totals
        assert t.intakes_received == 5
        assert t.qualified == 3
        assert t.proposed_bookings == 3
        assert t.after_hours_captured == 3
        assert t.recovered_revenue_cents == 130_000  # 45000 + 35000 + 50000

    def test_booked_vs_unbooked_split(self) -> None:
        result = a.analyze(_scenario())
        assert {b.intake_id for b in result.proposed_bookings} == {"I1", "I2", "I5"}
        assert {u.intake_id for u in result.unbooked} == {"I3", "I4"}

    def test_emergency_booking_details(self) -> None:
        by = {b.intake_id: b for b in a.analyze(_scenario()).proposed_bookings}
        assert by["I1"].proposed_date == date(2026, 6, 6)  # booked same day (earliest hvac)
        assert by["I1"].estimated_value_cents == 45_000
        assert by["I1"].confidence == pytest.approx(0.9, abs=1e-3)
        assert by["I1"].after_hours is True

    def test_unbooked_reasons(self) -> None:
        reasons = {u.intake_id: u.reason.lower() for u in a.analyze(_scenario()).unbooked}
        assert "spam" in reasons["I3"]
        assert "area" in reasons["I4"]

    def test_inputs_hash_stable_and_hex(self) -> None:
        h1 = a.analyze(_scenario()).inputs_hash
        h2 = a.analyze(_scenario()).inputs_hash
        assert h1 == h2 and len(h1) == 64


class TestProperties:
    @given(st.lists(st.integers(min_value=0, max_value=10), min_size=1, max_size=6))
    def test_recovered_never_negative(self, slot_counts: list[int]) -> None:
        avail = [AvailabilitySlot("hvac", date(2026, 6, 6 + i % 20), n) for i, n in enumerate(slot_counts)]
        data = BookingData(AS_OF, [], AREA, avail, [TradeValue("hvac", 450)])
        assert a.analyze(data).totals.recovered_revenue_cents == 0  # no intakes -> nothing recovered
