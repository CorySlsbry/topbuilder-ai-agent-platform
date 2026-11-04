"""Pure orchestration + mapping oracles for the payroll agent path (no DB, no LLM).

These exercise everything between the ServiceTitan-shaped rows and the deterministic engine: the
mappers (role -> pay class, dispatch/completion -> clocked hours, pay-form -> claimed hours, job
amounts -> cents), the fixture assembler, the narration template (ADR-0003: never recomputes), the
result schema mapper, and the action-param helper. The numbers are hand-computed independent oracles
and match the engine scenario in ``tests/test_payroll.py``.
"""
from __future__ import annotations

from datetime import UTC, date

import pytest

from app.agents.workforce import payroll as p
from app.agents.workforce import payroll_reasoning
from app.agents.workforce.payroll import PayPeriod, PayrollData, compute_payroll
from app.agents.workforce.payroll_data import assemble_payroll_data
from app.agents.workforce.payroll_schemas import PayrollRunResult, build_result
from app.agents.workforce.payroll_service import proposed_adjustment_params
from app.config import Settings
from app.integrations.servicetitan import mappers

PERIOD_START = date(2026, 6, 1)  # a Monday


# --------------------------------------------------------------------------------------------
# Mappers: ServiceTitan-shaped rows -> engine inputs
# --------------------------------------------------------------------------------------------
class TestPayClassForRole:
    @pytest.mark.parametrize(
        "role, expected",
        [
            ("service", p.PAY_HOURLY),
            ("Service", p.PAY_HOURLY),  # case-insensitive
            ("install", p.PAY_PIECE_RATE),
            ("installer", p.PAY_PIECE_RATE),
            ("sales", p.PAY_COMMISSION),
            ("comfort_advisor", p.PAY_COMMISSION),
        ],
    )
    def test_known_roles(self, role: str, expected: str) -> None:
        assert mappers.pay_class_for_role(role) == expected

    def test_unknown_role_fails_safe_to_hourly(self) -> None:
        # Unknown -> hourly (the only class that can accrue OT) so a worker is never under-paid.
        assert mappers.pay_class_for_role("plumber-apprentice") == p.PAY_HOURLY
        assert mappers.pay_class_for_role("") == p.PAY_HOURLY


class TestMapWorker:
    def test_service_tech_is_hourly_with_rate(self) -> None:
        w = mappers.map_worker({"id": "t1", "name": "Aaron", "role": "service", "hourly_rate": 40.0})
        assert (w.id, w.name, w.pay_class, w.hourly_rate) == ("t1", "Aaron", p.PAY_HOURLY, 40.0)

    def test_name_defaults_to_id_and_rate_defaults_zero(self) -> None:
        w = mappers.map_worker({"id": "t9", "role": "install"})
        assert (w.id, w.name, w.pay_class, w.hourly_rate) == ("t9", "t9", p.PAY_PIECE_RATE, 0.0)


class TestMapWorkday:
    def test_clocked_hours_from_dispatch_to_completion(self) -> None:
        # 08:00 -> 21:00 = 13h clocked; pay-form claims nothing.
        wd = mappers.map_workday(
            {"worker_id": "t1", "dispatched_at": "08:00:00", "completed_at": "21:00:00"},
            work_date=PERIOD_START,
        )
        assert wd.computed_hours == pytest.approx(13.0)
        assert wd.claimed_hours is None
        assert wd.work_date == PERIOD_START

    def test_claimed_hours_carried_when_present(self) -> None:
        wd = mappers.map_workday(
            {
                "worker_id": "t2",
                "dispatched_at": "08:00:00",
                "completed_at": "16:00:00",
                "claimed_hours": 12.0,
            },
            work_date=PERIOD_START,
        )
        # clock shows 8h, the tech self-reported 12h on the pay form.
        assert wd.computed_hours == pytest.approx(8.0)
        assert wd.claimed_hours == pytest.approx(12.0)


class TestMapPieceEarning:
    def test_cents_preserved_as_int(self) -> None:
        pe = mappers.map_piece_earning(
            {"worker_id": "i1", "job_id": "j1", "kind": "piece", "amount_cents": 80000}
        )
        assert (pe.worker_id, pe.job_id, pe.amount_cents, pe.kind) == ("i1", "j1", 80000, "piece")


# --------------------------------------------------------------------------------------------
# Fixture assembler -> engine: reproduces the test_payroll.py oracle from ST-shaped fixtures.
#   Aaron (service/hourly): one 13h day  -> 8 reg + 4 OT + 1 DT @ $40 = $640
#   Beth  (service/hourly): six 8h days  -> 40 reg + 8 weekly OT @ $40 = $2,080, gap +4h
#   Carl  (install/piece) : two pieces   -> $2,000, clock 12h vs claimed 16h -> gap +4h
#   Dana  (sales/commission): two commissions -> $1,200
#   Total gross = $5,920 ; flagged = 2
# --------------------------------------------------------------------------------------------
def _fixture_run() -> p.PayrollRun:
    data = assemble_payroll_data(period_start=PERIOD_START, settings=Settings(servicetitan_mode="fixture"))
    return compute_payroll(data)


def _pay(run: p.PayrollRun, worker_id: str) -> p.WorkerPay:
    return next(wp for wp in run.worker_pays if wp.worker_id == worker_id)


