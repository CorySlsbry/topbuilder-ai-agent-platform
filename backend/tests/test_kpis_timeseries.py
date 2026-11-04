"""Oracle + property tests for the executive KPI TIMESERIES rollup (PURE, no DB).

`aggregate_kpis_timeseries` reads the SAME persisted `totals.*` fields the snapshot rollup reads
(ADR 0003 — it only summarizes deterministic figures already computed by the agent engines and
persisted with each run; it never recomputes a business number). It tags every figure by date,
agent, department and unit so the dashboard can draw history + side-by-side department series — the
"go backwards" view Bloom Growth can't give.

The result-shape constants below copy the REAL persisted totals (the field names asserted by the
per-agent fixture oracles and by test_org_kpis.py).
"""
from __future__ import annotations

from datetime import date

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.org import permissions
from app.org.kpis import aggregate_kpis_timeseries

# --- persisted figures (independent oracles) ---------------------------------------------------
D1, D2, D3 = date(2026, 6, 1), date(2026, 6, 2), date(2026, 6, 3)

LEAKAGE_D1 = 14_250.50
LEAKAGE_D3 = 9_100.00
INVENTORY_D2 = 1_875.25
DOC_VALUE_D2 = 2_920.00
BOOKING_RECOVERED_D1 = 3_260.00
AFTER_HOURS_D1 = 2_895.00
DRIVE_MIN_D2 = 60
TECHS_OT_D3 = 3


def _financial(leakage: float) -> dict:
    return {"agent": "financial", "totals": {"total_leakage_usd": leakage, "cash_30_day": 88_000.0}}


def _inventory(savings: float) -> dict:
    return {"agent": "inventory", "totals": {"total_arbitrage_annual_usd": savings}}


def _documents(value: float) -> dict:
    return {"agent": "documents", "totals": {"extracted_value_usd": value}}


def _booking(recovered: float, after_hours: float) -> dict:
    return {
        "agent": "booking",
        "totals": {"recovered_revenue_usd": recovered, "after_hours_recovered_usd": after_hours},
    }


def _routing(drive_saved: int) -> dict:
    return {"agent": "routing", "totals": {"drive_minutes_saved": drive_saved}}


def _workforce(techs_ot: int) -> dict:
    return {"agent": "workforce", "totals": {"technicians_in_overtime": techs_ot}}


# A realistic 3-day history: financial ran D1 + D3, inventory + documents + booking + routing on
# their own days, workforce on D3. Each agent's owning department comes from AGENT_CARDS[0].
def _runs() -> list[dict]:
    return [
        {"date": D1, "agent": "financial", "result": _financial(LEAKAGE_D1)},
        {"date": D1, "agent": "booking", "result": _booking(BOOKING_RECOVERED_D1, AFTER_HOURS_D1)},
        {"date": D2, "agent": "inventory", "result": _inventory(INVENTORY_D2)},
        {"date": D2, "agent": "documents", "result": _documents(DOC_VALUE_D2)},
        {"date": D2, "agent": "routing", "result": _routing(DRIVE_MIN_D2)},
        {"date": D3, "agent": "financial", "result": _financial(LEAKAGE_D3)},
        {"date": D3, "agent": "workforce", "result": _workforce(TECHS_OT_D3)},
    ]


DEPARTMENTS = [{"key": d["key"], "name": d["name"], "color": d["color"]} for d in permissions.DEPARTMENTS]


def _series_by_key(payload: dict) -> dict[str, dict]:
    return {s["key"]: s for s in payload["series"]}


def _point(series: dict, day: date) -> float | None:
    return next(p["value"] for p in series["points"] if p["date"] == day.isoformat())


# --------------------------------------------------------------------------------------------
class TestDateAxis:
    def test_dates_are_the_sorted_unique_days_in_window(self) -> None:
        payload = aggregate_kpis_timeseries(_runs(), DEPARTMENTS, D1, D3, None)
        assert payload["dates"] == [D1.isoformat(), D2.isoformat(), D3.isoformat()]

    def test_window_clips_out_of_range_runs(self) -> None:
        payload = aggregate_kpis_timeseries(_runs(), DEPARTMENTS, D2, D3, None)
        assert payload["dates"] == [D2.isoformat(), D3.isoformat()]
        leakage = _series_by_key(payload)["margin_leakage_flagged"]
        # D1's financial run is outside the window — only D3 contributes a value.
        assert _point(leakage, D2) is None
        assert _point(leakage, D3) == LEAKAGE_D3

    def test_accepts_iso_string_dates_equivalently(self) -> None:
        runs_iso = [{**r, "date": r["date"].isoformat()} for r in _runs()]
        from_str = aggregate_kpis_timeseries(runs_iso, DEPARTMENTS, D1, D3, None)
        from_obj = aggregate_kpis_timeseries(_runs(), DEPARTMENTS, D1, D3, None)
        assert from_str == from_obj


