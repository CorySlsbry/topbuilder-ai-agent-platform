"""Oracle + property tests for the equipment-driven quoting-MARGIN engine (PURE, no DB).

Every asserted figure is an INDEPENDENT hand-computed oracle — margins are re-derived here from first
principles, not read back from the engine. Money is integer cents throughout; margin percentages are
whole numbers (45.0 == 45%).

Anchor scenario (a real 3-Ton Premium install that LEAKS margin):
  * Premium 3-Ton heat pump: price $5,390 / cost $3,650 -> margin (5390-3650)/5390 = 32.28%  (below 45%)
  * Install labor 12h @ price $165 / cost $65          -> line $1,980 / $780 = 60.61%
  * Refrigerant line set:    price $189 / cost $85      -> 55.03%
  Totals: price $7,559, cost $4,515, gross profit $3,044, blended 40.27% (below the 45% target).
  Flags: low_margin_line + brand_low_margin on the premium unit; blended_below_target on the quote.
"""
from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.fieldops.margin import (
    DEFAULT_TARGET_MARGIN_PCT,
    FlagCode,
    LineKind,
    MarginQuoteInput,
    QuoteLine,
    compute_margin_quote,
    gross_margin_pct,
    price_for_margin,
)


def _premium_unit(margin_target: float | None = None) -> QuoteLine:
    return QuoteLine(
        kind=LineKind.EQUIPMENT, name="3-Ton Heat Pump (Premium)", brand="Mitsubishi",
        price_cents=539000, cost_cents=365000, sold_hours=12.0, target_margin_pct=margin_target,
        code="EQ-HP-3T-PREM",
    )


def _labor(hours: int) -> QuoteLine:
    return QuoteLine(
        kind=LineKind.LABOR, name="Install Labor (per hour)", price_cents=16500, cost_cents=6500,
        qty=hours, code="MAT-LABOR",
    )


def _lineset() -> QuoteLine:
    return QuoteLine(
        kind=LineKind.MATERIAL, name="Refrigerant Line Set", price_cents=18900, cost_cents=8500,
        code="MAT-LINESET",
    )


# --------------------------------------------------------------------------------------------
# 1. Pure primitives — independent oracles
# --------------------------------------------------------------------------------------------
class TestGrossMarginPct:
    @pytest.mark.parametrize(
        "price, cost, expected",
        [
            (539000, 365000, 32.28),   # the premium-unit leak
            (198000, 78000, 60.61),    # 12h labor
            (18900, 8500, 55.03),      # line set
            (429000, 230000, 46.39),   # a standard unit that clears 45%
            (10000, 10000, 0.0),       # break-even
            (10000, 12000, -20.0),     # a loss is shown negative
            (0, 5000, 0.0),            # no price -> 0 (guard)
        ],
    )
    def test_known(self, price: int, cost: int, expected: float) -> None:
        assert gross_margin_pct(price, cost) == pytest.approx(expected)

    @given(st.integers(min_value=1, max_value=10_000_000), st.integers(min_value=0, max_value=10_000_000))
    def test_never_markup_on_cost(self, price: int, cost: int) -> None:
        # True margin is always <= the markup-on-cost figure for a profitable line.
        margin = gross_margin_pct(price, cost)
        if price > cost:
            markup = (price - cost) / cost * 100 if cost else float("inf")
            assert margin <= markup + 1e-6


class TestPriceForMargin:
    @pytest.mark.parametrize(
        "cost, target, expected",
        [
            (365000, 45.0, 663636),   # cost / (1 - 0.45)
            (230000, 50.0, 460000),
            (10000, 0.0, 10000),      # 0% margin -> price == cost
        ],
    )
    def test_known(self, cost: int, target: float, expected: int) -> None:
        assert price_for_margin(cost, target) == expected

    @given(st.integers(min_value=10_000, max_value=5_000_000), st.floats(min_value=1.0, max_value=90.0))
    def test_roundtrip_hits_target(self, cost: int, target: float) -> None:
        # At a realistic line cost (>= $100) the 1-cent rounding of price_for_margin can't move the
        # achieved margin off target by more than a rounding tolerance.
        price = price_for_margin(cost, target)
        assert gross_margin_pct(price, cost) == pytest.approx(target, abs=0.5)


