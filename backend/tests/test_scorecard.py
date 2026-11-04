"""Oracle + property tests for the Department Scorecard engine (PURE, no DB).

Every asserted figure is an INDEPENDENT hand-computed oracle — the calculated KPIs are re-derived
here from first principles (not from the engine's own output). Money is carried as integer **cents**
in the raw inputs and emitted as **dollars** by the engine, so the usd oracles divide by 100.

The catalog-coverage + fixture-shape tests pin the example-JSON contract the frontend builds to
(docs/ALEX_SCORECARD_SPEC.md): every catalog key resolves to a value in the right department, the
calculated/raw flags are correct, and the Canyon Ridge fixture produces all four departments.
"""
from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.org import scorecard as sc
from app.org import scorecard_data as sd
from app.org.scorecard import (
    CATALOG,
    CATALOG_BY_KEY,
    RawDepartment,
    RawEntity,
    RawEntityWeek,
    RawWeek,
    ScorecardData,
    compute_scorecard,
    scorecard_to_json,
)

# --------------------------------------------------------------------------------------------
# 1. Calculated-KPI helpers — independent hand-computed oracles
# --------------------------------------------------------------------------------------------


class TestClosingPct:
    @pytest.mark.parametrize(
        "jobs, opps, expected",
        [
            (7, 22, 31.82),  # the real Bloom anchor
            (113, 355, 31.83),
            (9, 9, 100.0),
            (0, 10, 0.0),
        ],
    )
    def test_known(self, jobs: float, opps: float, expected: float) -> None:
        assert sc.closing_pct(jobs, opps) == pytest.approx(expected)

    def test_zero_opportunities_is_none_not_divide_by_zero(self) -> None:
        assert sc.closing_pct(5, 0) is None


class TestRpl:
    def test_anchor_six_thousand_ish(self) -> None:
        # $152,800 over 25 leads = $6,112.00 (Bloom RPL anchor ~$6,138, goal $6,000)
        assert sc.rpl(152_800_00, 25) == pytest.approx(6112.00)

    def test_emits_dollars_from_cents(self) -> None:
        # 1,000,000 cents over 5 leads = $2,000.00
        assert sc.rpl(1_000_000, 5) == pytest.approx(2000.00)

    def test_zero_leads_is_none(self) -> None:
        assert sc.rpl(500_000, 0) is None


class TestAverageTicket:
    def test_anchor_thirteen_fifty(self) -> None:
        # $152,800 over 113 jobs = $1,352.21 (Bloom Avg Ticket anchor ~$1,357)
        assert sc.average_ticket(152_800_00, 113) == pytest.approx(1352.21)

    def test_zero_jobs_is_none(self) -> None:
        assert sc.average_ticket(500_000, 0) is None


class TestConversionRate:
    def test_known(self) -> None:
        # 40 converted over 54 dispatched = 74.07%
        assert sc.conversion_rate(40, 54) == pytest.approx(74.07)

    def test_zero_dispatched_is_none(self) -> None:
        assert sc.conversion_rate(10, 0) is None


class TestUtilization:
    def test_known(self) -> None:
        # 168 billable over 200 available = 84.0%
        assert sc.utilization(168, 200) == pytest.approx(84.0)

    def test_charadia_anchor(self) -> None:
        # 25.6 billable over 40 available = 64.0% (Michael Charadia's anchor)
        assert sc.utilization(25.6, 40) == pytest.approx(64.0)

    def test_zero_available_is_none(self) -> None:
        assert sc.utilization(10, 0) is None


class TestAvgPerDay:
    def test_drive_per_day(self) -> None:
        # 33.1 drive hours over 5 business days = 6.62 h/day
        assert sc.avg_per_day(33.1, 5) == pytest.approx(6.62)

    def test_zero_days_is_none(self) -> None:
        assert sc.avg_per_day(40, 0) is None


class TestTechniciansNeeded:
    @pytest.mark.parametrize(
        "calls_week, business_days, per_tech, expected",
        [
            (65, 5, 8, 2),  # (65/5)/8 = 1.625 -> ceil 2
            (80, 5, 8, 2),  # (80/5)/8 = 2.0  -> ceil 2
            (81, 5, 8, 3),  # (81/5)/8 = 2.025 -> ceil 3
            (200, 5, 8, 5),  # (200/5)/8 = 5.0 -> 5
        ],
    )
    def test_known(self, calls_week, business_days, per_tech, expected) -> None:
        assert sc.technicians_needed(calls_week, business_days, per_tech) == expected

    def test_is_ceiling_not_round(self) -> None:
        # (41/5)/8 = 1.025 must ceil to 2, never round to 1
        assert sc.technicians_needed(41, 5, 8) == 2

    def test_zero_business_days_is_none(self) -> None:
        assert sc.technicians_needed(50, 0, 8) is None

    def test_zero_per_tech_is_none(self) -> None:
        assert sc.technicians_needed(50, 5, 0) is None


