"""Fixture-backed dispatch client — a realistic day of jobs + technicians (zone coords)."""
from __future__ import annotations

import json
import pathlib
from datetime import date

from app.agents.routing.models import DispatchJob, FieldTech

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"


def _load(name: str) -> list[dict]:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


class FixtureDispatchClient:
    async def get_jobs(self, as_of: date) -> list[DispatchJob]:
        return [DispatchJob(**row) for row in _load("jobs.json")]

    async def get_technicians(self) -> list[FieldTech]:
        return [FieldTech(**row) for row in _load("technicians.json")]

    # Summit-shaped triage feed: a no-heat P1, electrical/plumbing/install trades, "Aaron Scott"
    # as the top-revenue tech. Kept separate from the drive-time feed so each engine has a focused set.
    async def get_triage_jobs(self, as_of: date) -> list[DispatchJob]:
        return [DispatchJob(**row) for row in _load("triage_jobs.json")]

    async def get_triage_technicians(self) -> list[FieldTech]:
        return [FieldTech(**row) for row in _load("triage_technicians.json")]
