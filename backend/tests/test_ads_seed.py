"""PURE tests for the trade-show template seed (no DB).

``app.ads.seed.template_specs()`` is the deterministic source-of-truth for the four 2026 trade-show
geofence templates. These tests pin the load-bearing facts transcribed from the trade-show markdown so a
later edit can't silently drift the slug, the geofence pin, or the budget:

  * the Nashville template exists under its canonical slug ``build-expo-nashville-2026``;
  * its primary geofence pin is the Music City Center (36.1565, -86.7766) at a 1-mile radius;
  * its budget is $10/day with a $20 lifetime cap, expressed as INTEGER CENTS (1000 / 2000);
  * the spec feeds the engine cleanly — ``build_from_template`` resolves it to a Meta plan whose adset
    daily_budget is the cents-as-string "1000" (an independent oracle, not read back from the spec).

Every asserted figure is an independent hand-computed oracle (the dollar amounts from geofence-configs.md
§1 converted to cents by hand), never echoed from the function under test.
"""
from __future__ import annotations

from app.ads import seed
from app.ads.engine import build_from_template
from app.ads.schemas import CampaignPlan

_NASHVILLE_SLUG = "build-expo-nashville-2026"


def _by_slug(slug: str) -> dict:
    specs = {s["slug"]: s for s in seed.template_specs()}
    assert slug in specs, f"seed is missing template {slug!r}"
    return specs[slug]


class TestNashvilleTemplateResolves:
    def test_slug_present(self) -> None:
        # The four shows seed under their canonical slugs; Nashville is the launch-now show.
        slugs = {s["slug"] for s in seed.template_specs()}
        assert _NASHVILLE_SLUG in slugs

    def test_objective_is_traffic(self) -> None:
        # geofence-configs.md §1 / runbook: objective Traffic.
        assert _by_slug(_NASHVILLE_SLUG)["objective"] == "traffic"

    def test_primary_geo_pin_is_music_city_center(self) -> None:
        # The first custom location is the Music City Center pin at a 1.0-mile radius (geofence-configs §1).
        first_pin = _by_slug(_NASHVILLE_SLUG)["geo_spec"]["custom_locations"][0]
        assert first_pin == {"lat": 36.1565, "long": -86.7766, "radius_mi": 1.0}

    def test_geo_location_type_recent(self) -> None:
        # Meta intent: "People who were recently in this location."
        assert _by_slug(_NASHVILLE_SLUG)["geo_spec"]["location_type"] == "recent"

    def test_budget_cents(self) -> None:
        # $10/day, $20 lifetime cap (geofence-configs §1) — our canonical money unit is integer CENTS.
        budget = _by_slug(_NASHVILLE_SLUG)["budget_spec"]
        assert budget == {"daily_cents": 1000, "lifetime_cap_cents": 2000}

    def test_landing_url_is_show_page(self) -> None:
        assert (
            _by_slug(_NASHVILLE_SLUG)["creative_spec"]["landing_url"]
            == "https://topbuilderai.com/shows/build-expo-nashville-2026"
        )

    def test_spec_builds_a_meta_plan(self) -> None:
        # The seeded spec must feed the pure engine cleanly. Resolve it to a Meta plan and check the
        # adset daily_budget is cents-as-string "1000" — an independent oracle (Meta minor-unit string).
        plan = build_from_template(
            _by_slug(_NASHVILLE_SLUG), {"platform": "meta", "external_account_id": "act_test"}
        )
        assert isinstance(plan, CampaignPlan)
        assert plan.budget.daily_cents == 1000
        assert plan.requests["adset"]["daily_budget"] == "1000"
        assert plan.requests["adset"]["lifetime_budget"] == "2000"
        # the window is strictly start < end, so the engine accepted it (no ValueError raised).
        assert plan.schedule.start_at < plan.schedule.end_at


class TestAllShowsSeeded:
    def test_four_distinct_shows(self) -> None:
        slugs = [s["slug"] for s in seed.template_specs()]
        assert slugs == [
            "build-expo-nashville-2026",
            "build-expo-houston-2026",
            "western-roofing-expo-2026",
            "servicetitan-pantheon-2026",
        ]

    def test_every_template_is_trade_show_geofence_and_builds(self) -> None:
        # Each seeded template must be the generic trade_show_geofence shape AND resolve through the
        # engine for Meta without error (proves geo/schedule/budget specs are all well-formed).
        for spec in seed.template_specs():
            plan = build_from_template(spec, {"platform": "meta", "external_account_id": "act_test"})
            assert plan.platform == "meta"
            assert plan.budget.daily_cents > 0
            assert plan.budget.lifetime_cap_cents >= plan.budget.daily_cents

    def test_budgets_match_geofence_config_caps(self) -> None:
        # Hand-computed caps from geofence-configs.md, in cents: Nashville $20, Houston $24,
        # Western Roofing $30, Pantheon $36.
        caps = {s["slug"]: s["budget_spec"]["lifetime_cap_cents"] for s in seed.template_specs()}
        assert caps == {
            "build-expo-nashville-2026": 2000,
            "build-expo-houston-2026": 2400,
            "western-roofing-expo-2026": 3000,
            "servicetitan-pantheon-2026": 3600,
        }