class TestBookRate:
    def test_known(self) -> None:
        # 83 booked over 93 leads = 89.25% (goal 90)
        assert sc.book_rate(83, 93) == pytest.approx(89.25)

    def test_zero_leads_is_none(self) -> None:
        assert sc.book_rate(10, 0) is None


class TestMissedCallRate:
    def test_known(self) -> None:
        # 11 missed over (115 handled + 11 missed) = 8.73%
        assert sc.missed_call_rate(11, 115) == pytest.approx(8.73)

    def test_zero_calls_is_none(self) -> None:
        assert sc.missed_call_rate(0, 0) is None


class TestAvgBookingValue:
    def test_known(self) -> None:
        # $9,200 over 83 booked = $110.84
        assert sc.avg_booking_value(920_000, 83) == pytest.approx(110.84)

    def test_zero_booked_is_none(self) -> None:
        assert sc.avg_booking_value(500_000, 0) is None


class TestQuickRatio:
    def test_known(self) -> None:
        # (cash 203,530 + AR 436,000) / current liabilities 456,807 ~= 1.40 (Bloom anchor)
        cash = 203_530_00
        ar = 436_000_00
        cl = round((cash + ar) / 1.4)
        assert sc.quick_ratio(cash, ar, cl) == pytest.approx(1.40, abs=0.01)

    def test_zero_liabilities_is_none(self) -> None:
        assert sc.quick_ratio(100, 100, 0) is None


class TestArPct:
    def test_pct_current(self) -> None:
        # current 222,000 / total 436,000 = 50.92%
        assert sc.ar_pct_current(222_000_00, 436_000_00) == pytest.approx(50.92)

    def test_pct_over_30(self) -> None:
        # (436,000 - 222,000) / 436,000 = 49.08%
        assert sc.ar_pct_over_30(222_000_00, 436_000_00) == pytest.approx(49.08)

    def test_current_and_over30_sum_to_100(self) -> None:
        cur, tot = 100_000_00, 250_000_00
        assert sc.ar_pct_current(cur, tot) + sc.ar_pct_over_30(cur, tot) == pytest.approx(100.0)

    def test_zero_total_is_none(self) -> None:
        assert sc.ar_pct_current(0, 0) is None
        assert sc.ar_pct_over_30(0, 0) is None


class TestAverageJobSize:
    def test_known(self) -> None:
        # $338,000 completed over 250 jobs = $1,352.00
        assert sc.average_job_size(338_000_00, 250) == pytest.approx(1352.00)

    def test_zero_jobs_is_none(self) -> None:
        assert sc.average_job_size(100_000, 0) is None


class TestNeedsCoaching:
    def test_below_goal_flags(self) -> None:
        assert sc.needs_coaching(25.0, 32) is True

    def test_at_or_above_goal_clears(self) -> None:
        assert sc.needs_coaching(32.0, 32) is False
        assert sc.needs_coaching(77.78, 32) is False

    def test_missing_inputs_is_none(self) -> None:
        assert sc.needs_coaching(None, 32) is None
        assert sc.needs_coaching(25.0, None) is None


class TestCalculatedHelperProperties:
    @given(st.floats(0, 1e6, allow_nan=False), st.floats(0.01, 1e6, allow_nan=False))
    def test_rpl_round_trips_to_dollars(self, gross_cents: float, leads: float) -> None:
        # rpl is gross/leads expressed in dollars (cents/100); never divides by zero here.
        assert sc.rpl(gross_cents, leads) == pytest.approx(round(gross_cents / leads / 100, 2))

    @given(st.integers(0, 1000), st.integers(1, 50), st.floats(0.1, 50, allow_nan=False))
    def test_technicians_needed_is_a_ceiling(self, calls, days, per_tech) -> None:
        got = sc.technicians_needed(calls, days, per_tech)
        assert got == math.ceil((calls / days) / per_tech)


# --------------------------------------------------------------------------------------------
# 2. on_goal / delta_pct evaluation
# --------------------------------------------------------------------------------------------