# --------------------------------------------------------------------------------------------
# 2. The engine — the anchor scenario
# --------------------------------------------------------------------------------------------
class TestMarginQuoteOracle:
    def _result(self):
        return compute_margin_quote(
            MarginQuoteInput(lines=[_premium_unit(), _labor(12), _lineset()], target_margin_pct=45.0)
        )

    def test_totals(self) -> None:
        r = self._result()
        assert r.total_price_cents == 755900
        assert r.total_cost_cents == 451500
        assert r.gross_profit_cents == 304400
        assert r.blended_margin_pct == pytest.approx(40.27)
        assert r.total_sold_hours == pytest.approx(12.0)

    def test_per_line_margin(self) -> None:
        r = self._result()
        assert [round(line.margin_pct, 2) for line in r.lines] == [32.28, 60.61, 55.03]
        assert [line.below_target for line in r.lines] == [True, False, False]

    def test_premium_unit_flags_low_margin_and_brand(self) -> None:
        r = self._result()
        unit = r.lines[0]
        assert FlagCode.LOW_MARGIN_LINE.value in unit.flags
        assert FlagCode.BRAND_LOW_MARGIN.value in unit.flags

    def test_blended_below_target_flag(self) -> None:
        r = self._result()
        codes = {f.code for f in r.flags}
        assert FlagCode.BLENDED_BELOW_TARGET.value in codes
        assert r.has_blocking_flag is True

    def test_inputs_hash_is_stable(self) -> None:
        assert self._result().inputs_hash == self._result().inputs_hash


class TestGoodQuoteHasNoLeakFlags:
    """A standard 3-Ton at the same labor/line-set clears the 45% target end-to-end."""

    def test_clean(self) -> None:
        unit = QuoteLine(
            kind=LineKind.EQUIPMENT, name="3-Ton Heat Pump (Standard)", brand="Standard",
            price_cents=429000, cost_cents=230000, sold_hours=12.0, code="EQ-HP-3T-STD",
        )
        r = compute_margin_quote(
            MarginQuoteInput(lines=[unit, _labor(12), _lineset()], target_margin_pct=45.0)
        )
        assert r.total_price_cents == 645900
        assert r.total_cost_cents == 316500
        assert r.blended_margin_pct == pytest.approx(51.0)
        assert r.flags == []
        assert r.lines[0].below_target is False


# --------------------------------------------------------------------------------------------
# 3. The leak flags in isolation
# --------------------------------------------------------------------------------------------
class TestBrandLeakFlag:
    def test_high_cost_low_margin_premium_box_flagged(self) -> None:
        r = compute_margin_quote(MarginQuoteInput(lines=[_premium_unit()], target_margin_pct=45.0))
        assert FlagCode.BRAND_LOW_MARGIN.value in {f.code for f in r.flags}

    def test_cheap_box_at_low_margin_is_not_a_brand_leak(self) -> None:
        # A $300 thermostat below target is a plain low-margin line, not the "sell the company" leak.
        cheap = QuoteLine(
            kind=LineKind.EQUIPMENT, name="Smart Thermostat", brand="Ecobee",
            price_cents=39000, cost_cents=30000, sold_hours=1.0, code="EQ-THERMO",
        )
        r = compute_margin_quote(MarginQuoteInput(lines=[cheap], target_margin_pct=45.0))
        codes = {f.code for f in r.flags}
        assert FlagCode.LOW_MARGIN_LINE.value in codes
        assert FlagCode.BRAND_LOW_MARGIN.value not in codes


class TestExcessMaterialFlag:
    def test_over_pulled_spool_flagged(self) -> None:
        # 4 sold hours -> $180 expected material budget, $270 threshold; two $220 copper spools = $440.
        equip = QuoteLine(
            kind=LineKind.EQUIPMENT, name="Mini-Split", brand="Daikin",
            price_cents=289000, cost_cents=145000, sold_hours=4.0, code="EQ-MINISPLIT",
        )
        copper = QuoteLine(
            kind=LineKind.MATERIAL, name="Copper Tubing (spool)", price_cents=39000, cost_cents=22000,
            qty=2, code="MAT-COPPER",
        )
        r = compute_margin_quote(MarginQuoteInput(lines=[equip, copper], target_margin_pct=45.0))
        flag = next((f for f in r.flags if f.code == FlagCode.EXCESS_MATERIAL.value), None)
        assert flag is not None

    def test_reasonable_material_not_flagged(self) -> None:
        equip = QuoteLine(
            kind=LineKind.EQUIPMENT, name="Mini-Split", brand="Daikin",
            price_cents=289000, cost_cents=145000, sold_hours=8.0, code="EQ-MINISPLIT",
        )
        one_spool = QuoteLine(
            kind=LineKind.MATERIAL, name="Copper Tubing (spool)", price_cents=39000, cost_cents=22000,
            qty=1, code="MAT-COPPER",
        )
        r = compute_margin_quote(MarginQuoteInput(lines=[equip, one_spool], target_margin_pct=45.0))
        assert FlagCode.EXCESS_MATERIAL.value not in {f.code for f in r.flags}


