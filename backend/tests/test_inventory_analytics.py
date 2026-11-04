"""Unit + property tests for the deterministic Inventory & Supply Chain engine."""
from __future__ import annotations

from datetime import date

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.agents.inventory import analytics as a
from app.agents.inventory.models import (
    InventoryData,
    MaterialUsage,
    Part,
    ReorderState,
    TruckStockCount,
    VendorQuote,
)

AS_OF = date(2026, 6, 1)


class TestPrimitives:
    @pytest.mark.parametrize("usage, lead, expected", [(0.8, 10, 8.0), (5, 5, 25), (1.2, 7, 8.4)])
    def test_demand_during_lead(self, usage: float, lead: float, expected: float) -> None:
        assert a.demand_during_lead(usage, lead) == pytest.approx(expected)

    def test_dynamic_reorder_point(self) -> None:
        assert a.dynamic_reorder_point(0.8, 10, 3) == pytest.approx(11.0)

    @pytest.mark.parametrize("on_hand, usage, expected", [(5, 0.8, 6.25), (4, 1.2, 3.333)])
    def test_days_to_stockout(self, on_hand: float, usage: float, expected: float) -> None:
        assert a.days_to_stockout(on_hand, usage) == pytest.approx(expected, abs=1e-3)

    def test_days_to_stockout_no_usage_is_infinite(self) -> None:
        assert a.days_to_stockout(5, 0) == float("inf")

    def test_shrinkage_value_cents(self) -> None:
        assert a.shrinkage_value_cents(1, 400) == 40_000

    def test_arbitrage_annual_savings_cents(self) -> None:
        # (400-360) * 0.8/day * 365 = $11,680
        assert a.arbitrage_annual_savings_cents(400, 360, 0.8) == 1_168_000

    @given(st.floats(0, 1000), st.floats(0, 1000), st.floats(0, 100))
    def test_arbitrage_never_negative(self, current: float, quote: float, usage: float) -> None:
        assert a.arbitrage_annual_savings_cents(current, quote, usage) >= 0


def _scenario() -> InventoryData:
    parts = [
        Part("SKU-A", "Compressor", "hvac", 400, 520, "high"),
        Part("SKU-B", "Filter", "hvac", 8, 18, "standard"),
        Part("SKU-C", "Thermostat", "controls", 60, 140, "high"),
    ]
    reorder = [
        ReorderState("SKU-A", on_hand=5, avg_daily_usage=0.8, lead_time_days=10, safety_stock=3, current_reorder_point=8, usage_sample_days=120),
        ReorderState("SKU-B", on_hand=200, avg_daily_usage=5, lead_time_days=5, safety_stock=50, current_reorder_point=75, usage_sample_days=120),
        ReorderState("SKU-C", on_hand=4, avg_daily_usage=1.2, lead_time_days=7, safety_stock=5, current_reorder_point=13, usage_sample_days=30),
    ]
    truck = [
        TruckStockCount("T1", "SKU-A", expected_qty=2, counted_qty=1),   # short 1 -> $400
        TruckStockCount("T2", "SKU-B", expected_qty=40, counted_qty=30),  # short 10 -> $80
        TruckStockCount("T1", "SKU-C", expected_qty=3, counted_qty=3),    # ok
        TruckStockCount("T2", "SKU-A", expected_qty=1, counted_qty=2),    # overage -> ignore
    ]
    usage = [
        MaterialUsage("J1", "SKU-B", qty_used=12, billed=False),  # $216
        MaterialUsage("J1", "SKU-A", qty_used=1, billed=True),
        MaterialUsage("J2", "SKU-C", qty_used=2, billed=False),   # $280
        MaterialUsage("J2", "SKU-B", qty_used=5, billed=True),
    ]
    quotes = [
        VendorQuote("SKU-A", "AltCo", 360, 9),
        VendorQuote("SKU-A", "BigBox", 410, 6),
        VendorQuote("SKU-B", "AltCo", 7.5, 4),
        VendorQuote("SKU-C", "AltCo", 65, 8),
    ]
    return InventoryData(AS_OF, parts, reorder, truck, usage, quotes)


class TestReorders:
    def test_two_skus_need_reorder(self) -> None:
        result = a.analyze(_scenario())
        assert [r.sku for r in result.critical_reorders] == ["SKU-A", "SKU-C"]  # by exposure desc

    def test_reorder_numbers(self) -> None:
        by = {r.sku: r for r in a.analyze(_scenario()).critical_reorders}
        assert by["SKU-A"].dynamic_reorder_point == pytest.approx(11.0)
        assert by["SKU-A"].stockout_exposure_cents == 156_000  # 3 units short * $520
        assert by["SKU-A"].recommended_order_qty == 14
        assert by["SKU-A"].confidence == pytest.approx(1.0)
        assert by["SKU-C"].stockout_exposure_cents == 61_600
        assert by["SKU-C"].confidence == pytest.approx(0.6)


class TestShrinkageUnbilledArbitrage:
    def test_shrinkage_alerts(self) -> None:
        alerts = a.analyze(_scenario()).shrinkage_alerts
        assert [(s.technician_id, s.sku, s.shrinkage_value_cents) for s in alerts] == [
            ("T1", "SKU-A", 40_000),
            ("T2", "SKU-B", 8_000),
        ]

    def test_unbilled_materials(self) -> None:
        unbilled = a.analyze(_scenario()).unbilled_materials
        assert {(u.job_id, u.sku): u.unbilled_value_cents for u in unbilled} == {
            ("J2", "SKU-C"): 28_000,
            ("J1", "SKU-B"): 21_600,
        }

    def test_vendor_arbitrage(self) -> None:
        arb = {o.sku: o for o in a.analyze(_scenario()).arbitrage}
        assert set(arb) == {"SKU-A", "SKU-B"}
        assert arb["SKU-A"].best_vendor == "AltCo"
        assert arb["SKU-A"].annual_savings_cents == 1_168_000


class TestMeta:
    def test_inputs_hash_stable_and_hex(self) -> None:
        h1 = a.analyze(_scenario()).inputs_hash
        h2 = a.analyze(_scenario()).inputs_hash
        assert h1 == h2 and len(h1) == 64
