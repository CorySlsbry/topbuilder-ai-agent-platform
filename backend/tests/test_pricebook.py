"""Oracle + property tests for the deterministic Pricebook re-pricing engine (PURE, no DB).

Every asserted figure is an INDEPENDENT hand-computed oracle. Money is carried as integer **cents** in
the inputs; the engine keeps cents, so cent oracles are exact (no float division). The pricing model is
Alex's sold-hour formula (verbatim):

    price = sold_hours * sold_hour_rate + materials_cost + (materials_cost * material_markup)

where materials_cost = sum over the item's material lines of (qty * vendor_unit_cost). When a vendor
publishes new unit costs, the engine recomputes each affected item's materials_cost, then its price, and
surfaces the old->new deltas + the margin impact, flagging items whose price moves beyond a tolerance.

The ``_scenario()`` mirrors a residential HVAC pricebook (copper, refrigerant, sheet metal, fittings,
a condenser, a line set) with a quarterly vendor price update.
"""
from __future__ import annotations

from datetime import date

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.agents.pricebook import analytics as a
from app.agents.pricebook.models import (
    MaterialLine,
    PricebookData,
    PricebookItem,
    VendorPriceUpdate,
)

AS_OF = date(2026, 6, 15)


# --------------------------------------------------------------------------------------------
# 1. Pure primitives — materials cost + sold-hour price
# --------------------------------------------------------------------------------------------
class TestMaterialsCost:
    def test_sums_qty_times_unit_cost(self) -> None:
        lines = [
            MaterialLine(sku="CU-34", qty=4, unit_cost_cents=5_000),   # 4 * $50 = $200
            MaterialLine(sku="R410A", qty=2, unit_cost_cents=5_000),   # 2 * $50 = $100
        ]
        # $200 + $100 = $300
        assert a.materials_cost_cents(lines) == 30_000

    def test_empty_lines_is_zero(self) -> None:
        assert a.materials_cost_cents([]) == 0

    def test_fractional_quantities_round_half_up_to_cents(self) -> None:
        # 1.5 units * $33.33 = $49.995 -> 4_999.5 cents -> rounds to 5_000 (banker's-safe half-up)
        lines = [MaterialLine(sku="X", qty=1.5, unit_cost_cents=3_333)]
        assert a.materials_cost_cents(lines) == 5_000


class TestSoldHourPrice:
    def test_alex_formula_oracle(self) -> None:
        # sold_hours=2, rate=$120 -> labor $240; materials $300 at 25% markup -> $300 + $75 = $375.
        # price = 240 + 300 + 75 = $615.00
        price = a.price_cents(
            sold_hours=2.0, sold_hour_rate_cents=12_000, materials_cost_cents=30_000, markup_pct=25.0
        )
        assert price == 61_500

    def test_zero_markup_is_labor_plus_materials(self) -> None:
        # 1h * $100 + $50 materials + 0 markup = $150
        assert a.price_cents(1.0, 10_000, 5_000, 0.0) == 15_000

    def test_zero_materials_is_pure_labor(self) -> None:
        # 3h * $90 + $0 + 0 = $270
        assert a.price_cents(3.0, 9_000, 0, 50.0) == 27_000


