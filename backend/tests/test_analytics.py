"""Unit + property tests for the deterministic workforce analytics engine.

The `analyze()` scenario below is hand-computed so every asserted number is an independent oracle.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.agents.workforce import analytics as a
from app.agents.workforce.models import (
    Appointment,
    DemandSignal,
    JobDurationStat,
    Technician,
    TradeEconomics,
    WorkforceData,
)

AS_OF = date(2026, 6, 1)  # a Monday


# --------------------------------------------------------------------------------------------
# Pure primitives
# --------------------------------------------------------------------------------------------
class TestProjectOvertimeHours:
    @pytest.mark.parametrize(
        "scheduled, contracted, expected",
        [(50, 40, 10), (40, 40, 0), (30, 40, 0), (46.5, 40, 6.5)],
    )
    def test_known(self, scheduled: float, contracted: float, expected: float) -> None:
        assert a.project_overtime_hours(scheduled, contracted) == pytest.approx(expected)

    @given(st.floats(0, 200), st.floats(1, 80))
    def test_never_negative(self, scheduled: float, contracted: float) -> None:
        assert a.project_overtime_hours(scheduled, contracted) >= 0.0

    @given(st.floats(0, 80), st.floats(0, 80))
    def test_additive_decomposition(self, scheduled: float, contracted: float) -> None:
        # scheduled == regular + overtime, with regular capped at contracted
        ot = a.project_overtime_hours(scheduled, contracted)
        regular = min(scheduled, contracted)
        assert regular + ot == pytest.approx(scheduled)


class TestOvertimePremiumCents:
    def test_time_and_a_half(self) -> None:
        # 10h at $50/h, 1.5x -> premium is the EXTRA 0.5x = 10*50*0.5 = $250 = 25000 cents
        assert a.overtime_premium_cents(10, 50, 1.5) == 25_000

    @given(st.floats(0, 60), st.floats(0, 200), st.floats(1.0, 3.0))
    def test_non_negative(self, hours: float, cost: float, mult: float) -> None:
        assert a.overtime_premium_cents(hours, cost, mult) >= 0


class TestGapCount:
    @pytest.mark.parametrize(
        "gap, per_tech, expected",
        [(56, 32, 2), (14.8, 34, 1), (0, 32, 0), (32, 32, 1), (33, 32, 2)],
    )
    def test_known(self, gap: float, per_tech: float, expected: int) -> None:
        assert a.gap_count(gap, per_tech) == expected

    @given(st.floats(0, 500), st.floats(1, 60))
    def test_enough_to_cover(self, gap: float, per_tech: float) -> None:
        assert a.gap_count(gap, per_tech) * per_tech + 1e-9 >= gap


# --------------------------------------------------------------------------------------------
# Scenario for analyze(): 1 trade, 2 techs, 2 weeks. Week 2 is short AND drives overtime.
# --------------------------------------------------------------------------------------------
def _scenario() -> WorkforceData:
    techs = [
        Technician("tA", "Tech A", "hvac", 40, 50, 1.5),
        Technician("tB", "Tech B", "hvac", 40, 50, 1.5),
    ]
    econ = [TradeEconomics("hvac", billable_rate=150, availability_factor=0.80)]
    durations = [JobDurationStat("ac_repair", "hvac", 2.5, 0.8, 500, 0.9)]
    demand = [
        DemandSignal("hvac", 0, 1.0),
        DemandSignal("hvac", 1, 1.5),
    ]
    appts = [
        Appointment("a1", "j1", "hvac", AS_OF + timedelta(days=1), 30, "ac_repair", "tA"),
        Appointment("a2", "j2", "hvac", AS_OF + timedelta(days=1), 30, "ac_repair", "tB"),
        Appointment("a3", "j3", "hvac", AS_OF + timedelta(days=8), 50, "ac_repair", "tA"),
        Appointment("a4", "j4", "hvac", AS_OF + timedelta(days=8), 30, "ac_repair", "tB"),
    ]
    return WorkforceData(
        as_of=AS_OF,
        horizon_days=14,
        technicians=techs,
        appointments=appts,
        timesheets=[],
        job_durations=durations,
        demand_signals=demand,
        trade_economics=econ,
    )


class TestAnalyzeUnderstaffing:
    def test_exactly_one_understaffing_risk_in_week_1(self) -> None:
        result = a.analyze(_scenario())
        assert len(result.understaffing_risks) == 1
        risk = result.understaffing_risks[0]
        assert (risk.trade, risk.week_offset) == ("hvac", 1)

    def test_week_1_numbers(self) -> None:
        # available = 2*40*0.80 = 64 ; booked = 80 ; projected = 80*1.5 = 120 ; gap = 56
        risk = a.analyze(_scenario()).understaffing_risks[0]
        assert risk.available_hours == pytest.approx(64.0)
        assert risk.booked_hours == pytest.approx(80.0)
        assert risk.projected_required_hours == pytest.approx(120.0)
        assert risk.gap_hours == pytest.approx(56.0)
        # added capacity per tech = 40*0.80 = 32 -> ceil(56/32) = 2
        assert risk.gap_count == 2
        # contribution margin = 150 - 50 = 100 ; impact = 56 * 100 = $5,600
        assert risk.economic_impact_cents == 560_000
        # horizon_decay(1)=0.92 * data_support(500,0.9)=0.95 -> 0.874
        assert risk.confidence == pytest.approx(0.874, abs=1e-3)


class TestAnalyzeOvertime:
    def test_only_tech_a_has_overtime(self) -> None:
        result = a.analyze(_scenario())
        assert [r.technician_id for r in result.overtime_risks] == ["tA"]

    def test_tech_a_overtime_numbers(self) -> None:
        risk = a.analyze(_scenario()).overtime_risks[0]
        # week 1: scheduled 50, contracted 40 -> 10 OT hours (week 0 is 30 -> none)
        assert risk.projected_overtime_hours == pytest.approx(10.0)
        # premium = 10 * 50 * 0.5 = $250
        assert risk.economic_impact_cents == 25_000
        # tech B averages < contracted -> a redistribution candidate
        assert "tB" in risk.mitigation_candidates
        assert risk.confidence == pytest.approx(0.828, abs=1e-3)


class TestAnalyzeMeta:
    def test_inputs_hash_is_stable_and_hex(self) -> None:
        h1 = a.analyze(_scenario()).inputs_hash
        h2 = a.analyze(_scenario()).inputs_hash
        assert h1 == h2
        assert len(h1) == 64 and all(ch in "0123456789abcdef" for ch in h1)

    def test_utilization_covers_every_trade_week(self) -> None:
        result = a.analyze(_scenario())
        assert {(u.trade, u.week_offset) for u in result.utilization} == {("hvac", 0), ("hvac", 1)}

    @given(st.integers(min_value=1, max_value=4))
    def test_horizon_weeks_controls_utilization_rows(self, weeks: int) -> None:
        data = _scenario()
        result = a.analyze(data, weeks=weeks)
        assert len(result.utilization) == weeks  # one trade x `weeks` weeks