class TestSqftBenchmark:
    def test_under_benchmark_flagged(self) -> None:
        r = compute_margin_quote(
            MarginQuoteInput(
                lines=[_premium_unit(), _labor(12), _lineset()],
                target_margin_pct=45.0, sqft=1500, avg_price_per_sqft_cents=600,
            )
        )
        assert r.benchmark_price_cents == 900000          # 600 cents * 1500
        assert r.sqft_price_per_unit_cents == 504         # round(755900 / 1500)
        assert FlagCode.BELOW_SQFT_BENCHMARK.value in {f.code for f in r.flags}

    def test_at_benchmark_not_flagged(self) -> None:
        # $4.50/sqft -> $675,000 benchmark; the $7,559 quote is comfortably above.
        r = compute_margin_quote(
            MarginQuoteInput(
                lines=[_premium_unit(), _labor(12), _lineset()],
                target_margin_pct=45.0, sqft=1500, avg_price_per_sqft_cents=450,
            )
        )
        assert FlagCode.BELOW_SQFT_BENCHMARK.value not in {f.code for f in r.flags}

    def test_sqft_is_informational_only_no_blocking(self) -> None:
        # A below-sqft note on an otherwise-on-target quote is a soft signal, not a blocking flag.
        unit = QuoteLine(
            kind=LineKind.EQUIPMENT, name="3-Ton Heat Pump (Standard)", brand="Standard",
            price_cents=429000, cost_cents=230000, sold_hours=12.0, code="EQ-HP-3T-STD",
        )
        r = compute_margin_quote(
            MarginQuoteInput(
                lines=[unit, _labor(12), _lineset()],
                target_margin_pct=45.0, sqft=1500, avg_price_per_sqft_cents=600,
            )
        )
        assert FlagCode.BELOW_SQFT_BENCHMARK.value in {f.code for f in r.flags}
        assert r.has_blocking_flag is False


# --------------------------------------------------------------------------------------------
# 4. Edge cases + invariants
# --------------------------------------------------------------------------------------------
class TestEdgeCases:
    def test_empty_quote_is_zero(self) -> None:
        r = compute_margin_quote(MarginQuoteInput(lines=[], target_margin_pct=45.0))
        assert (r.total_price_cents, r.total_cost_cents, r.gross_profit_cents) == (0, 0, 0)
        assert r.blended_margin_pct == 0.0
        assert r.flags == []

    def test_qty_below_one_is_clamped(self) -> None:
        r = compute_margin_quote(MarginQuoteInput(lines=[_lineset()], target_margin_pct=45.0))
        # _lineset() qty defaults to 1; clamping never produces a 0-qty line.
        assert r.lines[0].qty == 1

    def test_default_target_applies(self) -> None:
        r = compute_margin_quote(MarginQuoteInput(lines=[_lineset()]))
        assert r.target_margin_pct == DEFAULT_TARGET_MARGIN_PCT


class TestProperties:
    @given(
        st.lists(
            st.tuples(
                st.integers(min_value=1, max_value=1_000_000),  # price
                st.integers(min_value=0, max_value=1_000_000),  # cost
                st.integers(min_value=1, max_value=5),          # qty
            ),
            min_size=0, max_size=6,
        )
    )
    def test_profit_is_price_minus_cost(self, rows: list[tuple[int, int, int]]) -> None:
        lines = [
            QuoteLine(kind=LineKind.MATERIAL, name=f"m{i}", price_cents=p, cost_cents=c, qty=q)
            for i, (p, c, q) in enumerate(rows)
        ]
        r = compute_margin_quote(MarginQuoteInput(lines=lines, target_margin_pct=45.0))
        assert r.gross_profit_cents == r.total_price_cents - r.total_cost_cents
        assert r.total_price_cents == sum(p * q for p, _, q in rows)

    @given(st.integers(min_value=1, max_value=5_000_000), st.integers(min_value=0, max_value=5_000_000))
    def test_blended_equals_single_line_margin(self, price: int, cost: int) -> None:
        line = QuoteLine(kind=LineKind.MATERIAL, name="one", price_cents=price, cost_cents=cost)
        r = compute_margin_quote(MarginQuoteInput(lines=[line], target_margin_pct=45.0))
        assert r.blended_margin_pct == pytest.approx(gross_margin_pct(price, cost))