class TestOnGoal:
    def test_higher_is_better_meets_goal(self) -> None:
        assert sc.evaluate_on_goal(145000, 145000, higher_is_better=True) is True
        assert sc.evaluate_on_goal(144999, 145000, higher_is_better=True) is False

    def test_lower_is_better_meets_goal(self) -> None:
        # missed-call rate: lower is better — value at/under goal is on-goal.
        assert sc.evaluate_on_goal(5.0, 10.0, higher_is_better=False) is True
        assert sc.evaluate_on_goal(11.0, 10.0, higher_is_better=False) is False

    def test_no_goal_is_none(self) -> None:
        assert sc.evaluate_on_goal(50, None, higher_is_better=True) is None

    def test_no_value_is_none(self) -> None:
        assert sc.evaluate_on_goal(None, 100, higher_is_better=True) is None


class TestDeltaPct:
    def test_change_vs_first_present_point(self) -> None:
        series = [sc.SeriesPoint("d1", 100.0), sc.SeriesPoint("d2", 150.0)]
        # (150 - 100) / 100 * 100 = 50.0%
        assert sc.delta_pct(series) == pytest.approx(50.0)

    def test_skips_leading_gaps_to_first_present(self) -> None:
        series = [sc.SeriesPoint("d0", None), sc.SeriesPoint("d1", 200.0), sc.SeriesPoint("d2", 250.0)]
        # base is the first present (200), not the leading null. (250-200)/200 = 25%.
        assert sc.delta_pct(series) == pytest.approx(25.0)

    def test_single_present_point_is_none(self) -> None:
        assert sc.delta_pct([sc.SeriesPoint("d1", 100.0)]) is None

    def test_zero_base_is_none(self) -> None:
        series = [sc.SeriesPoint("d1", 0.0), sc.SeriesPoint("d2", 50.0)]
        assert sc.delta_pct(series) is None


# --------------------------------------------------------------------------------------------
# 3. compute_scorecard on a hand-built scenario (independent oracle)
# --------------------------------------------------------------------------------------------


