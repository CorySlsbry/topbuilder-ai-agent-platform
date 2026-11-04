"""Unit + property tests for the deterministic Financial Forecasting engine.

The analyze() scenario is hand-computed so every asserted number is an independent oracle.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.agents.financial import analytics as a
from app.agents.financial.models import (
    APBill,
    ARInvoice,
    FinancialData,
    Job,
    PaymentVelocity,
)

AS_OF = date(2026, 6, 1)


# --------------------------------------------------------------------------------------------
# Pure primitives
# --------------------------------------------------------------------------------------------
class TestPrimitives:
    @pytest.mark.parametrize(
        "contract, pc, expected", [(100000, 0.5, 50000), (80000, 0.25, 20000), (50000, 0, 0)]
    )
    def test_earned_revenue(self, contract: float, pc: float, expected: float) -> None:
        assert a.earned_revenue(contract, pc) == pytest.approx(expected)

    @pytest.mark.parametrize(
        "earned, cost, expected", [(50000, 40000, 0.2), (40000, 20000, 0.5), (0, 10, 0.0)]
    )
    def test_margin_to_date(self, earned: float, cost: float, expected: float) -> None:
        assert a.margin_to_date(earned, cost) == pytest.approx(expected)

    def test_budget_margin(self) -> None:
        assert a.budget_margin(100000, 65000) == pytest.approx(0.35)

    def test_profitability_index(self) -> None:
        assert a.profitability_index(0.20, 0.35) == pytest.approx(0.5714, abs=1e-4)

    @pytest.mark.parametrize("billed, earned, expected", [(45000, 50000, -5000), (60000, 50000, 10000)])
    def test_billing_position(self, billed: float, earned: float, expected: float) -> None:
        assert a.billing_position(billed, earned) == pytest.approx(expected)

    def test_cost_overrun_ratio(self) -> None:
        # actual 40000 vs budgeted-at-completion 65000*0.5 = 32500 -> 1.2308
        assert a.cost_overrun_ratio(40000, 65000, 0.5) == pytest.approx(1.2308, abs=1e-4)

    @given(st.floats(0, 1_000_000), st.floats(0, 1.0))
    def test_earned_never_exceeds_contract(self, contract: float, pc: float) -> None:
        assert a.earned_revenue(contract, pc) <= contract + 1e-6


# --------------------------------------------------------------------------------------------
# Scenario for analyze()
# --------------------------------------------------------------------------------------------
def _scenario() -> FinancialData:
    jobs = [
        # J1: cost overrun + margin erosion (margin_to_date 0.20 vs target 0.35)
        Job("J1", "Downtown Retrofit", "commercial", "in_progress", 100000, 65000, 40000, 0.5, 45000),
        # J2: healthy (margin_to_date 0.50)
        Job("J2", "Maple Plaza", "residential", "in_progress", 80000, 52000, 20000, 0.5, 35000),
    ]
    ar = [
        ARInvoice("AR1", "commercial", 30000, AS_OF - timedelta(days=10), AS_OF + timedelta(days=20)),
        ARInvoice("AR2", "residential", 40000, AS_OF - timedelta(days=5), AS_OF + timedelta(days=40)),
        ARInvoice("AR3", "government", 25000, AS_OF, AS_OF + timedelta(days=80)),
    ]
    ap = [
        APBill("AP1", "SupplyCo", 20000, AS_OF + timedelta(days=10)),
        APBill("AP2", "PartsInc", 15000, AS_OF + timedelta(days=40)),
        APBill("AP3", "ToolCo", 10000, AS_OF + timedelta(days=80)),
    ]
    velocity = [
        PaymentVelocity("commercial", 30, 60),
        PaymentVelocity("residential", 50, 80),
        PaymentVelocity("government", 75, 30),
    ]
    return FinancialData(
        as_of=AS_OF,
        starting_cash=100000,
        target_gross_margin=0.35,
        jobs=jobs,
        ar_invoices=ar,
        ap_bills=ap,
        payment_velocity=velocity,
    )


class TestCashFlow:
    def test_three_buckets(self) -> None:
        result = a.analyze(_scenario())
        assert [b.horizon_days for b in result.cash_flow] == [30, 60, 90]

    def test_projected_cash_curve(self) -> None:
        # b30: +30000 -20000 ; b60: +40000 -15000 ; b90: +25000 -10000 ; start 100000
        cash = {b.horizon_days: b.projected_cash for b in a.analyze(_scenario()).cash_flow}
        assert cash[30] == pytest.approx(110000)
        assert cash[60] == pytest.approx(135000)
        assert cash[90] == pytest.approx(150000)

    def test_confidence_decreases_with_horizon(self) -> None:
        cf = a.analyze(_scenario()).cash_flow
        confs = [b.confidence for b in cf]
        assert confs[0] >= confs[1] >= confs[2]


class TestJobProfitability:
    def test_two_jobs_scored(self) -> None:
        result = a.analyze(_scenario())
        by_id = {j.job_id: j for j in result.job_profitability}
        assert set(by_id) == {"J1", "J2"}
        assert by_id["J1"].profitability_index == pytest.approx(0.5714, abs=1e-4)
        assert by_id["J2"].profitability_index == pytest.approx(1.4286, abs=1e-4)


class TestLeakage:
    def test_j1_flagged_j2_clean(self) -> None:
        result = a.analyze(_scenario())
        flagged = {w.job_id for w in result.leakage}
        assert flagged == {"J1"}
        w = result.leakage[0]
        assert w.kind == "cost_overrun"
        # actual 40000 - budgeted-at-completion 32500 = 7500
        assert w.severity_cents == 750000


class TestSegmentsAndMeta:
    def test_segment_margins(self) -> None:
        margins = {s.segment: s.margin for s in a.analyze(_scenario()).segment_margins}
        assert margins["commercial"] == pytest.approx(0.20)
        assert margins["residential"] == pytest.approx(0.50)

    def test_inputs_hash_stable_and_hex(self) -> None:
        h1 = a.analyze(_scenario()).inputs_hash
        h2 = a.analyze(_scenario()).inputs_hash
        assert h1 == h2 and len(h1) == 64
