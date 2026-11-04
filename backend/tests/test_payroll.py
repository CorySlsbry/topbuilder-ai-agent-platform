"""Unit + property tests for the deterministic payroll engine.

The ``compute_payroll()`` scenario is hand-computed so every asserted number is an independent
oracle. The overtime cases follow California rules (the client's stated basis): >8h/day at 1.5x,
>12h/day at 2.0x, >40 straight-time hours/week at 1.5x, with no pyramiding.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.agents.workforce import payroll as p
from app.agents.workforce.payroll import (
    PayPeriod,
    PayrollData,
    PieceEarning,
    Worker,
    WorkdayHours,
)

WEEK_MON = date(2026, 6, 1)  # a Monday


# --------------------------------------------------------------------------------------------
# Pure primitives
# --------------------------------------------------------------------------------------------
class TestDailyOvertimeSplit:
    @pytest.mark.parametrize(
        "hours, expected",
        [
            (0, (0, 0, 0)),
            (6, (6, 0, 0)),
            (8, (8, 0, 0)),
            (10, (8, 2, 0)),
            (12, (8, 4, 0)),
            (13, (8, 4, 1)),  # Alex's "16 hours" install day lives in this regime
            (16, (8, 4, 4)),
        ],
    )
    def test_known(self, hours: float, expected: tuple[float, float, float]) -> None:
        assert p.daily_overtime_split(hours) == pytest.approx(expected)

    @given(st.floats(min_value=0, max_value=36))
    def test_buckets_sum_to_hours(self, hours: float) -> None:
        reg, ot, dt = p.daily_overtime_split(hours)
        assert reg + ot + dt == pytest.approx(hours)

    @given(st.floats(min_value=0, max_value=36))
    def test_bucket_caps(self, hours: float) -> None:
        reg, ot, dt = p.daily_overtime_split(hours)
        assert 0 <= reg <= p.DAILY_OT_THRESHOLD
        assert 0 <= ot <= (p.DAILY_DT_THRESHOLD - p.DAILY_OT_THRESHOLD)
        assert dt >= 0


class TestApplyWeeklyOvertime:
    @pytest.mark.parametrize(
        "regular, expected",
        [(30, (30, 0)), (40, (40, 0)), (48, (40, 8)), (40.5, (40, 0.5))],
    )
    def test_known(self, regular: float, expected: tuple[float, float]) -> None:
        assert p.apply_weekly_overtime(regular) == pytest.approx(expected)

    @given(st.floats(min_value=0, max_value=120))
    def test_conserves_total(self, regular: float) -> None:
        reg_after, weekly_ot = p.apply_weekly_overtime(regular)
        assert reg_after + weekly_ot == pytest.approx(regular)


class TestGrossPayCents:
    def test_regular_only(self) -> None:
        # 40h @ $50 = $2,000
        assert p.gross_pay_cents(40, 0, 0, 50.0) == 200_000

    def test_with_overtime(self) -> None:
        # 8h reg + 2h OT @ $40, 1.5x -> 320 + 120 = $440
        assert p.gross_pay_cents(8, 2, 0, 40.0) == 44_000

    def test_with_doubletime(self) -> None:
        # 8h reg + 4h OT + 1h DT @ $40 -> 320 + 240 + 80 = $640
        assert p.gross_pay_cents(8, 4, 1, 40.0) == 64_000

    @given(
        st.floats(0, 40),
        st.floats(0, 20),
        st.floats(0, 12),
        st.floats(0, 200),
    )
    def test_non_negative(self, reg: float, ot: float, dt: float, rate: float) -> None:
        assert p.gross_pay_cents(reg, ot, dt, rate) >= 0


class TestHoursDiscrepancy:
    def test_over_claim(self) -> None:
        # claimed 16h, clock shows 12h -> +4h over-reported
        assert p.hours_discrepancy(16, 12) == pytest.approx(4.0)

    def test_under_claim(self) -> None:
        assert p.hours_discrepancy(8, 8.5) == pytest.approx(-0.5)


# --------------------------------------------------------------------------------------------
# Scenario for compute_payroll(): one weekly pay period, the three worker classes, two gaps.
#   - Aaron  (service/hourly): one 13h day -> daily OT(4) + DT(1)            -> $640
#   - Beth   (service/hourly): six 8h days -> weekly OT(8) over 40           -> $2,080, gap +4h
#   - Carl   (install/piece) : two job pieces, clock 12h vs claimed 16h      -> $2,000, gap +4h
#   - Dana   (sales/commission): two commissions                            -> $1,200
# --------------------------------------------------------------------------------------------
def _scenario() -> PayrollData:
    workers = [
        Worker("svc1", "Aaron", p.PAY_HOURLY, hourly_rate=40.0),
        Worker("svc2", "Beth", p.PAY_HOURLY, hourly_rate=40.0),
        Worker("inst1", "Carl", p.PAY_PIECE_RATE),
        Worker("sales1", "Dana", p.PAY_COMMISSION),
    ]
    workdays = [
        # Aaron: single long day -> daily overtime + double-time, no claim.
        WorkdayHours("svc1", WEEK_MON, computed_hours=13.0),
        # Beth: six 8h days = 48h straight -> 8h weekly OT; over-claims 4h on Monday.
        WorkdayHours("svc2", date(2026, 6, 1), computed_hours=8.0, claimed_hours=12.0),
        WorkdayHours("svc2", date(2026, 6, 2), computed_hours=8.0, claimed_hours=8.0),
        WorkdayHours("svc2", date(2026, 6, 3), computed_hours=8.0, claimed_hours=8.0),
        WorkdayHours("svc2", date(2026, 6, 4), computed_hours=8.0, claimed_hours=8.0),
        WorkdayHours("svc2", date(2026, 6, 5), computed_hours=8.0, claimed_hours=8.0),
        WorkdayHours("svc2", date(2026, 6, 6), computed_hours=8.0, claimed_hours=8.0),
        # Carl: pay-form says 16h, clock says 12h (the gap Alex described) — piece-rate pay though.
        WorkdayHours("inst1", date(2026, 6, 3), computed_hours=12.0, claimed_hours=16.0),
    ]
    pieces = [
        PieceEarning("inst1", "j1", 80_000, kind="piece"),
        PieceEarning("inst1", "j2", 120_000, kind="piece"),
        PieceEarning("sales1", "c1", 50_000, kind="commission"),
        PieceEarning("sales1", "c2", 70_000, kind="commission"),
    ]
    return PayrollData(
        period=PayPeriod(date(2026, 6, 1), date(2026, 6, 7)),
        workers=workers,
        workdays=workdays,
        piece_earnings=pieces,
    )


def _pay(run: p.PayrollRun, worker_id: str) -> p.WorkerPay:
    return next(wp for wp in run.worker_pays if wp.worker_id == worker_id)


class TestComputePayrollHourly:
    def test_aaron_daily_overtime_and_doubletime(self) -> None:
        wp = _pay(p.compute_payroll(_scenario()), "svc1")
        # 13h day -> 8 reg, 4 OT (8..12), 1 DT (>12)
        assert (wp.regular_hours, wp.overtime_hours, wp.doubletime_hours) == pytest.approx((8, 4, 1))
        # 8*40 + 4*40*1.5 + 1*40*2 = 320 + 240 + 80 = $640
        assert wp.gross_pay_cents == 64_000
        assert wp.needs_review is False

    def test_beth_weekly_overtime(self) -> None:
        wp = _pay(p.compute_payroll(_scenario()), "svc2")
        # six 8h days = 48h straight -> 40 reg + 8 weekly OT, no daily OT
        assert (wp.regular_hours, wp.overtime_hours, wp.doubletime_hours) == pytest.approx((40, 8, 0))
        # 40*40 + 8*40*1.5 = 1600 + 480 = $2,080
        assert wp.gross_pay_cents == 208_000

    def test_beth_payroll_gap_flagged(self) -> None:
        wp = _pay(p.compute_payroll(_scenario()), "svc2")
        # claimed 12+8*5 = 52h vs computed 48h -> +4h, flagged
        assert wp.claimed_hours == pytest.approx(52.0)
        assert wp.computed_hours == pytest.approx(48.0)
        assert wp.hours_discrepancy == pytest.approx(4.0)
        assert wp.needs_review is True


class TestComputePayrollPieceAndCommission:
    def test_carl_piece_rate_pay_from_jobs_not_hours(self) -> None:
        wp = _pay(p.compute_payroll(_scenario()), "inst1")
        # piece-rate: gross is the two job amounts, never hours
        assert wp.gross_pay_cents == 200_000
        assert (wp.regular_hours, wp.overtime_hours, wp.doubletime_hours) == pytest.approx((0, 0, 0))

    def test_carl_hours_gap_still_flagged_for_costing(self) -> None:
        wp = _pay(p.compute_payroll(_scenario()), "inst1")
        # 16h claimed vs 12h clocked -> flagged even though pay is unaffected
        assert wp.hours_discrepancy == pytest.approx(4.0)
        assert wp.needs_review is True

    def test_dana_commission(self) -> None:
        wp = _pay(p.compute_payroll(_scenario()), "sales1")
        assert wp.gross_pay_cents == 120_000  # $500 + $700
        assert wp.needs_review is False


class TestComputePayrollRun:
    def test_totals_and_flag_count(self) -> None:
        run = p.compute_payroll(_scenario())
        # 64000 + 208000 + 200000 + 120000
        assert run.total_gross_cents == 592_000
        assert run.flagged_count == 2

    def test_flagged_workers_sort_first(self) -> None:
        run = p.compute_payroll(_scenario())
        # Beth (gap +4h, gross 2080) sorts ahead of Carl (gap +4h, gross 2000); both ahead of clean.
        assert [wp.worker_id for wp in run.worker_pays[:2]] == ["svc2", "inst1"]
        assert all(wp.needs_review for wp in run.worker_pays[:2])
        assert not any(wp.needs_review for wp in run.worker_pays[2:])

    def test_inputs_hash_stable_and_hex(self) -> None:
        h1 = p.compute_payroll(_scenario()).inputs_hash
        h2 = p.compute_payroll(_scenario()).inputs_hash
        assert h1 == h2
        assert len(h1) == 64 and all(ch in "0123456789abcdef" for ch in h1)


def _one_worker_week(anchor: int | None, *, jurisdiction: str = p.JURISDICTION_BC):
    """A single hourly worker logging 8h on each of the 7 days starting Thursday 2026-06-04."""
    thu = date(2026, 6, 4)  # 2026-06-01 is a Monday, so the 4th is a Thursday
    workers = [Worker("w", "W", p.PAY_HOURLY, hourly_rate=40.0)]
    workdays = [WorkdayHours("w", thu + timedelta(days=i), computed_hours=8.0) for i in range(7)]
    return PayrollData(
        period=PayPeriod(thu, thu + timedelta(days=6)),
        workers=workers,
        workdays=workdays,
        jurisdiction=jurisdiction,
        workweek_starts_on=anchor,
    )


class TestWeeklyOvertimeAnchoring:
    """Weekly OT must follow the EMPLOYER'S workweek, not a hardcoded ISO-Monday week."""

    def test_thursday_workweek_anchor_counts_weekly_ot(self) -> None:
        # workweek_starts_on=Thursday(3): all 56h fall in one workweek -> 40 reg + 16 weekly OT.
        wp = _pay(p.compute_payroll(_one_worker_week(anchor=3)), "w")
        assert (wp.regular_hours, wp.overtime_hours, wp.doubletime_hours) == pytest.approx((40, 16, 0))

    def test_bc_default_uses_sunday_saturday_week(self) -> None:
        # No explicit anchor + default BC jurisdiction -> Sunday-Saturday weeks. The Thu-start 56h
        # splits across two Sunday weeks (Thu-Sat 24h + Sun-Wed 32h), neither over 40 -> 56 reg, 0 OT.
        wp = _pay(p.compute_payroll(_one_worker_week(anchor=None)), "w")
        assert (wp.regular_hours, wp.overtime_hours) == pytest.approx((56, 0))

    def test_ca_jurisdiction_defaults_to_period_start_week(self) -> None:
        # jurisdiction="CA" with no explicit anchor -> the pay-period start weekday is the workweek,
        # so the Thu-start period IS one workweek -> 40 reg + 16 OT.
        wp = _pay(p.compute_payroll(_one_worker_week(anchor=None, jurisdiction=p.JURISDICTION_CA)), "w")
        assert (wp.regular_hours, wp.overtime_hours) == pytest.approx((40, 16))

    def test_monday_anchor_splits_thursday_period_across_two_workweeks(self) -> None:
        # An explicit Monday workweek splits the Thu-start 56h into 32h (Thu-Sun) + 24h (Mon-Wed),
        # neither over 40 -> 56 reg, 0 OT.
        wp = _pay(p.compute_payroll(_one_worker_week(anchor=0)), "w")
        assert (wp.regular_hours, wp.overtime_hours) == pytest.approx((56, 0))