def _scenario() -> ScorecardData:
    """Two weeks of raw figures across all four departments + a couple of entities.

    Money is cents. Every derived number below is hand-computed in the assertions.
    """
    sales = RawDepartment(
        key="sales",
        weeks=[
            RawWeek("2026-06-01", {
                "gross_sales": 100_000_00, "opportunities": 40, "jobs_sold": 10,
                "leads": 20, "sold_hours": 90, "tech_generated_leads": 2,
            }),
            RawWeek("2026-06-08", {
                "gross_sales": 120_000_00, "opportunities": 50, "jobs_sold": 20,
                "leads": 24, "sold_hours": 110, "tech_generated_leads": 3,
            }),
        ],
        entities=[
            RawEntity("rep-top", "Top Rep", "sales_rep", [
                RawEntityWeek("2026-06-01", {"gross_sales": 60_000_00, "opportunities": 10, "jobs_sold": 7, "leads": 9}),
                RawEntityWeek("2026-06-08", {"gross_sales": 70_000_00, "opportunities": 10, "jobs_sold": 8, "leads": 10}),
            ]),
            RawEntity("rep-low", "Low Rep", "sales_rep", [
                RawEntityWeek("2026-06-01", {"gross_sales": 20_000_00, "opportunities": 8, "jobs_sold": 2, "leads": 8}),
                RawEntityWeek("2026-06-08", {"gross_sales": 22_000_00, "opportunities": 8, "jobs_sold": 2, "leads": 8}),
            ]),
        ],
    )
    operations = RawDepartment(
        key="operations",
        weeks=[
            RawWeek("2026-06-01", {
                "completed_revenue_service": 25_000_00, "converted_jobs": 30, "dispatched": 50,
                "job_count": 35, "idle_time": 10.0, "driving_time": 30.0, "late_alerts": 12,
                "billable_hours": 150.0, "available_hours": 200.0, "calls_week": 65,
                "drive_time_saved": 50, "overtime_hours": 20, "understaffing_gap": 10,
                "unbilled_materials": 4_000_00, "hvac_maint_non_job_rev": 11_000_00,
            }),
            RawWeek("2026-06-08", {
                "completed_revenue_service": 26_000_00, "converted_jobs": 40, "dispatched": 54,
                "job_count": 42, "idle_time": 9.3, "driving_time": 33.1, "late_alerts": 20,
                "billable_hours": 168.0, "available_hours": 200.0, "calls_week": 65,
                "drive_time_saved": 57, "overtime_hours": 23, "understaffing_gap": 13,
                "unbilled_materials": 4_500_00, "hvac_maint_non_job_rev": 10_900_00,
            }),
        ],
        entities=[
            RawEntity("tech-a", "Tech A", "technician", [
                RawEntityWeek("2026-06-01", {"billable_hours": 24.0, "available_hours": 40.0, "job_count": 55, "idle_time": 9.0, "driving_time": 30.0, "late_alerts": 15}),
                RawEntityWeek("2026-06-08", {"billable_hours": 25.6, "available_hours": 40.0, "job_count": 62, "idle_time": 9.23, "driving_time": 32.87, "late_alerts": 19}),
            ]),
        ],
    )
    sales_marketing = RawDepartment(
        key="sales_marketing",
        weeks=[
            RawWeek("2026-06-01", {
                "calls_taken": 120, "missed_calls": 12, "leads_fo": 90, "booked": 80,
                "after_hours_recovered": 2_800_00, "booking_recovered": 8_600_00,
            }),
            RawWeek("2026-06-08", {
                "calls_taken": 126, "missed_calls": 11, "leads_fo": 93, "booked": 83,
                "after_hours_recovered": 3_000_00, "booking_recovered": 9_200_00,
            }),
        ],
        entities=[
            RawEntity("csr-1", "CSR One", "csr", [
                RawEntityWeek("2026-06-01", {"calls_taken": 26, "leads_fo": 19, "booked": 6}),
                RawEntityWeek("2026-06-08", {"calls_taken": 24, "leads_fo": 18, "booked": 5}),
            ]),
        ],
    )
    finance = RawDepartment(
        key="finance",
        weeks=[
            RawWeek("2026-06-01", {
                "cash_collected": 150_000_00, "cash": 200_000_00, "credit_card_balance": 118_000_00,
                "line_of_credit_used": 51_000_00, "current_liabilities": 450_000_00,
                "ar_total": 430_000_00, "ar_current": 210_000_00, "ar_1_30": 100_000_00,
                "ar_31_60": 50_000_00, "ar_61_90": 30_000_00, "ar_91_120": 25_000_00,
                "ar_121_plus": 15_000_00, "margin_leakage": 12_000_00,
                "completed_revenue_service": 320_000_00, "jobs_completed": 240,
                "department_income": 60_000_00, "upcoming_jobs_1wk": 110_000_00,
                "upcoming_jobs_2wk": 200_000_00, "upcoming_jobs_4wk": 270_000_00,
                "follow_up_backlog": 500_000_00,
            }),
            RawWeek("2026-06-08", {
                "cash_collected": 163_400_00, "cash": 209_800_00, "credit_card_balance": 117_300_00,
                "line_of_credit_used": 50_400_00, "current_liabilities": 461_286_00,
                "ar_total": 436_000_00, "ar_current": 222_000_00, "ar_1_30": 103_000_00,
                "ar_31_60": 51_000_00, "ar_61_90": 30_000_00, "ar_91_120": 17_000_00,
                "ar_121_plus": 13_000_00, "margin_leakage": 13_500_00,
                "completed_revenue_service": 338_000_00, "jobs_completed": 250,
                "department_income": 68_000_00, "upcoming_jobs_1wk": 119_000_00,
                "upcoming_jobs_2wk": 205_000_00, "upcoming_jobs_4wk": 278_000_00,
                "follow_up_backlog": 516_000_00,
            }),
        ],
        entities=[],
    )
    return ScorecardData(
        departments=[sales, operations, sales_marketing, finance],
        business_days_per_week=5,
        calls_per_tech_per_day=8.0,
    )


def _dept(card, key: str):
    return next(d for d in card.departments if d.key == key)


def _kpi(dept, key: str):
    return next(k for k in dept.kpis if k.key == key)


class TestComputeScorecardSalesCalculated:
    def test_closing_pct_uses_latest_week(self) -> None:
        card = compute_scorecard(_scenario())
        # latest week jobs_sold 20 / opportunities 50 = 40.0%
        assert _kpi(_dept(card, "sales"), "closing_pct").value == pytest.approx(40.0)

    def test_rpl_in_dollars(self) -> None:
        # $120,000 / 24 leads = $5,000.00
        card = compute_scorecard(_scenario())
        assert _kpi(_dept(card, "sales"), "rpl").value == pytest.approx(5000.0)

    def test_average_ticket_in_dollars(self) -> None:
        # $120,000 / 20 jobs = $6,000.00
        card = compute_scorecard(_scenario())
        assert _kpi(_dept(card, "sales"), "average_ticket").value == pytest.approx(6000.0)

    def test_gross_sales_emitted_as_dollars_with_goal_check(self) -> None:
        gross = _kpi(_dept(compute_scorecard(_scenario()), "sales"), "gross_sales")
        assert gross.value == pytest.approx(120000.0)  # 120,000 dollars from cents
        assert gross.goal == 145000
        assert gross.on_goal is False  # 120k < 145k goal, higher-is-better


