"""Unit + property tests for the deterministic confidence scorer."""
from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.agents.workforce import confidence as c


class TestHorizonDecay:
    @pytest.mark.parametrize(
        "week, expected",
        [(0, 1.0), (1, 0.92), (2, 0.84), (3, 0.76)],
    )
    def test_known_values(self, week: int, expected: float) -> None:
        assert c.horizon_decay(week) == pytest.approx(expected)

    def test_clamps_at_floor_for_distant_horizon(self) -> None:
        assert c.horizon_decay(99) == pytest.approx(c.MIN_HORIZON_DECAY)

    @given(st.integers(min_value=0, max_value=200))
    def test_within_bounds(self, week: int) -> None:
        assert c.MIN_HORIZON_DECAY <= c.horizon_decay(week) <= 1.0

    @given(st.integers(min_value=0, max_value=200))
    def test_monotonic_non_increasing(self, week: int) -> None:
        assert c.horizon_decay(week + 1) <= c.horizon_decay(week) + 1e-9


class TestDataSupport:
    @pytest.mark.parametrize(
        "samples, completion, expected",
        [
            (500, 0.9, 0.95),   # saturated samples + high completion
            (0, 0.8, 0.40),     # no samples -> only the completion half contributes
            (250, 1.0, 0.75),   # half-saturated, perfect completion
            (1000, 0.5, 0.75),  # over-saturated (capped), mediocre completion
        ],
    )
    def test_known_values(self, samples: int, completion: float, expected: float) -> None:
        assert c.data_support(samples, completion) == pytest.approx(expected)

    @given(st.integers(min_value=0, max_value=10_000), st.floats(min_value=0.0, max_value=1.0))
    def test_within_unit_interval(self, samples: int, completion: float) -> None:
        assert 0.0 <= c.data_support(samples, completion) <= 1.0

    @given(
        st.integers(min_value=0, max_value=10_000),
        st.integers(min_value=0, max_value=10_000),
        st.floats(min_value=0.0, max_value=1.0),
    )
    def test_monotonic_in_samples(self, a: int, b: int, completion: float) -> None:
        lo, hi = min(a, b), max(a, b)
        assert c.data_support(lo, completion) <= c.data_support(hi, completion) + 1e-9


class TestUnderstaffingConfidence:
    def test_known_value(self) -> None:
        # horizon_decay(1)=0.92, data_support(500,0.9)=0.95 -> 0.874
        assert c.understaffing_confidence(1, 500, 0.9) == pytest.approx(0.874, abs=1e-3)

    @given(
        st.integers(min_value=0, max_value=12),
        st.integers(min_value=0, max_value=5_000),
        st.floats(min_value=0.0, max_value=1.0),
    )
    def test_within_unit_interval(self, week: int, samples: int, completion: float) -> None:
        assert 0.0 <= c.understaffing_confidence(week, samples, completion) <= 1.0

    @given(st.integers(min_value=0, max_value=11), st.integers(0, 5000), st.floats(0.0, 1.0))
    def test_confidence_decays_with_horizon(self, week: int, samples: int, completion: float) -> None:
        nearer = c.understaffing_confidence(week, samples, completion)
        farther = c.understaffing_confidence(week + 1, samples, completion)
        assert farther <= nearer + 1e-9


class TestOvertimeConfidence:
    @pytest.mark.parametrize("week, expected", [(0, 0.9), (1, 0.828), (2, 0.756)])
    def test_known_values(self, week: int, expected: float) -> None:
        assert c.overtime_confidence(week) == pytest.approx(expected, abs=1e-3)

    @given(st.integers(min_value=0, max_value=50))
    def test_within_unit_interval(self, week: int) -> None:
        assert 0.0 <= c.overtime_confidence(week) <= 1.0
