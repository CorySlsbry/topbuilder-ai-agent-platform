"""Assemble the deterministic ``ScorecardData`` bundle for the department scorecard.

Fixture mode loads the seeded **Canyon Ridge** weekly figures (anchored to the real Bloom Growth L10
captured in docs/ALEX_DISCOVERY_2026-06-16.md). Live mode is a fail-closed skeleton (ADR 0005): the
per-source mapping (ServiceTitan reporting + QuickBooks aging/P&L) must be verified against a real
tenant before it can serve a number, so it raises rather than fabricate one.

No DB. The route reads the bundle and hands it to the PURE ``scorecard.compute_scorecard`` engine.
"""
from __future__ import annotations

import json
import pathlib

from app.config import get_settings
from app.org.scorecard import (
    RawDepartment,
    RawEntity,
    RawEntityWeek,
    RawWeek,
    ScorecardData,
)

FIXTURE_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "integrations"
    / "servicetitan"
    / "fixtures"
    / "scorecard_canyonridge.json"
)


def _raw_week(row: dict) -> RawWeek:
    return RawWeek(date=str(row["date"]), figures=dict(row.get("figures", {})))


def _raw_entity(row: dict) -> RawEntity:
    return RawEntity(
        entity_id=str(row["entity_id"]),
        entity_name=str(row["entity_name"]),
        role=str(row["role"]),
        weeks=[RawEntityWeek(date=str(w["date"]), figures=dict(w.get("figures", {})))
               for w in row.get("weeks", [])],
    )


def _raw_department(row: dict) -> RawDepartment:
    return RawDepartment(
        key=str(row["key"]),
        weeks=[_raw_week(w) for w in row.get("weeks", [])],
        entities=[_raw_entity(e) for e in row.get("entities", [])],
    )


def load_fixture_scorecard_data(path: pathlib.Path | None = None) -> ScorecardData:
    """Parse the Canyon Ridge fixture JSON into a ``ScorecardData`` bundle (pure parse, no IO beyond
    the single file read). Money in the JSON is integer cents; the engine emits dollars."""
    payload = json.loads((path or FIXTURE_PATH).read_text(encoding="utf-8"))
    return ScorecardData(
        departments=[_raw_department(d) for d in payload.get("departments", [])],
        business_days_per_week=int(payload.get("business_days_per_week", 5)),
        calls_per_tech_per_day=float(payload.get("calls_per_tech_per_day", 8.0)),
    )


def get_scorecard_data() -> ScorecardData:
    """Resolve the scorecard data source from config.

    ``SERVICETITAN_MODE=fixture`` (the default for the demo) loads Canyon Ridge. Any other value is
    treated as live and FAILS CLOSED — the live ServiceTitan/QuickBooks mapping is not yet verified
    against a real tenant, so we raise rather than serve a guessed figure (ADR 0003 + ADR 0005)."""
    settings = get_settings()
    if settings.servicetitan_mode == "fixture":
        return load_fixture_scorecard_data()
    raise RuntimeError(
        "Department scorecard live mode is not yet wired: map ServiceTitan reporting "
        "(sales/ops/front-office weekly figures) + QuickBooks (cash/aging/P&L) to the scorecard "
        "raw schema and verify units against a real tenant before serving live figures."
    )