class TestComputeScorecardOperationsCalculated:
    def test_conversion_rate(self) -> None:
        # latest: 40 converted / 54 dispatched = 74.07%
        card = compute_scorecard(_scenario())
        assert _kpi(_dept(card, "operations"), "conversion_rate").value == pytest.approx(74.07)

    def test_utilization(self) -> None:
        # latest: 168 billable / 200 available = 84.0%
        card = compute_scorecard(_scenario())
        assert _kpi(_dept(card, "operations"), "utilization").value == pytest.approx(84.0)

    def test_avg_drive_and_idle_per_day(self) -> None:
        ops = _dept(compute_scorecard(_scenario()), "operations")
        # latest drive 33.1 / 5 = 6.62 ; idle 9.3 / 5 = 1.86
        assert _kpi(ops, "avg_drive_per_day").value == pytest.approx(6.62)
        assert _kpi(ops, "avg_idle_per_day").value == pytest.approx(1.86)

    def test_technicians_needed(self) -> None:
        # (65 calls / 5 days) / 8 per tech = 1.625 -> ceil 2
        card = compute_scorecard(_scenario())
        assert _kpi(_dept(card, "operations"), "technicians_needed").value == pytest.approx(2.0)


class TestComputeScorecardFrontOfficeCalculated:
    def test_book_rate(self) -> None:
        # latest 83 booked / 93 leads = 89.25%
        card = compute_scorecard(_scenario())
        assert _kpi(_dept(card, "sales_marketing"), "book_rate").value == pytest.approx(89.25)

    def test_missed_call_rate(self) -> None:
        # latest 11 missed / (126 handled + 11 missed) = 8.03%
        card = compute_scorecard(_scenario())
        assert _kpi(_dept(card, "sales_marketing"), "missed_call_rate").value == pytest.approx(8.03)

    def test_avg_booking_value(self) -> None:
        # latest $9,200 recovered / 83 booked = $110.84
        card = compute_scorecard(_scenario())
        assert _kpi(_dept(card, "sales_marketing"), "avg_booking_value").value == pytest.approx(110.84)


class TestComputeScorecardFinanceCalculated:
    def test_quick_ratio(self) -> None:
        # latest (cash 209,800 + AR 436,000) / CL 461,286 = 1.40
        card = compute_scorecard(_scenario())
        qr = _kpi(_dept(card, "finance"), "quick_ratio")
        assert qr.value == pytest.approx(1.40, abs=0.01)
        assert qr.goal == 3
        assert qr.on_goal is False  # 1.40 < 3 goal

    def test_ar_pct_current_and_over30(self) -> None:
        fin = _dept(compute_scorecard(_scenario()), "finance")
        # latest current 222,000 / total 436,000 = 50.92% ; over-30 = 49.08%
        assert _kpi(fin, "ar_pct_current").value == pytest.approx(50.92)
        assert _kpi(fin, "ar_pct_over_30").value == pytest.approx(49.08)

    def test_average_job_size(self) -> None:
        # latest $338,000 / 250 jobs = $1,352.00
        card = compute_scorecard(_scenario())
        assert _kpi(_dept(card, "finance"), "average_job_size").value == pytest.approx(1352.0)

    def test_cash_collected_dollars_and_on_goal(self) -> None:
        cc = _kpi(_dept(compute_scorecard(_scenario()), "finance"), "cash_collected")
        assert cc.value == pytest.approx(163400.0)  # dollars from cents
        assert cc.on_goal is True  # 163,400 >= 100,000 goal


class TestDeltaPctOnSeries:
    def test_gross_sales_delta_vs_first_week(self) -> None:
        # gross week1 $100,000 -> week2 $120,000 = +20.0%
        card = compute_scorecard(_scenario())
        assert _kpi(_dept(card, "sales"), "gross_sales").delta_pct == pytest.approx(20.0)

    def test_series_has_one_point_per_week(self) -> None:
        card = compute_scorecard(_scenario(), weeks=13)
        gross = _kpi(_dept(card, "sales"), "gross_sales")
        assert [p.date for p in gross.series] == ["2026-06-01", "2026-06-08"]
        assert [p.value for p in gross.series] == [pytest.approx(100000.0), pytest.approx(120000.0)]


