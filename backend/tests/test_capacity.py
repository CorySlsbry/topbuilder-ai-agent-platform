"""Unit + property tests for the rolling per-(technician, job_type) capacity engine.

The scenarios are hand-computed so every asserted number is an independent oracle. The rolling estimate
is a time-decay (half-life) weighted mean, credibility-blended toward the job-type baseline by sample
size — a moving target that re-adjusts as new jobs complete.
"""
from __future__ import annotations

from datetime import date

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.agents.workforce import capacity as c
from app.agents.workforce.capacity import AssignedJob, CompletedJob, TechJobTypeDuration
from app.agents.workforce.models import Technician

AS_OF = date(2026, 6, 30)


# --------------------------------------------------------------------------------------------
# Pure primitives
# --------------------------------------------------------------------------------------------
class TestRecencyWeight:
    @pytest.mark.parametrize(
        "age, half_life, expected",
        [(0, 30, 1.0), (30, 30, 0.5), (60, 30, 0.25), (15, 30, 0.70710678)],
    )
    def test_known(self, age: float, half_life: float, expected: float) -> None:
        assert c.recency_weight(age, half_life) == pytest.approx(expected)

    def test_nonpositive_half_life_is_flat(self) -> None:
        assert c.recency_weight(100, 0) == 1.0

    @given(st.floats(0, 3650), st.floats(1, 365))
    def test_in_unit_interval(self, age: float, half_life: float) -> None:
        # Weight decays in [0, 1] (a very old job's weight can underflow to exactly 0.0 — fine; the
        # weighted mean treats an all-zero-weight set as "no signal"). Always 1.0 at age 0.
        assert 0.0 <= c.recency_weight(age, half_life) <= 1.0


class TestWeightedMean:
    def test_known(self) -> None:
        # (0.25*6 + 0.5*5 + 1.0*4) / 1.75 = 8.0 / 1.75
        assert c.weighted_mean([6, 5, 4], [0.25, 0.5, 1.0]) == pytest.approx(8.0 / 1.75)

    def test_no_weight_is_none(self) -> None:
        assert c.weighted_mean([1, 2], [0, 0]) is None
        assert c.weighted_mean([], []) is None

    @given(
        st.lists(st.floats(0, 100), min_size=1, max_size=8),
        st.data(),
    )
    def test_within_value_range(self, values: list[float], data: st.DataObject) -> None:
        weights = data.draw(
            st.lists(st.floats(0.01, 5), min_size=len(values), max_size=len(values))
        )
        m = c.weighted_mean(values, weights)
        assert min(values) - 1e-9 <= m <= max(values) + 1e-9


class TestCredibilityBlend:
    def test_known(self) -> None:
        # n=3, k=3 -> tech weight 0.5; (0.5*4.5714) + (0.5*5.5) = 5.0357
        assert c.credibility_blend(8.0 / 1.75, 5.5, 3, 3) == pytest.approx(5.0357142, abs=1e-4)

    def test_zero_samples_is_baseline(self) -> None:
        assert c.credibility_blend(2.0, 5.5, 0, 3) == 5.5

    @given(st.floats(0, 50), st.floats(0, 50), st.integers(1, 200))
    def test_between_tech_and_baseline(self, tech: float, baseline: float, n: int) -> None:
        out = c.credibility_blend(tech, baseline, n, 4.0)
        assert min(tech, baseline) - 1e-9 <= out <= max(tech, baseline) + 1e-9


class TestSampleConfidence:
    @pytest.mark.parametrize("n, expected", [(0, 0.0), (3, 0.5), (6, 0.75), (9, 0.875)])
    def test_known(self, n: int, expected: float) -> None:
        assert c.sample_confidence(n, 3) == pytest.approx(expected)


class TestOvertimeHours:
    @pytest.mark.parametrize("proj, contracted, expected", [(45, 40, 5), (38, 40, 0), (40, 40, 0)])
    def test_known(self, proj: float, contracted: float, expected: float) -> None:
        assert c.overtime_hours(proj, contracted) == expected


# --------------------------------------------------------------------------------------------
# estimate_tech_durations — the rolling, recency-weighted, credibility-blended estimate
# --------------------------------------------------------------------------------------------
def _completed() -> list[CompletedJob]:
    return [
        # T1 ac_install: 6h (60d ago) -> 5h (30d ago) -> 4h (today); recent dominates.
        CompletedJob("t1", "ac_install", "hvac", 6.0, date(2026, 5, 1)),
        CompletedJob("t1", "ac_install", "hvac", 5.0, date(2026, 5, 31)),
        CompletedJob("t1", "ac_install", "hvac", 4.0, date(2026, 6, 30)),
        # ac_repair has NO provided baseline -> derived from all techs: weighted mean of 2h + 6h = 4h.
        CompletedJob("t1", "ac_repair", "hvac", 2.0, date(2026, 6, 30)),
        CompletedJob("t2", "ac_repair", "hvac", 6.0, date(2026, 6, 30)),
    ]


