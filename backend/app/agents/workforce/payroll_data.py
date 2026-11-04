"""Assemble a ``PayrollData`` bundle for the deterministic payroll engine.

DB-free (so it previews easily) and mode-driven, exactly like the rest of the ServiceTitan adapter
boundary (ADR 0005):

  * ``fixture`` (default) loads realistic JSON next to the existing ServiceTitan fixtures and
    materializes job-action / pay-form dates *relative to the pay-period start* (stored as day
    offsets) so the demo is always current. Zero credentials required.
  * ``live`` is a typed, **fail-closed** skeleton: it raises rather than fabricate payroll inputs,
    because pay figures must be verified against a real tenant before any money moves (ADR 0005).

The engine itself (``compute_payroll``) is pure and tested separately; this module only marshals the
ServiceTitan-shaped rows through the pure mappers in ``integrations/servicetitan/mappers.py``.
"""
from __future__ import annotations

import json
import pathlib
from datetime import date, timedelta

from app.agents.workforce.payroll import PayPeriod, PayrollData, PieceEarning, WorkdayHours, Worker
from app.config import Settings, get_settings
from app.integrations.servicetitan.mappers import (
    map_piece_earning,
    map_workday,
    map_worker,
)

FIXTURES_DIR = pathlib.Path(__file__).parents[2] / "integrations" / "servicetitan" / "fixtures"
DEFAULT_PERIOD_DAYS = 7


def _load(name: str) -> list[dict]:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


class PayrollSourceError(RuntimeError):
    """Live payroll inputs are not available — fail closed rather than fabricate pay (ADR 0005)."""


def _fixture_payroll_data(period: PayPeriod) -> PayrollData:
    """Build the engine inputs from the bundled fixtures, dated relative to ``period.start``."""
    workers: list[Worker] = [map_worker(row) for row in _load("payroll_workers.json")]

    workdays: list[WorkdayHours] = []
    for row in _load("payroll_jobactions.json"):
        work_date = period.start + timedelta(days=int(row["day_offset"]))
        workdays.append(map_workday(row, work_date=work_date))

    earnings: list[PieceEarning] = [map_piece_earning(row) for row in _load("payroll_earnings.json")]

    return PayrollData(
        period=period,
        workers=workers,
        workdays=workdays,
        piece_earnings=earnings,
    )


def _live_payroll_data(period: PayPeriod, settings: Settings) -> PayrollData:
    """Typed, fail-closed live skeleton.

    The real implementation pulls technicians/payroll-setup, job-actions (dispatch/completion
    timestamps + pay-form hours), and piece/commission job amounts from the live ServiceTitan client
    and maps them with ``map_worker`` / ``map_workday`` / ``map_piece_earning``. It intentionally
    raises until verified against a real tenant — we never guess pay inputs (ADR 0005).
    """
    raise PayrollSourceError(
        "live ServiceTitan payroll assembly is not yet wired; map the ST payroll/job-actions API "
        "to Worker/WorkdayHours/PieceEarning against a real tenant (ADR 0005) before enabling."
    )


def assemble_payroll_data(
    *,
    period_start: date,
    period_end: date | None = None,
    settings: Settings | None = None,
) -> PayrollData:
    """Assemble everything the payroll engine needs for one pay period.

    ``servicetitan_mode`` selects the source: ``fixture`` (default, offline) or ``live`` (fail-closed
    skeleton). The period defaults to a 7-day window from ``period_start``.
    """
    settings = settings or get_settings()
    end = period_end or (period_start + timedelta(days=DEFAULT_PERIOD_DAYS - 1))
    period = PayPeriod(start=period_start, end=end)

    if settings.servicetitan_mode.lower() == "live":
        return _live_payroll_data(period, settings)
    return _fixture_payroll_data(period)