class TestWeeksTrimming:
    def test_weeks_one_keeps_only_latest_column(self) -> None:
        card = compute_scorecard(_scenario(), weeks=1)
        assert card.period_weeks == 1
        gross = _kpi(_dept(card, "sales"), "gross_sales")
        assert len(gross.series) == 1
        assert gross.series[0].date == "2026-06-08"
        # one present point -> no meaningful delta
        assert gross.delta_pct is None


# --------------------------------------------------------------------------------------------
# 4. Per-entity rows (the side-by-side reps/techs/CSRs panel — Cory's explicit ask)
# --------------------------------------------------------------------------------------------


class TestEntityRows:
    def test_sales_reps_close_rates_side_by_side(self) -> None:
        sales = _dept(compute_scorecard(_scenario()), "sales")
        by_id = {e.entity_id: e for e in sales.entities}
        # Top Rep latest: 8/10 = 80.0% ; Low Rep latest: 2/8 = 25.0%
        assert by_id["rep-top"].values["closing_pct"] == pytest.approx(80.0)
        assert by_id["rep-low"].values["closing_pct"] == pytest.approx(25.0)

    def test_needs_coaching_flag_per_rep(self) -> None:
        sales = _dept(compute_scorecard(_scenario()), "sales")
        by_id = {e.entity_id: e for e in sales.entities}
        # goal is 32%; Low Rep at 25% is flagged (1.0), Top Rep at 80% is clear (0.0).
        assert by_id["rep-low"].values["needs_coaching"] == pytest.approx(1.0)
        assert by_id["rep-top"].values["needs_coaching"] == pytest.approx(0.0)

    def test_entity_rows_carry_role_and_name(self) -> None:
        sales = _dept(compute_scorecard(_scenario()), "sales")
        top = next(e for e in sales.entities if e.entity_id == "rep-top")
        assert (top.entity_name, top.role) == ("Top Rep", "sales_rep")

    def test_headline_series_tracks_the_primary_metric(self) -> None:
        # Sales headline = closing_pct: Top Rep 7/10=70.0% then 8/10=80.0%.
        sales = _dept(compute_scorecard(_scenario()), "sales")
        top = next(e for e in sales.entities if e.entity_id == "rep-top")
        assert [p.value for p in top.headline_series] == [pytest.approx(70.0), pytest.approx(80.0)]

    def test_technician_utilization_per_entity(self) -> None:
        ops = _dept(compute_scorecard(_scenario()), "operations")
        tech = next(e for e in ops.entities if e.entity_id == "tech-a")
        # latest 25.6 billable / 40 available = 64.0% (Charadia anchor)
        assert tech.values["utilization"] == pytest.approx(64.0)

    def test_csr_book_rate_per_entity(self) -> None:
        fo = _dept(compute_scorecard(_scenario()), "sales_marketing")
        csr = next(e for e in fo.entities if e.entity_id == "csr-1")
        # latest 5 booked / 18 leads = 27.78%
        assert csr.values["book_rate"] == pytest.approx(27.78)

    def test_finance_has_no_entities(self) -> None:
        fin = _dept(compute_scorecard(_scenario()), "finance")
        assert fin.entity_role is None
        assert fin.entities == []


# --------------------------------------------------------------------------------------------
# 5. Catalog coverage + flags
# --------------------------------------------------------------------------------------------

_EXPECTED_CALCULATED = {
    "closing_pct", "rpl", "average_ticket", "needs_coaching",  # sales
    "conversion_rate", "utilization", "avg_drive_per_day", "avg_idle_per_day", "technicians_needed",  # ops
    "book_rate", "missed_call_rate", "avg_booking_value",  # sales+marketing
    "quick_ratio", "ar_pct_current", "ar_pct_over_30", "average_job_size",  # finance
}

_EXPECTED_DEPTS = {"sales", "operations", "sales_marketing", "finance"}


