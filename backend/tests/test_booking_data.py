"""Wiring test for the Booking agent's fixture adapter -> engine -> schema -> narration path.

No database, no network. Asserts the realistic fixture batch produces the exact, hand-computed result
the dashboard will show, so the demo numbers can't silently drift. Oracle (14 inbound intakes):

  qualified      = 10   (service_request/existing_customer, served trade, in-area-or-no-zip)
  booked         =  8   {B01,B02,B03,B05,B06,B10,B13,B14}   (qualified AND an open slot)
  unbooked       =  6   {B04,B07,B08,B09,B11,B12}
                          B04,B12 -> electrical booked solid (no availability)
                          B07 spam · B08 out of area · B09 wrong number · B11 sales
  after-hours booked = 7   (all booked except B10, which came in during business hours)
  recovered      = $3,260  (hvac 485*4 + plumbing 365*2 + drains 295*2)
  after-hours    = $2,895  ($3,260 less B10's $365 daytime plumbing job)
"""
from __future__ import annotations

from datetime import date, datetime

from app.agents.booking.analytics import analyze
from app.agents.booking.data import assemble_booking_data
from app.agents.booking.reasoning import _template_narrative
from app.agents.booking.schemas import build_result
from app.integrations.booking_intake.fixture_client import FixtureBookingIntakeClient

AS_OF = datetime(2026, 6, 6, 19, 0)  # Saturday 7pm — the after-hours batch the demo tells a story about
BOOKED_IDS = {"B01", "B02", "B03", "B05", "B06", "B10", "B13", "B14"}
UNBOOKED_IDS = {"B04", "B07", "B08", "B09", "B11", "B12"}


async def _analyze_fixtures():
    data = await assemble_booking_data(FixtureBookingIntakeClient(as_of=AS_OF), as_of=AS_OF)
    return analyze(data)


class TestFixtureOracle:
    async def test_totals(self) -> None:
        t = (await _analyze_fixtures()).totals
        assert (
            t.intakes_received,
            t.qualified,
            t.proposed_bookings,
            t.after_hours_captured,
            t.recovered_revenue_cents,
        ) == (14, 10, 8, 7, 326_000)

    async def test_booked_vs_unbooked_split(self) -> None:
        result = await _analyze_fixtures()
        assert {b.intake_id for b in result.proposed_bookings} == BOOKED_IDS
        assert {u.intake_id for u in result.unbooked} == UNBOOKED_IDS

    async def test_electrical_booked_solid_goes_to_human(self) -> None:
        unbooked = {u.intake_id: u.reason.lower() for u in (await _analyze_fixtures()).unbooked}
        assert "availability" in unbooked["B04"]  # emergency, qualified, but no open electrical slot
        assert "availability" in unbooked["B12"]

    async def test_screening_reasons(self) -> None:
        unbooked = {u.intake_id: u.reason.lower() for u in (await _analyze_fixtures()).unbooked}
        assert "spam" in unbooked["B07"]
        assert "area" in unbooked["B08"]
        assert "wrong" in unbooked["B09"]
        assert "sales" in unbooked["B11"]

    async def test_emergency_books_soonest_slot(self) -> None:
        by = {b.intake_id: b for b in (await _analyze_fixtures()).proposed_bookings}
        assert by["B01"].proposed_date == AS_OF.date()  # earliest open hvac slot is today
        assert by["B01"].after_hours is True


class TestResultSchema:
    async def test_rollups_and_marquee_metric(self) -> None:
        analysis = await _analyze_fixtures()
        result = build_result(
            analysis, narrative="n/a", analysis_timestamp=datetime(2026, 6, 6, 19, 1)
        )
        assert result.agent == "booking"
        assert result.totals.recovered_revenue_usd == 3260.00
        assert result.totals.after_hours_recovered_usd == 2895.00  # $3,260 less B10's $365 daytime job
        assert result.totals.screened_out == 6
        assert len(result.proposed_bookings) == 8

    async def test_template_narrative_leads_with_after_hours(self) -> None:
        narrative = _template_narrative(await _analyze_fixtures())
        assert "after-hours" in narrative.lower()
        assert "2,895" in narrative  # the after-hours recovered dollars are quoted, not recomputed
