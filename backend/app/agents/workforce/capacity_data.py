"""Assemble the rolling-capacity engine inputs from the ServiceTitan adapter boundary.

DB-free (so it previews easily) and mode-driven, exactly like the rest of the ServiceTitan adapter
boundary (ADR 0005), mirroring ``payroll_data.py``:

  * ``fixture`` (default) loads the Canyon Ridge completed-job history + the upcoming assigned week from
    JSON next to the existing ServiceTitan fixtures, and materializes each completed job's
    ``completed_date`` *relative to the run's ``as_of``* (stored as ``weeks_ago`` offsets) so the
    moving-target + overtime demo is always current. Zero credentials required. The job-type baselines
    prior comes from the bundled ``job_durations.json`` (so "faster/slower than baseline" is anchored to
    the same numbers the rest of the Workforce agent already uses).
  * ``live`` is a typed, **fail-closed** skeleton: it raises rather than fabricate capacity inputs,
    because actual on-site hours must be verified against a real tenant (clock-in@dispatch ->
    clock-out@completion) before any schedule decision rests on them (ADR 0005).

The engine itself (``estimate_tech_durations`` / ``project_tech_overtime`` in ``capacity.py``) is pure
and tested separately; this module only marshals the source rows into its dataclasses.
"""
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass
from datetime import date, timedelta

from app.agents.workforce.capacity import AssignedJob, CompletedJob
from app.agents.workforce.models import Technician
from app.config import Settings, get_settings

FIXTURES_DIR = pathlib.Path(__file__).parents[2] / "integrations" / "servicetitan" / "fixtures"


class CapacitySourceError(RuntimeError):
    """Live capacity inputs are not available — fail closed rather than fabricate hours (ADR 0005)."""


@dataclass(frozen=True)
class CapacityData:
    """Everything the rolling-capacity engine needs for one analysis."""

    as_of: date
    completed_jobs: list[CompletedJob]
    assigned_jobs: list[AssignedJob]
    technicians: list[Technician]
    baselines: dict[str, float]


def _load(name: str) -> list[dict]:
    """Load a fixture, tolerating leading string entries used as inline documentation."""
    raw = json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))
    return [row for row in raw if isinstance(row, dict)]


def _map_completed_job(row: dict, *, as_of: date) -> CompletedJob:
    """A history row -> CompletedJob, dating it ``weeks_ago`` weeks back from ``as_of``."""
    return CompletedJob(
        technician_id=str(row["technician_id"]),
        job_type=str(row["job_type"]),
        trade=str(row["trade"]),
        actual_hours=float(row["actual_hours"]),
        completed_date=as_of - timedelta(weeks=int(row["weeks_ago"])),
    )


def _map_assigned_job(row: dict) -> AssignedJob:
    return AssignedJob(
        technician_id=str(row["technician_id"]),
        job_type=str(row["job_type"]),
        trade=str(row["trade"]),
    )


def _map_technician(row: dict) -> Technician:
    return Technician(
        id=str(row["id"]),
        name=str(row.get("name", row["id"])),
        trade=str(row.get("trade", "unknown")),
        contracted_weekly_hours=float(row.get("contracted_weekly_hours", 40)),
        hourly_cost=float(row.get("hourly_cost", 0.0)),
        overtime_multiplier=float(row.get("overtime_multiplier", 1.5)),
        active=bool(row.get("active", True)),
    )


def _baselines_from_durations() -> dict[str, float]:
    """Job-type -> mean-hours prior from the bundled job-duration stats (the comparison line)."""
    return {str(r["job_type"]): float(r["mean_hours"]) for r in _load("job_durations.json")}


def _relevant_technicians(
    completed: list[CompletedJob], assigned: list[AssignedJob]
) -> list[Technician]:
    """Active technicians who appear in the history or the upcoming week (so the projection covers
    exactly the techs the capacity story is about), in fixture order for a stable demo."""
    seen = {j.technician_id for j in completed} | {a.technician_id for a in assigned}
    return [
        _map_technician(row)
        for row in _load("technicians.json")
        if bool(row.get("active", True)) and str(row["id"]) in seen
    ]


def _fixture_capacity_data(as_of: date) -> CapacityData:
    completed = [_map_completed_job(r, as_of=as_of) for r in _load("capacity_completed_jobs.json")]
    assigned = [_map_assigned_job(r) for r in _load("capacity_assigned_jobs.json")]
    return CapacityData(
        as_of=as_of,
        completed_jobs=completed,
        assigned_jobs=assigned,
        technicians=_relevant_technicians(completed, assigned),
        baselines=_baselines_from_durations(),
    )


def _live_capacity_data(as_of: date, settings: Settings) -> CapacityData:
    """Typed, fail-closed live skeleton.

    The real implementation pulls each completed job's ACTUAL on-site hours from ServiceTitan
    job-actions / payroll job-splits (clock-in at dispatch -> clock-out at completion) for the trailing
    window, the upcoming week's assigned jobs from the dispatch board, and the technician roster from
    Settings — mapping them to ``CompletedJob`` / ``AssignedJob`` / ``Technician``. It intentionally
    raises until verified against a real tenant: we never guess on-site hours (ADR 0005).
    """
    raise CapacitySourceError(
        "live ServiceTitan capacity assembly is not yet wired; map ST job-actions/payroll job-splits "
        "(dispatch->completion clock) + the assigned-week dispatch board + the technician roster to "
        "CompletedJob/AssignedJob/Technician against a real tenant (ADR 0005) before enabling."
    )


def assemble_capacity_data(*, as_of: date, settings: Settings | None = None) -> CapacityData:
    """Assemble everything the rolling-capacity engine needs for one analysis.

    ``servicetitan_mode`` selects the source: ``fixture`` (default, offline) or ``live`` (fail-closed
    skeleton).
    """
    settings = settings or get_settings()
    if settings.servicetitan_mode.lower() == "live":
        return _live_capacity_data(as_of, settings)
    return _fixture_capacity_data(as_of)
