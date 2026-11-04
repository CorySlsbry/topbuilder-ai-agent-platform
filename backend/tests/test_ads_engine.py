"""Oracle + property tests for the pure deterministic ad-campaign engine (PURE, no DB).

Every asserted figure is an INDEPENDENT hand-computed oracle, not read back from the function under test:
  * meta daily_budget is the integer cents AS A STRING -> 1000 cents == "1000".
  * google amount_micros == cents * 10_000 -> 1000 cents == 10_000_000 micros.
  * duration_days(2026-06-30 .. 2026-07-02) == 2.
  * enforce_caps raises when requested daily (2500c) exceeds the daily cap (1000c), and when the
    projected lifetime spend exceeds the lifetime cap.

Anchor: a Nashville-like trade-show geofence template — $10/day, $20 lifetime cap, a 1-mile radius around
the Music City Center (36.1565, -86.7766), running 2026-06-30 -> 2026-07-02.
"""
from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.ads.engine import (
    MICROS_PER_CENT,
    build_from_template,
    cents_to_micros,
    cents_to_minor_unit_str,
    duration_days,
    enforce_caps,
    projected_lifetime_spend,
    validate_window,
)
from app.ads.schemas import CampaignPlan, SchedulePlan


def _nashville_template() -> dict:
    return {
        "name": "Nashville Trade Show Geofence",
        "objective": "leads",
        "geo_spec": {
            "custom_locations": [{"lat": 36.1565, "long": -86.7766, "radius_mi": 1}],
            "location_type": "recent",
        },
        "targeting_spec": {"age_min": 25, "age_max": 65},
        "schedule_spec": {"start_at": "2026-06-30T00:00:00", "end_at": "2026-07-02T00:00:00", "tz": "America/Chicago"},
        "budget_spec": {"daily_cents": 1000, "lifetime_cap_cents": 2000},
        "creative_spec": {
            "headline": "Stop losing margin",
            "primary_text": "The back office ServiceTitan can't run.",
            "description": "Book a 15-minute demo.",
            "landing_url": "https://topbuilderai.com",
            "image_ref": "img-123",
        },
    }


def _meta_account() -> dict:
    return {"platform": "meta", "external_account_id": "act_555"}


def _google_account() -> dict:
    return {"platform": "google", "external_account_id": "(555) 010-0100"}


# --------------------------------------------------------------------------------------------
# 1. Cents + schedule primitives — independent oracles
# --------------------------------------------------------------------------------------------
class TestCentsConversions:
    def test_micros_per_cent_constant(self) -> None:
        assert MICROS_PER_CENT == 10_000

    @pytest.mark.parametrize(
        "cents, micros",
        [(1000, 10_000_000), (0, 0), (1, 10_000), (12_345, 123_450_000)],
    )
    def test_cents_to_micros(self, cents: int, micros: int) -> None:
        assert cents_to_micros(cents) == micros

    @pytest.mark.parametrize("cents, text", [(1000, "1000"), (0, "0"), (50_000, "50000")])
    def test_cents_to_minor_unit_str(self, cents: int, text: str) -> None:
        assert cents_to_minor_unit_str(cents) == text


class TestSchedule:
    def test_duration_days_oracle(self) -> None:
        sched = SchedulePlan(
            start_at="2026-06-30T00:00:00", end_at="2026-07-02T00:00:00", tz="America/Chicago"
        )
        assert duration_days(sched) == 2

    def test_partial_day_floors(self) -> None:
        sched = SchedulePlan(
            start_at="2026-06-30T00:00:00", end_at="2026-07-02T12:00:00", tz="UTC"
        )
        assert duration_days(sched) == 2  # 2.5 days floors to 2 whole days

    def test_validate_window_rejects_zero_length(self) -> None:
        sched = SchedulePlan(start_at="2026-06-30T00:00:00", end_at="2026-06-30T00:00:00", tz="UTC")
        with pytest.raises(ValueError):
            validate_window(sched)

    def test_validate_window_rejects_reversed(self) -> None:
        sched = SchedulePlan(start_at="2026-07-02T00:00:00", end_at="2026-06-30T00:00:00", tz="UTC")
        with pytest.raises(ValueError):
            duration_days(sched)