# --------------------------------------------------------------------------------------------
# 2. Scenario — a residential HVAC pricebook + a quarterly vendor price update
#   AC Install (P-AC): 8h @ $150 = $1,200 labor; materials = condenser 1*$1,800 + line set
#       1*$120 + R410A 4*$50 + copper 20*$5 = 1,800 + 120 + 200 + 100 = $2,220;
#       markup 20% -> materials portion = 2,220 + 444 = $2,664; price = 1,200 + 2,664 = $3,864
#   Duct Repair (P-DUCT): 2h @ $120 = $240 labor; materials = sheet metal 6*$30 + fittings 10*$8
#       = 180 + 80 = $260; markup 25% -> 260 + 65 = $325; price = 240 + 325 = $565
#   Tune-Up (P-TUNE): 1h @ $110 = $110 labor; NO materials; markup 25% -> $0; price = $110
#
#   Vendor update raises COPPER $5.00 -> $6.50/ft (+$1.50) and R410A $50 -> $62/lb (+$12).
#   Only P-AC uses both; P-DUCT + P-TUNE use neither -> unchanged.
#   New P-AC materials = 1,800 + 120 + (4*62=248) + (20*6.50=130) = $2,298 (was $2,220)
#       -> +$78 materials; +20% markup -> materials portion 2,298 + 459.60 = $2,757.60
#       -> new price = 1,200 + 2,757.60 = $3,957.60 (was $3,864) -> +$93.60 (+2.42% of $3,864)
# --------------------------------------------------------------------------------------------
def _scenario() -> PricebookData:
    items = [
        PricebookItem(
            code="P-AC", name="AC System Install", category="Install",
            sold_hours=8.0, sold_hour_rate_cents=15_000, markup_pct=20.0,
            current_price_cents=386_400,  # the existing sheet price; engine recomputes the baseline
            material_lines=[
                MaterialLine(sku="COND-3T", qty=1, unit_cost_cents=180_000),  # $1,800 condenser
                MaterialLine(sku="LINESET", qty=1, unit_cost_cents=12_000),   # $120 line set
                MaterialLine(sku="R410A", qty=4, unit_cost_cents=5_000),      # 4 lb @ $50
                MaterialLine(sku="CU-34", qty=20, unit_cost_cents=500),       # 20 ft @ $5
            ],
        ),
        PricebookItem(
            code="P-DUCT", name="Duct Repair", category="Service",
            sold_hours=2.0, sold_hour_rate_cents=12_000, markup_pct=25.0,
            current_price_cents=56_500,
            material_lines=[
                MaterialLine(sku="SHEET", qty=6, unit_cost_cents=3_000),    # 6 @ $30
                MaterialLine(sku="FITTING", qty=10, unit_cost_cents=800),   # 10 @ $8
            ],
        ),
        PricebookItem(
            code="P-TUNE", name="Seasonal Tune-Up", category="Maintenance",
            sold_hours=1.0, sold_hour_rate_cents=11_000, markup_pct=25.0,
            current_price_cents=11_000, material_lines=[],
        ),
    ]
    updates = [
        VendorPriceUpdate(sku="CU-34", vendor="Ferguson", new_unit_cost_cents=650,
                          effective_date=date(2026, 7, 1)),
        VendorPriceUpdate(sku="R410A", vendor="Ferguson", new_unit_cost_cents=6_200,
                          effective_date=date(2026, 7, 1)),
    ]
    return PricebookData(as_of=AS_OF, items=items, updates=updates, price_change_tolerance_pct=2.0)


def _change(analysis: a.PricebookAnalysis, code: str) -> a.PricebookItemChange:
    return next(c for c in analysis.changes if c.code == code)


class TestRepricing:
    def test_ac_install_baseline_price_matches_formula(self) -> None:
        c = _change(a.analyze(_scenario()), "P-AC")
        # old materials = $2,220; old price = $3,864 (the engine recomputes the baseline from the model)
        assert c.old_materials_cost_cents == 222_000
        assert c.old_price_cents == 386_400
        assert c.labor_cost_cents == 120_000  # 8h * $150

    def test_ac_install_reprices_on_copper_and_refrigerant_update(self) -> None:
        c = _change(a.analyze(_scenario()), "P-AC")
        assert c.new_materials_cost_cents == 229_800  # $2,298
        assert c.materials_delta_cents == 7_800        # +$78 (copper +$30, refrigerant +$48)
        assert c.new_price_cents == 395_760            # $3,957.60
        assert c.price_delta_cents == 9_360            # +$93.60
        assert set(c.changed_skus) == {"CU-34", "R410A"}

    def test_unaffected_items_have_zero_delta(self) -> None:
        analysis = a.analyze(_scenario())
        duct = _change(analysis, "P-DUCT")
        tune = _change(analysis, "P-TUNE")
        assert duct.price_delta_cents == 0 and duct.changed_skus == []
        assert tune.price_delta_cents == 0 and tune.new_price_cents == 11_000

    def test_margin_impact_is_recorded(self) -> None:
        # margin = price - cost (labor + materials at cost). For P-AC at-cost = labor 120,000 + materials.
        c = _change(a.analyze(_scenario()), "P-AC")
        # old margin = old_price - (labor + old_materials) = 386,400 - (120,000 + 222,000) = 44,400
        assert c.old_margin_cents == 44_400
        # new margin = 395,760 - (120,000 + 229,800) = 45,960 (the 20% markup IS the margin)
        assert c.new_margin_cents == 45_960
        assert c.margin_delta_cents == 1_560

    def test_tolerance_flag(self) -> None:
        analysis = a.analyze(_scenario())
        # P-AC moved +$93.60 / $3,864 = +2.42% > 2% tolerance -> flagged
        assert _change(analysis, "P-AC").beyond_tolerance is True
        # P-DUCT / P-TUNE unchanged (0%) -> not flagged
        assert _change(analysis, "P-DUCT").beyond_tolerance is False
        assert _change(analysis, "P-TUNE").beyond_tolerance is False