class TestAssembleFixturePayrollData:
    def test_period_window_defaults_to_seven_days(self) -> None:
        data = assemble_payroll_data(
            period_start=PERIOD_START, settings=Settings(servicetitan_mode="fixture")
        )
        assert isinstance(data, PayrollData)
        assert (data.period.start, data.period.end) == (PERIOD_START, date(2026, 6, 7))

    def test_aaron_daily_ot_and_dt(self) -> None:
        wp = _pay(_fixture_run(), "tech-001")
        assert (wp.regular_hours, wp.overtime_hours, wp.doubletime_hours) == pytest.approx((8, 4, 1))
        assert wp.gross_pay_cents == 64_000  # $640
        assert wp.needs_review is False

    def test_beth_weekly_ot_and_gap(self) -> None:
        wp = _pay(_fixture_run(), "tech-002")
        assert (wp.regular_hours, wp.overtime_hours, wp.doubletime_hours) == pytest.approx((40, 8, 0))
        assert wp.gross_pay_cents == 208_000  # $2,080
        # claimed 12 + 8*5 = 52h vs clocked 48h -> +4h, flagged
        assert wp.claimed_hours == pytest.approx(52.0)
        assert wp.computed_hours == pytest.approx(48.0)
        assert wp.needs_review is True

    def test_carl_piece_rate_pay_from_jobs_with_hours_gap(self) -> None:
        wp = _pay(_fixture_run(), "tech-101")
        assert wp.gross_pay_cents == 200_000  # $2,000 from two pieces, never hours
        assert (wp.regular_hours, wp.overtime_hours, wp.doubletime_hours) == pytest.approx((0, 0, 0))
        assert wp.hours_discrepancy == pytest.approx(4.0)  # 16 claimed vs 12 clocked
        assert wp.needs_review is True

    def test_dana_commission(self) -> None:
        wp = _pay(_fixture_run(), "sales-201")
        assert wp.gross_pay_cents == 120_000  # $500 + $700
        assert wp.needs_review is False

    def test_run_totals_and_flag_count(self) -> None:
        run = _fixture_run()
        assert run.total_gross_cents == 592_000  # $5,920
        assert run.flagged_count == 2


class TestAssembleLiveFailsClosed:
    def test_live_mode_raises_rather_than_fabricate(self) -> None:
        from app.agents.workforce.payroll_data import PayrollSourceError

        with pytest.raises(PayrollSourceError):
            assemble_payroll_data(
                period_start=PERIOD_START, settings=Settings(servicetitan_mode="live")
            )


# --------------------------------------------------------------------------------------------
# Narration template (ADR-0003: never recomputes — only quotes the engine figures)
# --------------------------------------------------------------------------------------------
class TestNarrationTemplate:
    async def test_template_quotes_total_and_flags(self) -> None:
        run = _fixture_run()
        text = await payroll_reasoning.explain(run, Settings(disable_llm=True))
        assert "$5,920.00" in text
        assert "2 worker(s)" in text  # the flagged-for-review count
        # the two flagged workers are named, the clean ones are not in the review list
        assert "Beth Calloway" in text and "Carl Dominguez" in text

    async def test_template_no_flags_when_clean(self) -> None:
        # A clean single hourly worker, no claimed hours -> no discrepancy section.
        data = PayrollData(
            period=PayPeriod(PERIOD_START, date(2026, 6, 7)),
            workers=[p.Worker("w1", "Solo", p.PAY_HOURLY, hourly_rate=30.0)],
            workdays=[p.WorkdayHours("w1", PERIOD_START, computed_hours=8.0)],
        )
        text = await payroll_reasoning.explain(compute_payroll(data), Settings(disable_llm=True))
        assert "No pay-form discrepancies" in text


# --------------------------------------------------------------------------------------------
# Result schema mapper + the action-param helper
# --------------------------------------------------------------------------------------------
def _result() -> PayrollRunResult:
    from datetime import datetime

    return build_result(
        _fixture_run(),
        narrative="x",
        analysis_timestamp=datetime(2026, 6, 8, tzinfo=UTC),
    )


class TestBuildResult:
    def test_usd_rollup_matches_engine_cents(self) -> None:
        res = _result()
        assert res.totals.total_gross_usd == pytest.approx(5920.0)
        assert res.totals.flagged_count == 2
        assert res.totals.workers == 4
        carl = next(wp for wp in res.worker_pays if wp.worker_id == "tech-101")
        assert carl.gross_pay_usd == pytest.approx(2000.0)


class TestProposedAdjustmentParams:
    def test_builds_params_for_flagged_worker(self) -> None:
        params = proposed_adjustment_params(_result(), "tech-002")
        assert params["worker_id"] == "tech-002"
        assert params["worker_name"] == "Beth Calloway"
        assert params["claimed_hours"] == pytest.approx(52.0)
        assert params["computed_hours"] == pytest.approx(48.0)
        assert params["hours_discrepancy"] == pytest.approx(4.0)
        assert params["period_start"] == "2026-06-01"

    def test_refuses_a_clean_worker(self) -> None:
        # Dana (commission) has no discrepancy -> the gate is never asked to adjust her.
        with pytest.raises(ValueError, match="no pay-form discrepancy"):
            proposed_adjustment_params(_result(), "sales-201")

    def test_refuses_unknown_worker(self) -> None:
        with pytest.raises(ValueError, match="not in this payroll run"):
            proposed_adjustment_params(_result(), "ghost-999")