# --------------------------------------------------------------------------------------------
# 2. enforce_caps — the spend guard executors call before any write
# --------------------------------------------------------------------------------------------
class TestEnforceCaps:
    def test_within_caps_passes(self) -> None:
        # requested $10/day <= $10/day daily cap, and one day ($10) <= $20 lifetime cap. OK.
        enforce_caps(daily_cents=1000, lifetime_cap_cents=2000, requested_daily_cents=1000)

    def test_requested_over_daily_cap_raises(self) -> None:
        # requested $25/day > $10/day daily cap.
        with pytest.raises(ValueError, match="daily cap"):
            enforce_caps(daily_cents=1000, lifetime_cap_cents=2000, requested_daily_cents=2500)

    def test_requested_daily_over_lifetime_cap_raises(self) -> None:
        # requested $10/day clears the $10/day daily cap, but one day ($10) exceeds the $9 lifetime cap.
        with pytest.raises(ValueError, match="lifetime cap"):
            enforce_caps(daily_cents=1000, lifetime_cap_cents=900, requested_daily_cents=1000)

    def test_zero_daily_cap_raises(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            enforce_caps(daily_cents=0, lifetime_cap_cents=2000, requested_daily_cents=0)


class TestProjectedLifetimeSpend:
    @pytest.mark.parametrize(
        "daily, lifetime, expected",
        [
            (1000, 2000, 2000),   # $10/day, $20 cap -> 20//10 = 2 funded days -> $20.
            (1000, 2500, 2000),   # $10/day, $25 cap -> 25//10 = 2 funded days -> $20 (partial day unfunded).
            (700, 2000, 1400),    # $7/day, $20 cap -> 20//7 = 2 funded days -> $14.
            (1000, 1000, 1000),   # exactly one funded day.
        ],
    )
    def test_known(self, daily: int, lifetime: int, expected: int) -> None:
        assert projected_lifetime_spend(daily, lifetime) == expected

    def test_daily_over_lifetime_raises(self) -> None:
        with pytest.raises(ValueError, match="lifetime cap"):
            projected_lifetime_spend(1000, 900)

    def test_zero_daily_raises(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            projected_lifetime_spend(0, 2000)


# --------------------------------------------------------------------------------------------
# 3. build_from_template — Meta
# --------------------------------------------------------------------------------------------
class TestBuildMeta:
    def _plan(self) -> CampaignPlan:
        return build_from_template(_nashville_template(), _meta_account())

    def test_returns_campaign_plan(self) -> None:
        plan = self._plan()
        assert isinstance(plan, CampaignPlan)
        assert plan.platform == "meta"
        assert plan.name == "Nashville Trade Show Geofence"
        assert plan.objective == "leads"

    def test_budget_resolved_to_cents(self) -> None:
        plan = self._plan()
        assert plan.budget.daily_cents == 1000
        assert plan.budget.lifetime_cap_cents == 2000

    def test_meta_daily_budget_is_cents_as_string(self) -> None:
        plan = self._plan()
        assert plan.requests["adset"]["daily_budget"] == "1000"
        assert plan.requests["adset"]["lifetime_budget"] == "2000"

    def test_all_create_payloads_paused(self) -> None:
        plan = self._plan()
        assert plan.requests["campaign"]["status"] == "PAUSED"
        assert plan.requests["adset"]["status"] == "PAUSED"
        assert plan.requests["ad"]["status"] == "PAUSED"

    def test_meta_request_keys(self) -> None:
        plan = self._plan()
        assert set(plan.requests) == {"campaign", "adset", "adcreative", "ad"}

    def test_geo_custom_location_passed_through(self) -> None:
        plan = self._plan()
        loc = plan.requests["adset"]["targeting"]["geo_locations"]["custom_locations"][0]
        assert loc == {"latitude": 36.1565, "longitude": -86.7766, "radius": 1.0, "distance_unit": "mile"}

    def test_creative_copy_mapped(self) -> None:
        plan = self._plan()
        assert plan.requests["adcreative"]["title"] == "Stop losing margin"
        assert plan.requests["adcreative"]["object_url"] == "https://topbuilderai.com"


# --------------------------------------------------------------------------------------------
# 4. build_from_template — Google
# --------------------------------------------------------------------------------------------
class TestBuildGoogle:
    def _plan(self) -> CampaignPlan:
        return build_from_template(_nashville_template(), _google_account())

    def test_platform_is_google(self) -> None:
        assert self._plan().platform == "google"

    def test_google_amount_micros_oracle(self) -> None:
        plan = self._plan()
        # 1000 cents * 10_000 micros/cent == 10_000_000 micros.
        assert plan.requests["campaign_budget"]["amount_micros"] == 10_000_000

    def test_google_request_keys(self) -> None:
        plan = self._plan()
        assert set(plan.requests) == {"campaign_budget", "campaign", "ad_group", "criterion", "ad"}

    def test_campaign_paused(self) -> None:
        plan = self._plan()
        assert plan.requests["campaign"]["status"] == "PAUSED"
        assert plan.requests["ad"]["status"] == "PAUSED"

    def test_google_dates_yyyymmdd(self) -> None:
        plan = self._plan()
        assert plan.requests["campaign"]["start_date"] == "20260630"
        assert plan.requests["campaign"]["end_date"] == "20260702"

    def test_proximity_micro_degrees(self) -> None:
        plan = self._plan()
        prox = plan.requests["criterion"]["proximity"][0]
        # 36.1565 * 1_000_000 = 36_156_500 ; -86.7766 * 1_000_000 = -86_776_600.
        assert prox["latitude_in_micro_degrees"] == 36_156_500
        assert prox["longitude_in_micro_degrees"] == -86_776_600
        assert prox["radius"] == 1.0


# --------------------------------------------------------------------------------------------
# 5. Edge cases + invariants
# --------------------------------------------------------------------------------------------
class TestBuildEdgeCases:
    def test_unknown_platform_raises(self) -> None:
        with pytest.raises(ValueError, match="platform"):
            build_from_template(_nashville_template(), {"platform": "tiktok", "external_account_id": "x"})

    def test_reversed_schedule_in_template_raises(self) -> None:
        tmpl = _nashville_template()
        tmpl["schedule_spec"] = {"start_at": "2026-07-02T00:00:00", "end_at": "2026-06-30T00:00:00", "tz": "UTC"}
        with pytest.raises(ValueError):
            build_from_template(tmpl, _meta_account())


class TestProperties:
    @given(st.integers(min_value=0, max_value=10_000_000))
    def test_micros_roundtrip(self, cents: int) -> None:
        # cents -> micros -> back to cents is lossless (micros is an exact 10_000x scaling).
        micros = cents_to_micros(cents)
        assert micros == cents * 10_000
        assert micros // 10_000 == cents

    @given(st.integers(min_value=0, max_value=10_000_000))
    def test_minor_unit_str_roundtrips_to_int(self, cents: int) -> None:
        assert int(cents_to_minor_unit_str(cents)) == cents

    @given(
        daily=st.integers(min_value=1, max_value=1_000_000),
        requested=st.integers(min_value=1, max_value=1_000_000),
    )
    def test_enforce_caps_never_passes_over_daily(self, daily: int, requested: int) -> None:
        # A request over the daily cap must ALWAYS raise, regardless of the lifetime cap.
        if requested > daily:
            with pytest.raises(ValueError):
                enforce_caps(daily_cents=daily, lifetime_cap_cents=10_000_000, requested_daily_cents=requested)
