"""Oracle tests for the deterministic KPI forecast + monthly rollup (ADR 0003)."""
from __future__ import annotations

import datetime as dt

import pytest

from app.org.forecast import (
    _ols_slope,
    aggregation_for,
    project_series,
    to_monthly,
)
from app.org.scorecard import SeriesPoint


def _hist(values, start: str = "2026-01-05") -> list[SeriesPoint]:
    """Weekly SeriesPoints from a list of values (None = a gap)."""
    d0 = dt.date.fromisoformat(start)
    return [SeriesPoint((d0 + dt.timedelta(days=7 * i)).isoformat(), v) for i, v in enumerate(values)]


def test_ols_slope():
    assert _ols_slope([10, 12, 14]) == pytest.approx(2.0)  # perfect +2/step line
    assert _ols_slope([5, 5, 5]) == 0.0  # flat
    assert _ols_slope([7]) == 0.0  # too few points


def test_project_damped_trend_values_dates_and_flag():
    out = project_series(_hist([10, 12, 14]), 3, damping=0.85, non_negative=True)
    # slope=2, last=14, base_i = 14 + 2*(sum of 0.85^k) = 16.0, 17.7, ~19.145
    assert [p.date for p in out] == ["2026-01-26", "2026-02-02", "2026-02-09"]
    assert [p.value for p in out] == pytest.approx([16.0, 17.7, 19.145], abs=0.02)
    assert all(p.projected for p in out)


def test_project_flat_when_only_one_present_point():
    out = project_series(_hist([None, None, 5]), 2)
    assert [p.value for p in out] == [5.0, 5.0]
    assert all(p.projected for p in out)


def test_project_clamps_to_non_negative():
    # slope=-40, last=20, undamped -> would go negative; clamped to 0.
    out = project_series(_hist([100, 60, 20]), 4, damping=1.0, non_negative=True)
    assert [p.value for p in out] == [0.0, 0.0, 0.0, 0.0]


def test_project_empty_or_all_gaps_returns_empty():
    assert project_series([], 5) == []
    assert project_series(_hist([None, None]), 5) == []
    assert project_series(_hist([10, 12, 14]), 0) == []


def test_seasonal_overlay_reshapes_the_projection():
    # period=4, two cycles of a low/high/low/high pattern -> the forward band alternates too.
    out = project_series(_hist([10, 20, 10, 20, 12, 24, 12, 24]), 4,
                         seasonal_period=4, damping=1.0, non_negative=True)
    v = [p.value for p in out]
    # anchor phase = 3 (a 'high'); forward phases are 0(low),1(high),2(low),3(high).
    assert v[0] < v[1] and v[2] < v[3]  # each in-cycle low is below its following high


def test_to_monthly_sum_last_mean():
    h = [SeriesPoint("2026-01-05", 10), SeriesPoint("2026-01-19", 20),
         SeriesPoint("2026-02-02", 5), SeriesPoint("2026-02-16", 15)]
    assert [(p.date, p.value) for p in to_monthly(h, "sum")] == [("2026-01-01", 30.0), ("2026-02-01", 20.0)]
    assert [(p.date, p.value) for p in to_monthly(h, "last")] == [("2026-01-01", 20.0), ("2026-02-01", 15.0)]
    assert [(p.date, p.value) for p in to_monthly(h, "mean")] == [("2026-01-01", 15.0), ("2026-02-01", 10.0)]


def test_to_monthly_skips_empty_months_and_propagates_projected():
    h = [SeriesPoint("2026-01-05", None), SeriesPoint("2026-01-19", 10),
         SeriesPoint("2026-02-02", 5, projected=True)]
    out = to_monthly(h, "sum")
    assert [(p.date, p.value, p.projected) for p in out] == [
        ("2026-01-01", 10.0, False), ("2026-02-01", 5.0, True)]


def test_aggregation_for_maps_flow_snapshot_rate():
    assert aggregation_for("gross_sales", "usd") == "sum"      # flow
    assert aggregation_for("cash", "usd") == "last"            # snapshot balance
    assert aggregation_for("ar_total", "usd") == "last"        # snapshot balance
    assert aggregation_for("closing_pct", "percent") == "mean"  # rate
    assert aggregation_for("quick_ratio", "ratio") == "last"   # snapshot ratio (SNAPSHOT_KEYS wins over rate)