def _estimates() -> dict[tuple[str, str], TechJobTypeDuration]:
    return c.estimate_tech_durations(
        _completed(), {"ac_install": 5.5}, as_of=AS_OF, half_life_days=30, min_samples=3, shrinkage_k=3
    )


class TestEstimateTechDurations:
    def test_rolling_estimate_is_recency_weighted(self) -> None:
        d = _estimates()[("t1", "ac_install")]
        # recency-weighted mean of 6/5/4 at weights 0.25/0.5/1.0 = 8/1.75 = 4.571
        assert d.rolling_hours == pytest.approx(4.571, abs=1e-3)
        assert d.baseline_hours == 5.5
        assert d.sample_size == 3
        assert d.confidence == pytest.approx(0.5)
        # blended toward baseline at n=3,k=3 -> 5.036
        assert d.estimate_hours == pytest.approx(5.036, abs=1e-3)
        # faster than baseline -> negative efficiency delta
        assert d.efficiency_delta_hours == pytest.approx(-0.464, abs=1e-3)

    def test_baseline_derived_from_data_when_not_provided(self) -> None:
        d = _estimates()[("t1", "ac_repair")]
        assert d.baseline_hours == pytest.approx(4.0)  # all-tech weighted mean of 2h + 6h
        # single sample (n=1) shrinks hard toward the baseline: 0.25*2 + 0.75*4 = 3.5
        assert d.sample_size == 1
        assert d.estimate_hours == pytest.approx(3.5)

    def test_estimate_is_between_rolling_and_baseline(self) -> None:
        for d in _estimates().values():
            lo, hi = sorted((d.rolling_hours, d.baseline_hours))
            assert lo - 1e-6 <= d.estimate_hours <= hi + 1e-6


# --------------------------------------------------------------------------------------------
# project_tech_overtime — proactive OT detection + same-trade redistribution
# --------------------------------------------------------------------------------------------
def _project():
    techs = [
        Technician("t1", "Tech 1", "hvac", 40, 50, 1.5),
        Technician("t2", "Tech 2", "hvac", 40, 50, 1.5),
    ]
    durations = {
        ("t1", "ac_install"): TechJobTypeDuration("t1", "ac_install", "hvac", 9.0, 9.0, 8.5, 8, 0.8, 0.5),
        ("t2", "ac_install"): TechJobTypeDuration("t2", "ac_install", "hvac", 8.0, 8.0, 8.5, 8, 0.7, -0.5),
    }
    assigned = (
        [AssignedJob("t1", "ac_install", "hvac")] * 5  # 5 * 9.0 = 45h -> 5h OT
        + [AssignedJob("t2", "ac_install", "hvac")] * 2  # 2 * 8.0 = 16h
        + [AssignedJob("t2", "mystery", "hvac")]  # no estimate/baseline -> DEFAULT_JOB_HOURS (2.0)
    )
    return c.project_tech_overtime(techs, assigned, durations, {"ac_install": 8.5})


class TestProjectTechOvertime:
    def test_overloaded_tech_flags_overtime(self) -> None:
        t1 = next(p for p in _project() if p.technician_id == "t1")
        assert t1.projected_hours == pytest.approx(45.0)
        assert t1.overtime_hours == pytest.approx(5.0)
        assert t1.confidence == pytest.approx(0.8)

    def test_overtime_routes_to_a_same_trade_tech_with_slack(self) -> None:
        t1 = next(p for p in _project() if p.technician_id == "t1")
        assert t1.redistribute_to == ["t2"]  # t2 projects 18h << 40h, same trade

    def test_slack_tech_has_no_overtime_and_uses_default_for_unknown_type(self) -> None:
        t2 = next(p for p in _project() if p.technician_id == "t2")
        # 2*8.0 (ac_install) + 2.0 (mystery -> DEFAULT_JOB_HOURS) = 18.0
        assert t2.projected_hours == pytest.approx(18.0)
        assert t2.overtime_hours == 0.0
        assert t2.redistribute_to == []

    def test_sorted_overtime_first(self) -> None:
        ids = [p.technician_id for p in _project()]
        assert ids == ["t1", "t2"]
