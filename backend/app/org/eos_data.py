"""Assemble the deterministic EOS bundle (issues + business plan) for the communication hub.

Fixture mode loads the seeded **Canyon Ridge** issues + business plan (anchored to the real pains in
docs/ALEX_DISCOVERY_2026-06-16.md and the Finance measurables in docs/QBO_DATA_MAP.md). Live mode is
a fail-closed skeleton (ADR 0005): the business-plan numbers must be mapped from QuickBooks P&L
(budget-to-actual + trailing-12 per QBO_DATA_MAP §3.2) and verified against a real company before they
can serve a figure, so it raises rather than fabricate one.

No DB. The route reads the bundle and hands it to the PURE ``eos`` engine. Issues are returned as a
list the route overlays its tenant-scoped create/resolve store on top of.
"""
from __future__ import annotations

import json
import pathlib

from app.config import get_settings
from app.org.eos import (
    AnnualGoal,
    BudgetLine,
    BusinessPlan,
    Issue,
    TrailingPoint,
)

FIXTURE_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "integrations"
    / "servicetitan"
    / "fixtures"
    / "eos_canyonridge.json"
)


def _issue(row: dict) -> Issue:
    return Issue(
        id=str(row["id"]),
        title=str(row["title"]),
        owner=str(row.get("owner", "Unassigned")),
        department=str(row.get("department", "")),
        priority=int(row.get("priority", 2)),
        status=str(row.get("status", "open")),
        created=str(row["created"]),
        resolved=(str(row["resolved"]) if row.get("resolved") else None),
    )


def _goal(row: dict) -> AnnualGoal:
    return AnnualGoal(
        key=str(row["key"]),
        label=str(row["label"]),
        unit=str(row["unit"]),
        target=row["target"],
        actual=row.get("actual"),
        higher_is_better=bool(row.get("higher_is_better", True)),
    )


def _line(row: dict) -> BudgetLine:
    return BudgetLine(
        key=str(row["key"]),
        label=str(row["label"]),
        kind=str(row["kind"]),
        budget_cents=int(row["budget_cents"]),
        actual_cents=int(row["actual_cents"]),
    )


def _trailing(row: dict) -> TrailingPoint:
    return TrailingPoint(
        month=str(row["month"]),
        revenue_cents=int(row["revenue_cents"]),
        net_income_cents=int(row["net_income_cents"]),
    )


def _payload(path: pathlib.Path | None = None) -> dict:
    return json.loads((path or FIXTURE_PATH).read_text(encoding="utf-8"))


def load_fixture_issues(path: pathlib.Path | None = None) -> list[Issue]:
    """Parse the seeded Canyon Ridge issues (pure parse, single file read)."""
    return [_issue(r) for r in _payload(path).get("issues", [])]


def load_fixture_business_plan(path: pathlib.Path | None = None) -> BusinessPlan:
    """Parse the seeded Canyon Ridge business plan into a ``BusinessPlan`` (money in CENTS)."""
    data = _payload(path)
    return BusinessPlan(
        company=str(data.get("company", "")),
        fiscal_year=int(data.get("fiscal_year", 0)),
        period_label=str(data.get("period_label", "")),
        annual_goals=[_goal(g) for g in data.get("annual_goals", [])],
        budget_lines=[_line(line) for line in data.get("budget_to_actual", [])],
        trailing_12=[_trailing(p) for p in data.get("trailing_12", [])],
    )


def get_seed_issues() -> list[Issue]:
    """The seed issue list (fixture). Live mode reuses the same shape — issues are OUR store, not a
    QBO/ServiceTitan read — so it does not fail closed; a live tenant simply starts with no seed."""
    settings = get_settings()
    if settings.servicetitan_mode == "fixture":
        return load_fixture_issues()
    return []


def get_business_plan() -> BusinessPlan:
    """Resolve the business-plan data source from config.

    ``SERVICETITAN_MODE=fixture`` (the demo default) loads Canyon Ridge. Any other value is treated as
    live and FAILS CLOSED — the QuickBooks P&L mapping (budget-to-actual + trailing-12, per
    docs/QBO_DATA_MAP §3.2) is not yet verified against a real company, so we raise rather than serve a
    guessed figure (ADR 0003 + ADR 0005)."""
    settings = get_settings()
    if settings.servicetitan_mode == "fixture":
        return load_fixture_business_plan()
    raise RuntimeError(
        "Business-plan live mode is not yet wired: map QuickBooks ProfitAndLoss "
        "(budget-to-actual by month + trailing-12) + the annual goals to the business-plan schema "
        "and verify units against a real tenant before serving live figures."
    )
