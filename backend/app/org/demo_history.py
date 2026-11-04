"""Deterministic demo run-history generator — PURE (no DB, no IO, no randomness source).

Gives the executive KPI timeseries a realistic ~30-day daily story on a DEMO tenant whose real
runs land on only a few distinct days. Three pure pieces:

  * ``demo_run_history(tenant_slug, agent, day)`` — a minimal succeeded-run payload containing
    exactly the ``totals.*`` fields ``aggregate_kpis_timeseries`` reads for that agent. Values are
    hash-seeded (SHA-256 over tenant/agent/field/day) smoothed noise around the SAME fixture-oracle
    baselines the live demo agents produce (booking 3260/2895, routing 60, financial 14250.50,
    inventory 1875.25, documents 2920, workforce 3), shaped by a weekly rhythm (weekend dips on
    demand-driven metrics) — so the newest seeded day flows into the real runs without a cliff.
  * ``needs_seeding(existing_days, start, end)`` — the sparsity gate (< 60% of window days covered).
  * ``plan_seed_runs(tenant_slug, existing, start, end)`` — the full idempotent plan, keyed on
    (agent, day): an agent/day that already has a succeeded run is never re-planned.

ADR 0003 holds: every figure is produced by this deterministic code (same inputs -> same output);
no LLM, no live data. Persistence lives in app/repositories/demo_runs.py; this module stays pure.
"""
from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from datetime import date, timedelta

from app.org.kpis import CHARTED_AGENTS

SEEDED_SOURCE = "demo_history"          # marker stamped into every seeded result payload
SEED_COVERAGE_THRESHOLD = 0.6           # seed only when < 60% of window days have a succeeded run

# Smoothed noise = a geometric (AR(1)-style) blend of the last few days' hash draws, so consecutive
# days correlate (an organic drift, not white static). Normalized to [-1, 1].
_NOISE_LAGS = 6
_NOISE_PHI = 0.55
_NOISE_NORM = (1 - _NOISE_PHI ** (_NOISE_LAGS + 1)) / (1 - _NOISE_PHI)

# Weekly rhythm per agent (Mon..Sun multipliers). Demand-driven metrics (booked calls, the dispatch
# board, office paperwork) dip on weekends; job-margin leakage and annualized vendor arbitrage are
# analysis outputs over the whole book, so they stay flat. Overtime builds through the week.
_WEEKLY: dict[str, tuple[float, ...]] = {
    "booking":   (1.00, 1.03, 1.00, 1.05, 1.08, 0.62, 0.50),
    "routing":   (1.05, 1.00, 1.02, 1.00, 0.95, 0.45, 0.30),
    "documents": (1.05, 1.00, 1.00, 0.95, 0.90, 0.35, 0.20),
    "financial": (1.00,) * 7,
    "inventory": (1.00,) * 7,
    "workforce": (0.70, 0.85, 1.00, 1.15, 1.30, 0.80, 0.40),
}

# agent -> ((totals field, baseline, noise amplitude, kind), ...). Baselines are the live fixture
# oracles (test_org_kpis.py) so seeded history meets today's real runs at the same level.
_FIELD_SPECS: dict[str, tuple[tuple[str, float, float, str], ...]] = {
    "booking":   (("recovered_revenue_usd", 3260.00, 0.15, "usd"),),
    "routing":   (("drive_minutes_saved", 60.0, 0.22, "count"),),
    "financial": (("total_leakage_usd", 14250.50, 0.10, "usd"),),
    "inventory": (("total_arbitrage_annual_usd", 1875.25, 0.06, "usd"),),
    "documents": (("extracted_value_usd", 2920.00, 0.18, "usd"),),
    "workforce": (("technicians_in_overtime", 3.0, 0.55, "count"),),
}