class TestTotals:
    def test_items_affected_counts_only_changed(self) -> None:
        t = a.analyze(_scenario()).totals
        assert t.items == 3
        assert t.items_affected == 1  # only P-AC

    def test_total_price_delta_oracle(self) -> None:
        t = a.analyze(_scenario()).totals
        assert t.total_price_delta_cents == 9_360  # only P-AC moved, +$93.60

    def test_vendor_coverage_oracle(self) -> None:
        t = a.analyze(_scenario()).totals
        # distinct SKUs across the pricebook: COND-3T, LINESET, R410A, CU-34, SHEET, FITTING = 6
        # SKUs the vendor update covers: CU-34, R410A = 2 -> 2/6 = 33.33%
        assert t.distinct_skus == 6
        assert t.skus_updated == 2
        assert t.vendor_coverage_pct == pytest.approx(33.33, abs=0.01)

    def test_avg_markup_oracle(self) -> None:
        t = a.analyze(_scenario()).totals
        # (20 + 25 + 25) / 3 = 23.333...
        assert t.avg_markup_pct == pytest.approx(23.33, abs=0.01)

    def test_items_flagged_count(self) -> None:
        t = a.analyze(_scenario()).totals
        assert t.items_flagged == 1  # P-AC beyond tolerance


class TestInvariants:
    def test_changes_sorted_by_largest_price_move_first(self) -> None:
        changes = a.analyze(_scenario()).changes
        moves = [abs(c.price_delta_cents) for c in changes]
        assert moves == sorted(moves, reverse=True)
        assert changes[0].code == "P-AC"

    def test_inputs_hash_stable_and_hex(self) -> None:
        h1 = a.analyze(_scenario()).inputs_hash
        h2 = a.analyze(_scenario()).inputs_hash
        assert h1 == h2
        assert len(h1) == 64 and all(ch in "0123456789abcdef" for ch in h1)

    def test_empty_pricebook_is_zero_not_divide_by_zero(self) -> None:
        res = a.analyze(PricebookData(as_of=AS_OF, items=[], updates=[]))
        assert res.totals.items == 0
        assert res.totals.vendor_coverage_pct == 0.0
        assert res.totals.avg_markup_pct == 0.0
        assert res.totals.total_price_delta_cents == 0

    def test_no_updates_leaves_every_price_unchanged(self) -> None:
        data = _scenario()
        no_updates = PricebookData(as_of=data.as_of, items=data.items, updates=[])
        res = a.analyze(no_updates)
        assert res.totals.items_affected == 0
        for c in res.changes:
            assert c.price_delta_cents == 0
            assert c.new_price_cents == c.old_price_cents

    @given(
        st.floats(min_value=0.0, max_value=40.0),
        st.integers(min_value=0, max_value=50_000_00),
        st.integers(min_value=0, max_value=200_000_00),
        st.floats(min_value=0.0, max_value=100.0),
    )
    def test_price_is_monotonic_in_materials_cost(
        self, hours: float, rate: int, materials: int, markup: float
    ) -> None:
        # raising materials cost can never lower the price (markup_pct >= 0)
        lo = a.price_cents(hours, rate, materials, markup)
        hi = a.price_cents(hours, rate, materials + 10_000, markup)
        assert hi >= lo