class TestBritishColumbiaOvertime:
    """BC Employment Standards Act (Part 4, s.40) — the client's jurisdiction (Vancouver Island, BC).
    Daily >8h -> 1.5x, >12h -> 2x; weekly >40h -> 1.5x counting only the first 8h/day; Sunday-Saturday
    week; and NO 7th-consecutive-day premium (that is a California rule BC does not have)."""

    @staticmethod
    def _consecutive_8h_week(n_days: int) -> PayrollData:
        # n consecutive 8h days starting Sunday 2026-06-07, all inside ONE Sunday-Saturday week
        # (Jun 7 Sun .. Jun 13 Sat). Default BC jurisdiction -> Sunday anchor.
        sun = date(2026, 6, 7)
        return PayrollData(
            period=PayPeriod(sun, sun + timedelta(days=6)),
            workers=[Worker("w", "W", p.PAY_HOURLY, hourly_rate=40.0)],
            workdays=[WorkdayHours("w", sun + timedelta(days=i), computed_hours=8.0) for i in range(n_days)],
        )

    def test_bc_daily_overtime_and_doubletime(self) -> None:
        data = PayrollData(
            period=PayPeriod(date(2026, 6, 8), date(2026, 6, 8)),
            workers=[Worker("w", "W", p.PAY_HOURLY, hourly_rate=40.0)],
            workdays=[WorkdayHours("w", date(2026, 6, 8), computed_hours=13.0)],
        )
        wp = _pay(p.compute_payroll(data), "w")
        # 13h -> 8 reg, 4 OT (8..12), 1 DT (>12); gross 8*40 + 4*60 + 1*80 = $640.
        assert (wp.regular_hours, wp.overtime_hours, wp.doubletime_hours) == pytest.approx((8, 4, 1))
        assert wp.gross_pay_cents == 64_000

    def test_bc_weekly_overtime_counts_first_8_per_day(self) -> None:
        # Six 8h days in one Sunday week = 48h -> 40 reg + 8 weekly OT, no daily OT.
        wp = _pay(p.compute_payroll(self._consecutive_8h_week(6)), "w")
        assert (wp.regular_hours, wp.overtime_hours, wp.doubletime_hours) == pytest.approx((40, 8, 0))

    def test_bc_has_no_seventh_consecutive_day_premium(self) -> None:
        # SEVEN consecutive 8h days in one Sunday week = 56h. BC has NO 7th-day premium, so this is
        # purely weekly OT: 40 reg + 16 weekly OT, and crucially 0 double-time. (California would add a
        # 7th-consecutive-day premium here; BC does not.) Gross = 40*40 + 16*60 = $2,560.
        wp = _pay(p.compute_payroll(self._consecutive_8h_week(7)), "w")
        assert (wp.regular_hours, wp.overtime_hours, wp.doubletime_hours) == pytest.approx((40, 16, 0))
        assert wp.gross_pay_cents == 256_000


def test_payroll_adjustment_is_always_hitl() -> None:
    # Payroll writes pay — it must never auto-execute even when an agent is in 'auto' mode.
    from app.actions.service import ALWAYS_HITL_KINDS

    assert "payroll_adjustment" in ALWAYS_HITL_KINDS


def test_regulated_and_financial_kinds_are_always_hitl() -> None:
    """Outbound customer contact (TCPA/CASL) and book-writing/vendor-session actions must stay
    human-in-the-loop even under agent mode='auto' — auto queues them, it never self-fires them."""
    from app.actions.service import ALWAYS_HITL_KINDS

    for kind in (
        "place_dunning_call",
        "send_dunning_sms",
        "send_dunning_email",
        "create_ap_draft",
        "register_warranty",
    ):
        assert kind in ALWAYS_HITL_KINDS, kind