class TestSeriesValuesReadPersistedFieldsExactly:
    def test_each_metric_reads_its_persisted_total_per_day(self) -> None:
        payload = aggregate_kpis_timeseries(_runs(), DEPARTMENTS, D1, D3, None)
        s = _series_by_key(payload)
        assert _point(s["margin_leakage_flagged"], D1) == LEAKAGE_D1
        assert _point(s["margin_leakage_flagged"], D3) == LEAKAGE_D3
        assert _point(s["inventory_savings"], D2) == INVENTORY_D2
        assert _point(s["documents_value_extracted"], D2) == DOC_VALUE_D2
        assert _point(s["booking_recovered"], D1) == BOOKING_RECOVERED_D1
        assert _point(s["after_hours_captured"], D1) == AFTER_HOURS_D1
        assert _point(s["drive_time_saved"], D2) == DRIVE_MIN_D2
        assert _point(s["technicians_in_overtime"], D3) == TECHS_OT_D3

    def test_day_without_a_run_for_that_agent_is_a_null_point(self) -> None:
        payload = aggregate_kpis_timeseries(_runs(), DEPARTMENTS, D1, D3, None)
        s = _series_by_key(payload)
        # financial ran D1 and D3 but not D2 -> D2 is a gap (null), not zero.
        assert _point(s["margin_leakage_flagged"], D2) is None
        # inventory only ran D2.
        assert _point(s["inventory_savings"], D1) is None
        assert _point(s["inventory_savings"], D3) is None

    def test_latest_run_of_the_day_wins_when_an_agent_runs_twice(self) -> None:
        runs = _runs() + [{"date": D1, "agent": "financial", "result": _financial(20_000.0)}]
        payload = aggregate_kpis_timeseries(runs, DEPARTMENTS, D1, D3, None)
        # the later D1 financial run (appended last) overrides the earlier one for that day.
        assert _point(_series_by_key(payload)["margin_leakage_flagged"], D1) == 20_000.0

    def test_malformed_result_yields_null_points_not_an_error(self) -> None:
        runs = [{"date": D1, "agent": "financial", "result": {"agent": "financial"}}]  # no totals
        payload = aggregate_kpis_timeseries(runs, DEPARTMENTS, D1, D1, None)
        assert _point(_series_by_key(payload)["margin_leakage_flagged"], D1) is None


class TestSeriesMetadata:
    def test_series_carry_agent_department_unit_label(self) -> None:
        payload = aggregate_kpis_timeseries(_runs(), DEPARTMENTS, D1, D3, None)
        leakage = _series_by_key(payload)["margin_leakage_flagged"]
        # financial's owning department is AGENT_CARDS' first dept_key = 'finance'.
        assert leakage["agent"] == "financial"
        assert leakage["department"] == "finance"
        assert leakage["unit"] == "usd"
        assert leakage["label"] == "Margin leakage flagged"
        assert leakage["color"] == next(d["color"] for d in DEPARTMENTS if d["key"] == "finance")

    def test_drive_time_metric_is_tagged_to_dispatch(self) -> None:
        payload = aggregate_kpis_timeseries(_runs(), DEPARTMENTS, D1, D3, None)
        assert _series_by_key(payload)["drive_time_saved"]["department"] == "dispatch"


class TestDepartmentFilter:
    def test_filter_keeps_only_the_named_departments_series(self) -> None:
        payload = aggregate_kpis_timeseries(_runs(), DEPARTMENTS, D1, D3, ["finance"])
        depts = {s["department"] for s in payload["series"]}
        assert depts == {"finance"}
        # finance is the home department of the financial agent only (documents' first dept_key is
        # front_office — see AGENT_CARDS), so finance owns exactly the margin-leakage metric.
        keys = {s["key"] for s in payload["series"]}
        assert keys == {"margin_leakage_flagged"}

    def test_front_office_owns_the_booking_and_documents_metrics(self) -> None:
        payload = aggregate_kpis_timeseries(_runs(), DEPARTMENTS, D1, D3, ["front_office"])
        # booking's home dept is front_office (its first dept_key); documents' too. Booking
        # contributes both its recovered + after-hours metrics.
        assert {s["key"] for s in payload["series"]} == {
            "booking_recovered",
            "after_hours_captured",
            "documents_value_extracted",
        }

    def test_empty_filter_is_treated_as_all(self) -> None:
        all_series = aggregate_kpis_timeseries(_runs(), DEPARTMENTS, D1, D3, None)["series"]
        empty_filter = aggregate_kpis_timeseries(_runs(), DEPARTMENTS, D1, D3, [])["series"]
        assert {s["key"] for s in empty_filter} == {s["key"] for s in all_series}

    def test_unknown_department_filter_yields_no_series(self) -> None:
        payload = aggregate_kpis_timeseries(_runs(), DEPARTMENTS, D1, D3, ["nonexistent"])
        assert payload["series"] == []
        # the date axis is still the window, so the chart renders an empty grid not an error.
        assert payload["dates"] == [D1.isoformat(), D2.isoformat(), D3.isoformat()]


class TestDepartmentsPresent:
    def test_departments_carry_through_for_the_panel_layout(self) -> None:
        payload = aggregate_kpis_timeseries(_runs(), DEPARTMENTS, D1, D3, None)
        # every metric's department is one of the known departments.
        known = {d["key"] for d in DEPARTMENTS}
        assert all(s["department"] in known for s in payload["series"])


class TestProperties:
    @given(st.integers(min_value=0, max_value=50_000))
    def test_value_round_trips_through_the_series(self, leakage: int) -> None:
        runs = [{"date": D1, "agent": "financial", "result": _financial(float(leakage))}]
        payload = aggregate_kpis_timeseries(runs, DEPARTMENTS, D1, D1, None)
        assert _point(_series_by_key(payload)["margin_leakage_flagged"], D1) == float(leakage)

    @given(
        st.lists(
            st.tuples(st.sampled_from([D1, D2, D3]), st.floats(0, 1e6, allow_nan=False)),
            max_size=8,
        )
    )
    def test_every_point_count_equals_the_date_axis_length(
        self, entries: list[tuple[date, float]]
    ) -> None:
        runs = [{"date": d, "agent": "financial", "result": _financial(v)} for d, v in entries]
        payload = aggregate_kpis_timeseries(runs, DEPARTMENTS, D1, D3, None)
        n = len(payload["dates"])
        assert all(len(s["points"]) == n for s in payload["series"])