class TestCatalogCoverage:
    def test_every_catalog_key_is_unique(self) -> None:
        keys = [d.key for d in CATALOG]
        assert len(keys) == len(set(keys))

    def test_every_calculated_flag_is_correct(self) -> None:
        calculated = {d.key for d in CATALOG if d.calculated}
        assert calculated == _EXPECTED_CALCULATED

    def test_catalog_departments_are_the_four_scorecard_depts(self) -> None:
        assert {d.department for d in CATALOG} == _EXPECTED_DEPTS

    def test_every_catalog_key_resolves_to_a_kpivalue_in_its_department(self) -> None:
        card = compute_scorecard(_scenario())
        kpis_by_dept = {d.key: {k.key for k in d.kpis} for d in card.departments}
        for d in CATALOG:
            assert d.key in kpis_by_dept[d.department], f"{d.key} missing from {d.department}"

    def test_usd_kpis_emit_dollars_not_cents(self) -> None:
        # gross_sales is a usd KPI; the engine value must be dollars (120,000), never cents.
        card = compute_scorecard(_scenario())
        assert _kpi(_dept(card, "sales"), "gross_sales").value == pytest.approx(120000.0)

    def test_goals_match_the_spec(self) -> None:
        # Pin the load-bearing Bloom goals from the spec catalog.
        assert CATALOG_BY_KEY["gross_sales"].goal == 145000
        assert CATALOG_BY_KEY["closing_pct"].goal == 32
        assert CATALOG_BY_KEY["rpl"].goal == 6000
        assert CATALOG_BY_KEY["average_ticket"].goal == 400
        assert CATALOG_BY_KEY["leads"].goal == 20
        assert CATALOG_BY_KEY["completed_revenue_service"].goal == 9300
        assert CATALOG_BY_KEY["hvac_maint_non_job_rev"].goal == 10000
        assert CATALOG_BY_KEY["book_rate"].goal == 90
        assert CATALOG_BY_KEY["cash_collected"].goal == 100000
        assert CATALOG_BY_KEY["quick_ratio"].goal == 3
        assert CATALOG_BY_KEY["upcoming_jobs_1wk"].goal == 130000
        assert CATALOG_BY_KEY["upcoming_jobs_2wk"].goal == 283000
        assert CATALOG_BY_KEY["upcoming_jobs_4wk"].goal == 400000
        assert CATALOG_BY_KEY["follow_up_backlog"].goal == 900000

    def test_lower_is_better_metrics_flagged(self) -> None:
        # idle/drive/late/missed-call/over-30 AR are healthier when LOWER.
        for key in ("idle_time", "driving_time", "late_alerts", "missed_call_rate",
                    "ar_pct_over_30", "margin_leakage", "overtime_hours",
                    "credit_card_balance", "line_of_credit_used"):
            assert CATALOG_BY_KEY[key].higher_is_better is False, key


# --------------------------------------------------------------------------------------------
# 6. Fixture shape — the Canyon Ridge JSON loads + anchors to the real Bloom numbers
# --------------------------------------------------------------------------------------------


class TestCanyonRidgeFixture:
    def test_fixture_loads_into_scorecard_data(self) -> None:
        data = sd.load_fixture_scorecard_data()
        assert {d.key for d in data.departments} == _EXPECTED_DEPTS
        # 78 weekly columns per department (1.5 years: the real recent 13 + a seasonal history that
        # feeds the rolling-year trend view + the forecast's year-over-year overlay).
        for d in data.departments:
            assert len(d.weeks) == 78, d.key
        # Chronological, ending at the real recent tail.
        for d in data.departments:
            dates = [w.date for w in d.weeks]
            assert dates == sorted(dates) and dates[-1] == "2026-06-15", d.key

    def test_fixture_produces_all_four_departments_with_full_catalog(self) -> None:
        card = compute_scorecard(sd.load_fixture_scorecard_data(), weeks=13)
        assert [d.key for d in card.departments] == ["sales", "operations", "sales_marketing", "finance"]
        assert card.catalog == CATALOG
        # every catalog KPI is present in its department.
        for d in CATALOG:
            dept = _dept(card, d.department)
            assert any(k.key == d.key for k in dept.kpis)

    def test_fixture_anchors_match_bloom(self) -> None:
        card = compute_scorecard(sd.load_fixture_scorecard_data(), weeks=13)
        sales = _dept(card, "sales")
        # Closing % ~31.83 (goal 32) ; RPL ~$6,112 (goal 6,000) ; Avg Ticket ~$1,352 (~$1,357 anchor)
        assert _kpi(sales, "closing_pct").value == pytest.approx(31.83, abs=0.05)
        assert _kpi(sales, "rpl").value == pytest.approx(6112.0, abs=1.0)
        assert _kpi(sales, "average_ticket").value == pytest.approx(1352.21, abs=0.5)
        assert _kpi(sales, "gross_sales").value == pytest.approx(152800.0)
        fin = _dept(card, "finance")
        # Quick Ratio ~1.4 (goal 3) ; A/R total >$400K (the documented pain) ; cash collected on-goal.
        assert _kpi(fin, "quick_ratio").value == pytest.approx(1.4, abs=0.02)
        assert _kpi(fin, "ar_total").value > 400_000
        assert _kpi(fin, "cash_collected").on_goal is True

    def test_fixture_top_rep_and_coaching_flag(self) -> None:
        sales = _dept(compute_scorecard(sd.load_fixture_scorecard_data()), "sales")
        by_name = {e.entity_name: e for e in sales.entities}
        assert "Aaron Scott" in by_name  # the top rep from the spec
        # Aaron is above the 32% close goal -> not coaching ; Devon is below -> coaching.
        assert by_name["Aaron Scott"].values["needs_coaching"] == pytest.approx(0.0)
        assert by_name["Devon Pierce"].values["needs_coaching"] == pytest.approx(1.0)
        assert by_name["Aaron Scott"].values["closing_pct"] > 32

    def test_fixture_technicians_anchor_to_dispatch_console(self) -> None:
        ops = _dept(compute_scorecard(sd.load_fixture_scorecard_data()), "operations")
        by_name = {e.entity_name: e for e in ops.entities}
        # Michael Charadia 64% util ; Naudeez Singh 73% ; Nico Roark 59% (the Supervisor Console rows).
        assert by_name["Michael Charadia"].values["utilization"] == pytest.approx(64.0, abs=0.5)
        assert by_name["Naudeez Singh"].values["utilization"] == pytest.approx(73.0, abs=0.5)
        assert by_name["Nico Roark"].values["utilization"] == pytest.approx(59.0, abs=0.5)

    def test_fixture_front_office_colette(self) -> None:
        fo = _dept(compute_scorecard(sd.load_fixture_scorecard_data()), "sales_marketing")
        names = {e.entity_name for e in fo.entities}
        assert "Colette Vance" in names  # the front-office CSR from the spec


