"""Deterministic KPI forecasting + monthly rollup for the executive/CFO trend view (ADR 0003).

PURE, no IO, no LLM — every projected figure comes from tested code. Two capabilities:

- ``project_series``: a DAMPED linear trend (Gardner's damped-trend method) with an optional
  multiplicative year-over-year seasonal overlay when at least one full seasonal cycle of history
  exists. Damping (phi<1) stops the trend from extrapolating to absurd values over the 6-month
  horizon; the seasonal overlay, anchored on the latest actual's phase, lets the 13-week and
  26-week forward views carry the same seasonal shape the business actually has. Projected points
  are flagged ``projected=True`` so the chart renders them as a distinct forward band.

- ``to_monthly``: aggregate a weekly series into calendar months — SUM for flow metrics
  (revenue, calls), LAST for stock/snapshot metrics (cash, A/R balance, pipeline), MEAN for rate
  metrics (percent, ratio). This drives the "monthly trends" view; the weekly series drives the
  rolling-year view.

Rolling-year-back = ask the engine for 52 weekly columns; forward = project 13 (a CFO quarter) and
26 (six months) weeks. Together they surface seasonality: last year's actuals behind, the seasonal
projection ahead.
"""
from __future__ import annotations

import datetime as dt

from app.org.scorecard import SeriesPoint

# Stock/snapshot KPIs: a point-in-time balance, so a month rolls up as the LAST value, never a sum.
SNAPSHOT_KEYS: frozenset[str] = frozenset(
    {
        "cash", "credit_card_balance", "line_of_credit_used", "quick_ratio",
        "ar_total", "ar_current", "ar_1_30", "ar_31_60", "ar_61_90", "ar_91_120", "ar_121_plus",
        "follow_up_backlog", "upcoming_jobs_1wk", "upcoming_jobs_2wk", "upcoming_jobs_4wk",
    }
)
_RATE_UNITS: frozenset[str] = frozenset({"percent", "ratio", "bool"})


def aggregation_for(key: str, unit: str) -> str:
    """How a KPI's weekly points roll up into a month: 'last' (snapshots), 'mean' (rates), 'sum'."""
    if key in SNAPSHOT_KEYS:
        return "last"
    if unit in _RATE_UNITS:
        return "mean"
    return "sum"


def _present(series: list[SeriesPoint]) -> list[tuple[int, float]]:
    """(index, value) for every point that has a value — gaps are skipped, not zero-filled."""
    return [(i, float(p.value)) for i, p in enumerate(series) if p.value is not None]


def _ols_slope(values: list[float]) -> float:
    """Least-squares slope of values over x = 0..n-1 (per-step change). 0 for <2 points or no spread."""
    n = len(values)
    if n < 2:
        return 0.0
    mean_x = (n - 1) / 2.0
    mean_y = sum(values) / n
    denom = sum((x - mean_x) ** 2 for x in range(n))
    if denom == 0:
        return 0.0
    num = sum((x - mean_x) * (values[x] - mean_y) for x in range(n))
    return num / denom


def _seasonal_factors(values: list[float], period: int) -> list[float] | None:
    """Multiplicative seasonal factor per phase (0..period-1), or None when < one full cycle.

    factor[phase] = mean over the cycles of value / (that cycle's mean level), normalized so the
    factors average 1. A phase never observed, or a degenerate all-zero history, yields None.
    """
    n = len(values)
    if n < period or period <= 1:
        return None
    cycles = n // period
    if cycles < 1:
        return None
    # De-level each full cycle by its own mean, then average the ratios per phase.
    sums = [0.0] * period
    counts = [0] * period
    for c in range(cycles):
        window = values[c * period:(c + 1) * period]
        level = sum(window) / period
        if level == 0:
            continue
        for phase, v in enumerate(window):
            sums[phase] += v / level
            counts[phase] += 1
    if any(cnt == 0 for cnt in counts):
        return None
    factors = [sums[p] / counts[p] for p in range(period)]
    mean_factor = sum(factors) / period
    if mean_factor == 0:
        return None
    return [f / mean_factor for f in factors]


def _add_days(iso_date: str, days: int) -> str:
    d = dt.date.fromisoformat(iso_date[:10])
    return (d + dt.timedelta(days=days)).isoformat()


def project_series(
    history: list[SeriesPoint],
    horizon: int,
    *,
    step_days: int = 7,
    seasonal_period: int = 52,
    damping: float = 0.85,
    non_negative: bool = True,
) -> list[SeriesPoint]:
    """Project ``horizon`` steps forward from a weekly history (all points flagged projected=True).

    Base = last actual value + a DAMPED accumulation of the OLS trend (level + slope * sum(phi^k)).
    When >= one seasonal cycle of history exists, a phase-relative seasonal factor (anchored on the
    latest actual's phase, so the first step's own phase is neutral) reshapes the base. Values are
    clamped to >= 0 when ``non_negative``. Empty/one-point history degrades gracefully (flat).
    """
    if horizon <= 0 or not history:
        return []
    present = _present(history)
    if not present:
        return []
    last_date = history[-1].date
    last_value = present[-1][1]
    if len(present) < 2:
        return [
            SeriesPoint(date=_add_days(last_date, step_days * i), value=round(last_value, 2), projected=True)
            for i in range(1, horizon + 1)
        ]
    slope = _ols_slope([v for _, v in present])
    factors = _seasonal_factors([v for _, v in present], seasonal_period)
    anchor_phase = (len(present) - 1) % seasonal_period
    out: list[SeriesPoint] = []
    cum = 0.0
    for i in range(1, horizon + 1):
        cum += damping ** (i - 1)  # damped trend: each further step contributes less
        base = last_value + slope * cum
        if factors is not None:
            future_phase = (len(present) - 1 + i) % seasonal_period
            anchor = factors[anchor_phase] or 1.0
            base *= factors[future_phase] / anchor  # relative to the current phase (step-0 neutral)
        if non_negative and base < 0:
            base = 0.0
        out.append(SeriesPoint(date=_add_days(last_date, step_days * i), value=round(base, 2), projected=True))
    return out


def to_monthly(history: list[SeriesPoint], aggregation: str) -> list[SeriesPoint]:
    """Roll a weekly series up into calendar months (chronological). aggregation: 'sum'|'last'|'mean'.

    A month with no present points is omitted (never emitted as a false 0). The point's date is the
    first of that month. A projected month (any projected source point) stays flagged projected.
    """
    buckets: dict[tuple[int, int], list[tuple[str, float, bool]]] = {}
    order: list[tuple[int, int]] = []
    for p in history:
        if p.value is None:
            continue
        d = dt.date.fromisoformat(p.date[:10])
        key = (d.year, d.month)
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append((p.date, float(p.value), p.projected))
    out: list[SeriesPoint] = []
    for key in order:
        pts = buckets[key]
        values = [v for _, v, _ in pts]
        if aggregation == "sum":
            agg = sum(values)
        elif aggregation == "mean":
            agg = sum(values) / len(values)
        else:  # "last"
            agg = pts[-1][1]
        projected = any(pr for _, _, pr in pts)
        out.append(SeriesPoint(date=f"{key[0]:04d}-{key[1]:02d}-01", value=round(agg, 2), projected=projected))
    return out