# Booking's after-hours figure is DERIVED from the day's recovered revenue so it can never invert
# the production invariant (after-hours is a strict subset of recovered — the rollup never re-adds
# it). Base share 2895/3260 ≈ 0.888, wobbled and clamped to a believable band.
_AFTER_HOURS_BASE_RATIO = 2895.00 / 3260.00
_AFTER_HOURS_WOBBLE = 0.05
_AFTER_HOURS_MIN, _AFTER_HOURS_MAX = 0.75, 0.95


def _unit_noise(tenant_slug: str, agent: str, field: str, day: date) -> float:
    """One deterministic draw in [-1, 1): SHA-256 over the fully-qualified stream key + day."""
    key = f"{tenant_slug}:{agent}:{field}:{day.isoformat()}".encode()
    draw = int.from_bytes(hashlib.sha256(key).digest()[:8], "big") / 2**64
    return 2.0 * draw - 1.0


def _smooth_noise(tenant_slug: str, agent: str, field: str, day: date) -> float:
    """Geometric blend of today's + the prior days' draws, normalized to [-1, 1]."""
    total = sum(
        _NOISE_PHI**lag * _unit_noise(tenant_slug, agent, field, day - timedelta(days=lag))
        for lag in range(_NOISE_LAGS + 1)
    )
    return total / _NOISE_NORM


def demo_run_history(tenant_slug: str, agent: str, day: date) -> dict:
    """A minimal deterministic succeeded-run payload for (tenant, agent, day).

    Contains exactly the ``totals.*`` fields the executive timeseries reads for the agent, plus a
    ``seeded``/``source`` marker so seeded rows stay distinguishable from real runs.
    """
    specs = _FIELD_SPECS.get(agent)
    if specs is None:
        raise ValueError(f"no demo-history spec for agent '{agent}'")
    weekly = _WEEKLY[agent][day.weekday()]
    totals: dict[str, float | int] = {}
    for field, base, amplitude, kind in specs:
        noise = _smooth_noise(tenant_slug, agent, field, day)
        raw = base * weekly * (1 + amplitude * noise)
        totals[field] = round(raw, 2) if kind == "usd" else max(0, round(raw))
    if agent == "booking":
        wobble = _smooth_noise(tenant_slug, agent, "after_hours_recovered_usd", day)
        ratio = _AFTER_HOURS_BASE_RATIO + _AFTER_HOURS_WOBBLE * wobble
        ratio = min(max(ratio, _AFTER_HOURS_MIN), _AFTER_HOURS_MAX)
        totals["after_hours_recovered_usd"] = round(totals["recovered_revenue_usd"] * ratio, 2)
    return {"agent": agent, "totals": totals, "seeded": True, "source": SEEDED_SOURCE}


def window_days(start: date, end: date) -> list[date]:
    """Every day in [start, end] inclusive (empty when start > end)."""
    if start > end:
        return []
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def needs_seeding(existing_days: Iterable[date], start: date, end: date) -> bool:
    """True when strictly fewer than SEED_COVERAGE_THRESHOLD of the window's days are covered."""
    days = window_days(start, end)
    if not days:
        return False
    covered = len({d for d in existing_days if start <= d <= end})
    return covered / len(days) < SEED_COVERAGE_THRESHOLD


def plan_seed_runs(
    tenant_slug: str,
    existing: Mapping[str, set[date]],
    start: date,
    end: date,
) -> list[tuple[str, date, dict]]:
    """The idempotent seed plan: [] when overall day coverage clears the sparsity gate; otherwise
    one (agent, day, payload) per charted agent per day that agent has no succeeded run for."""
    all_days = {day for days in existing.values() for day in days}
    if not needs_seeding(all_days, start, end):
        return []
    plan: list[tuple[str, date, dict]] = []
    for agent in CHARTED_AGENTS:
        have = existing.get(agent, set())
        for day in window_days(start, end):
            if day not in have:
                plan.append((agent, day, demo_run_history(tenant_slug, agent, day)))
    return plan