# --------------------------------------------------------------------------------------------
# 7. JSON serialization — the example-JSON contract the frontend builds to
# --------------------------------------------------------------------------------------------


class TestJsonContract:
    def test_top_level_shape(self) -> None:
        payload = scorecard_to_json(compute_scorecard(_scenario(), weeks=13))
        assert set(payload) == {"period_weeks", "catalog", "departments"}
        # period_weeks echoes the REQUESTED window (the series simply carries the present columns).
        assert payload["period_weeks"] == 13

    def test_catalog_entry_shape(self) -> None:
        payload = scorecard_to_json(compute_scorecard(_scenario()))
        entry = next(c for c in payload["catalog"] if c["key"] == "closing_pct")
        assert entry == {
            "key": "closing_pct",
            "label": "Closing %",
            "department": "sales",
            "unit": "percent",
            "calculated": True,
            "goal": 32,
            "higher_is_better": True,
            "description": "Jobs sold ÷ opportunities × 100.",
        }

    def test_department_and_kpi_shape(self) -> None:
        payload = scorecard_to_json(compute_scorecard(_scenario()))
        sales = next(d for d in payload["departments"] if d["key"] == "sales")
        assert set(sales) == {"key", "label", "source", "entity_role", "entity_kpi_keys", "kpis", "entities"}
        assert sales["source"] == "ServiceTitan"
        assert sales["entity_role"] == "sales_rep"
        kpi = next(k for k in sales["kpis"] if k["key"] == "gross_sales")
        assert set(kpi) == {"key", "value", "goal", "on_goal", "delta_pct", "series"}
        assert kpi["value"] == pytest.approx(120000.0)
        assert all(set(p) == {"date", "value", "projected"} for p in kpi["series"])
        assert all(p["projected"] is False for p in kpi["series"])  # scorecard series are actuals

    def test_entity_shape(self) -> None:
        payload = scorecard_to_json(compute_scorecard(_scenario()))
        sales = next(d for d in payload["departments"] if d["key"] == "sales")
        ent = next(e for e in sales["entities"] if e["entity_id"] == "rep-top")
        assert set(ent) == {"entity_id", "entity_name", "role", "values", "headline_series"}
        assert ent["values"]["closing_pct"] == pytest.approx(80.0)

    def test_finance_serializes_with_no_entities(self) -> None:
        payload = scorecard_to_json(compute_scorecard(_scenario()))
        fin = next(d for d in payload["departments"] if d["key"] == "finance")
        assert fin["entity_role"] is None
        assert fin["entities"] == []
        assert fin["entity_kpi_keys"] == []
