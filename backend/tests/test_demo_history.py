"""Oracle + property tests for the demo run-history generator (PURE, no DB).

`app/org/demo_history.py` manufactures the deterministic ~30-day history the executive KPI charts
read on a DEMO tenant: per-(agent, field) hash-seeded smoothed noise around the SAME fixture-oracle
baselines the live demo agents produce (booking 3260/2895, routing 60, financial 14250.50,
inventory 1875.25, documents 2920, workforce 3 — see test_org_kpis.py), with a weekly rhythm
(weekend dips on demand-driven metrics). ADR 0003 holds: every figure comes from this pure,
deterministic code — same inputs always produce the same output, and the payloads round-trip
through the UNMODIFIED `aggregate_kpis_timeseries`.

The exact-value assertions in TestDeterminismPins are regression pins: they lock the generator's
output across sessions/refactors (the determinism contract), while the surrounding range / rhythm /
subset assertions are independent hand-computed oracles.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.org import permissions
from app.org.demo_history import (
    SEED_COVERAGE_THRESHOLD,
    SEEDED_SOURCE,
    demo_run_history,
    needs_seeding,
    plan_seed_runs,
    window_days,
)
from app.org.kpis import _AGENT_KPIS, CHARTED_AGENTS, aggregate_kpis_timeseries

SLUG = "canyonridge"

# Fixed calendar anchors (June 2026): the 1st is a Monday, the 6th a Saturday, the 7th a Sunday.
MON, TUE = date(2026, 6, 1), date(2026, 6, 2)
SAT, SUN = date(2026, 6, 6), date(2026, 6, 7)

# The live fixture-oracle baselines the generator anchors to (copied from test_org_kpis.py).
BOOKING_BASE = 3260.00
ROUTING_BASE = 60
FINANCIAL_BASE = 14250.50
INVENTORY_BASE = 1875.25
DOCUMENTS_BASE = 2920.00
WORKFORCE_BASE = 3

DEPARTMENTS = [
    {"key": d["key"], "name": d["name"], "color": d["color"]} for d in permissions.DEPARTMENTS
]

ALL_KPI_KEYS = {key for key, _, _, _, _, _ in _AGENT_KPIS}


def _month_of(agent: str, days: int = 28, anchor: date = MON) -> list[dict]:
    return [demo_run_history(SLUG, agent, anchor + timedelta(days=i)) for i in range(days)]


class TestChartedAgentsExport:
    def test_charted_agents_stay_in_lockstep_with_the_kpi_table(self) -> None:
        assert set(CHARTED_AGENTS) == {agent for _, _, agent, _, _, _ in _AGENT_KPIS}

    def test_charted_agents_are_the_six_history_agents(self) -> None:
        assert set(CHARTED_AGENTS) == {
            "booking", "routing", "financial", "inventory", "documents", "workforce",
        }


class TestDeterminism:
    def test_same_inputs_produce_the_identical_payload(self) -> None:
        for agent in CHARTED_AGENTS:
            assert demo_run_history(SLUG, agent, MON) == demo_run_history(SLUG, agent, MON)

    def test_different_tenants_get_different_histories(self) -> None:
        ours = [demo_run_history(SLUG, "financial", MON + timedelta(days=i)) for i in range(5)]
        theirs = [demo_run_history("apex", "financial", MON + timedelta(days=i)) for i in range(5)]
        assert ours != theirs

    def test_values_vary_across_days(self) -> None:
        month = _month_of("financial")
        values = {r["totals"]["total_leakage_usd"] for r in month}
        assert len(values) > 1

    def test_unknown_agent_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            demo_run_history(SLUG, "not-an-agent", MON)


class TestPayloadShape:
    def test_payload_carries_agent_totals_and_the_seeded_marker(self) -> None:
        for agent in CHARTED_AGENTS:
            payload = demo_run_history(SLUG, agent, MON)
            assert payload["agent"] == agent
            assert isinstance(payload["totals"], dict) and payload["totals"]
            assert payload["seeded"] is True
            assert payload["source"] == SEEDED_SOURCE

    def test_usd_figures_are_rounded_to_cents(self) -> None:
        for run in _month_of("booking"):
            for field in ("recovered_revenue_usd", "after_hours_recovered_usd"):
                value = run["totals"][field]
                assert value == round(value, 2)

    def test_count_figures_are_non_negative_ints(self) -> None:
        for agent, field in (
            ("routing", "drive_minutes_saved"),
            ("workforce", "technicians_in_overtime"),
        ):
            for run in _month_of(agent):
                value = run["totals"][field]
                assert isinstance(value, int) and value >= 0


class TestValueRealism:
    """Hand-computed envelope oracles: base * weekly_factor * (1 +/- amplitude) bounds every value,
    so the assertions below are independent of the noise implementation."""

    def test_financial_leakage_stays_within_ten_pct_of_the_live_oracle(self) -> None:
        for run in _month_of("financial"):
            value = run["totals"]["total_leakage_usd"]
            assert FINANCIAL_BASE * 0.90 <= value <= FINANCIAL_BASE * 1.10

    def test_inventory_savings_move_slowly_around_the_live_oracle(self) -> None:
        for run in _month_of("inventory"):
            value = run["totals"]["total_arbitrage_annual_usd"]
            assert INVENTORY_BASE * 0.94 <= value <= INVENTORY_BASE * 1.06

    def test_booking_sundays_dip_below_every_weekday(self) -> None:
        # Sunday factor 0.50 * (1+0.15) < Tuesday factor 1.03 * (1-0.15): EVERY Sunday value sits
        # below EVERY Tuesday value — a deterministic weekend rhythm, not an on-average fluke.
        sundays = [
            demo_run_history(SLUG, "booking", SUN + timedelta(weeks=w))["totals"][
                "recovered_revenue_usd"]
            for w in range(8)
        ]
        tuesdays = [
            demo_run_history(SLUG, "booking", TUE + timedelta(weeks=w))["totals"][
                "recovered_revenue_usd"]
            for w in range(8)
        ]
        assert max(sundays) < min(tuesdays)

    def test_dispatch_board_quiets_down_on_weekends(self) -> None:
        saturday = demo_run_history(SLUG, "routing", SAT)["totals"]["drive_minutes_saved"]
        monday = demo_run_history(SLUG, "routing", MON)["totals"]["drive_minutes_saved"]
        assert saturday < monday

    def test_after_hours_is_always_a_strict_subset_of_recovered_revenue(self) -> None:
        # Mirrors the production invariant the snapshot rollup depends on (the after-hours figure
        # is never re-added to the headline) — a seeded day must never invert it.
        for run in _month_of("booking", days=60):
            totals = run["totals"]
            assert 0 < totals["after_hours_recovered_usd"] < totals["recovered_revenue_usd"]
            ratio = totals["after_hours_recovered_usd"] / totals["recovered_revenue_usd"]
            assert 0.75 <= ratio <= 0.95

    def test_workforce_overtime_count_stays_in_a_believable_band(self) -> None:
        for run in _month_of("workforce", days=60):
            assert 0 <= run["totals"]["technicians_in_overtime"] <= 6


class TestDeterminismPins:
    """Regression pins: exact generated values, locked so a refactor can never silently change the
    seeded history (same inputs -> same output is the module's contract)."""

    def test_pinned_financial_value(self) -> None:
        assert demo_run_history(SLUG, "financial", MON)["totals"]["total_leakage_usd"] == 13749.64

    def test_pinned_booking_values(self) -> None:
        totals = demo_run_history(SLUG, "booking", TUE)["totals"]
        assert totals == {"recovered_revenue_usd": 3456.15, "after_hours_recovered_usd": 3105.79}

    def test_pinned_routing_value(self) -> None:
        assert demo_run_history(SLUG, "routing", SAT)["totals"]["drive_minutes_saved"] == 26


class TestWindowAndGate:
    def test_window_days_is_inclusive(self) -> None:
        assert window_days(MON, MON + timedelta(days=2)) == [
            MON, MON + timedelta(days=1), MON + timedelta(days=2),
        ]
        assert window_days(MON, MON) == [MON]
        assert window_days(MON, MON - timedelta(days=1)) == []

    def test_sparse_coverage_needs_seeding(self) -> None:
        # 17 of 30 days = 56.7% < the 60% threshold.
        window_end = MON + timedelta(days=29)
        existing = {MON + timedelta(days=i) for i in range(17)}
        assert needs_seeding(existing, MON, window_end) is True

    def test_coverage_at_the_threshold_does_not_need_seeding(self) -> None:
        # 18 of 30 days = exactly 60% — not strictly below the threshold.
        window_end = MON + timedelta(days=29)
        existing = {MON + timedelta(days=i) for i in range(18)}
        assert needs_seeding(existing, MON, window_end) is False

    def test_days_outside_the_window_do_not_count_as_coverage(self) -> None:
        existing = {MON - timedelta(days=i) for i in range(1, 40)}  # all before the window
        assert needs_seeding(existing, MON, MON + timedelta(days=29)) is True

    def test_threshold_constant_is_the_documented_sixty_pct(self) -> None:
        assert SEED_COVERAGE_THRESHOLD == 0.6


class TestPlanSeedRuns:
    def test_empty_history_plans_every_agent_for_every_day(self) -> None:
        end = MON + timedelta(days=29)
        plan = plan_seed_runs(SLUG, {}, MON, end)
        assert len(plan) == len(CHARTED_AGENTS) * 30
        assert {agent for agent, _, _ in plan} == set(CHARTED_AGENTS)

    def test_existing_agent_days_are_never_replanned(self) -> None:
        end = MON + timedelta(days=29)
        existing = {"booking": {MON, TUE}}
        plan = plan_seed_runs(SLUG, existing, MON, end)
        booking_days = {day for agent, day, _ in plan if agent == "booking"}
        assert MON not in booking_days and TUE not in booking_days
        assert len(plan) == len(CHARTED_AGENTS) * 30 - 2
        # The other agents still get MON/TUE — the existence key is (agent, day), not day.
        assert MON in {day for agent, day, _ in plan if agent == "financial"}

    def test_dense_coverage_plans_nothing(self) -> None:
        end = MON + timedelta(days=29)
        existing = {"booking": {MON + timedelta(days=i) for i in range(18)}}  # 60% of the window
        assert plan_seed_runs(SLUG, existing, MON, end) == []

    def test_planned_payloads_are_the_deterministic_generator_output(self) -> None:
        plan = plan_seed_runs(SLUG, {}, MON, MON)
        assert all(result == demo_run_history(SLUG, agent, day) for agent, day, result in plan)


class TestRoundTripThroughTheUnmodifiedAggregator:
    """The load-bearing constraint: seeded rows must produce a daily point for EVERY charted KPI
    through the untouched `aggregate_kpis_timeseries`."""

    def test_thirty_days_of_seed_yield_thirty_non_null_points_per_kpi(self) -> None:
        start, end = MON, MON + timedelta(days=29)
        plan = plan_seed_runs(SLUG, {}, start, end)
        runs = [{"date": day, "agent": agent, "result": result} for agent, day, result in plan]
        payload = aggregate_kpis_timeseries(runs, DEPARTMENTS, start, end, None)
        assert len(payload["dates"]) == 30
        assert {s["key"] for s in payload["series"]} == ALL_KPI_KEYS
        for series in payload["series"]:
            assert len(series["points"]) == 30
            assert all(p["value"] is not None for p in series["points"]), series["key"]

    def test_seeded_and_real_runs_compose_with_the_real_run_winning_its_day(self) -> None:
        # A real run persisted later the same day overrides the seeded midday row (list order =
        # started_at ASC in the repository; the aggregator folds last-wins per (date, agent)).
        real = {"agent": "financial", "totals": {"total_leakage_usd": 9_999.0}}
        seeded = demo_run_history(SLUG, "financial", MON)
        runs = [
            {"date": MON, "agent": "financial", "result": seeded},
            {"date": MON, "agent": "financial", "result": real},
        ]
        payload = aggregate_kpis_timeseries(runs, DEPARTMENTS, MON, MON, None)
        leakage = next(s for s in payload["series"] if s["key"] == "margin_leakage_flagged")
        assert leakage["points"][0]["value"] == 9_999.0
