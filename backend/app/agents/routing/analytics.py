"""Deterministic dispatch-routing engine: skill-constrained, window-aware nearest-stop assignment.

No LLM, no randomness. Assigns each job to the eligible technician that adds the least drive time,
respecting skills, shift capacity, and arrival windows; reports the drive time saved vs. a naive
round-robin baseline. The reasoning layer narrates; it never decides. Output is ADVISORY (a dispatcher
accepts a suggestion) per the product decision.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date

from app.agents.routing.models import DispatchData, DispatchJob, FieldTech

MINUTES_PER_UNIT = 3   # drive minutes per zone-distance unit
ROUTE_CONFIDENCE = 0.9


# --------------------------------------------------------------------------------------------
# Result types
# --------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class RoutingSuggestion:
    job_id: str
    customer_name: str
    trade: str
    required_skill: str
    tech_id: str
    tech_name: str
    sequence: int          # 1 = this tech's first stop of the day
    drive_minutes: int     # added drive from the tech's previous stop
    arrival_min: int
    confidence: float
    reasoning: str


@dataclass(frozen=True)
class UnassignedJob:
    job_id: str
    trade: str
    reason: str


@dataclass(frozen=True)
class RoutingTotals:
    jobs: int
    assigned: int
    unassigned: int
    techs_used: int
    drive_minutes_optimized: int
    drive_minutes_baseline: int
    drive_minutes_saved: int


@dataclass(frozen=True)
class RoutingAnalysis:
    as_of: date
    suggestions: list[RoutingSuggestion]
    unassigned: list[UnassignedJob]
    totals: RoutingTotals
    inputs_hash: str


# --------------------------------------------------------------------------------------------
# Pure primitives
# --------------------------------------------------------------------------------------------
def _manhattan(ax: int, ay: int, bx: int, by: int) -> int:
    return abs(ax - bx) + abs(ay - by)


def _drive(distance: int) -> int:
    return distance * MINUTES_PER_UNIT


def eligible_techs(job: DispatchJob, techs: list[FieldTech]) -> list[FieldTech]:
    return [t for t in techs if job.required_skill in t.skills]


def _fmt(minutes: int) -> str:
    h, m = divmod(int(minutes), 60)
    return f"{h:02d}:{m:02d}"


class _TechState:
    __slots__ = ("tech", "x", "y", "time", "count")

    def __init__(self, tech: FieldTech) -> None:
        self.tech = tech
        self.x = tech.home_x
        self.y = tech.home_y
        self.time = tech.shift_start_min
        self.count = 0


# --------------------------------------------------------------------------------------------
# Engine
# --------------------------------------------------------------------------------------------
def _optimize(data: DispatchData):
    states = {t.id: _TechState(t) for t in data.technicians}
    jobs = sorted(data.jobs, key=lambda j: (-j.priority, j.window_start_min, j.id))
    suggestions: list[RoutingSuggestion] = []
    unassigned: list[UnassignedJob] = []
    total_drive = 0

    for job in jobs:
        cands = eligible_techs(job, data.technicians)
        if not cands:
            unassigned.append(
                UnassignedJob(job.id, job.trade, f"no technician has skill '{job.required_skill}'")
            )
            continue
        best: tuple[int, int, _TechState] | None = None  # (drive, arrival, state)
        for t in cands:
            s = states[t.id]
            d = _drive(_manhattan(s.x, s.y, job.x, job.y))
            arrival = max(s.time + d, job.window_start_min)
            if arrival > job.window_end_min or arrival + job.duration_min > t.shift_end_min:
                continue
            if best is None or d < best[0] or (d == best[0] and t.id < best[2].tech.id):
                best = (d, arrival, s)
        if best is None:
            unassigned.append(
                UnassignedJob(job.id, job.trade, "no technician with capacity in the arrival window")
            )
            continue
        d, arrival, s = best
        s.count += 1
        suggestions.append(
            RoutingSuggestion(
                job_id=job.id,
                customer_name=job.customer_name,
                trade=job.trade,
                required_skill=job.required_skill,
                tech_id=s.tech.id,
                tech_name=s.tech.name,
                sequence=s.count,
                drive_minutes=d,
                arrival_min=arrival,
                confidence=ROUTE_CONFIDENCE,
                reasoning=(
                    f"{s.tech.name}: {d}min drive from previous stop, arrive {_fmt(arrival)} "
                    f"for {job.customer_name} ({job.trade})."
                ),
            )
        )
        total_drive += d
        s.x, s.y, s.time = job.x, job.y, arrival + job.duration_min

    techs_used = sum(1 for s in states.values() if s.count > 0)
    return suggestions, unassigned, total_drive, techs_used


def _baseline_drive(data: DispatchData) -> int:
    """Naive round-robin among skilled techs, jobs in input order, no nearest-stop optimization."""
    skilled: dict[str, list[FieldTech]] = {}
    for t in data.technicians:
        for skill in t.skills:
            skilled.setdefault(skill, []).append(t)
    pos = {t.id: (t.home_x, t.home_y) for t in data.technicians}
    rr: dict[str, int] = {}
    total = 0
    for job in data.jobs:
        techs = skilled.get(job.required_skill)
        if not techs:
            continue
        i = rr.get(job.required_skill, 0) % len(techs)
        rr[job.required_skill] = i + 1
        t = techs[i]
        px, py = pos[t.id]
        total += _drive(_manhattan(px, py, job.x, job.y))
        pos[t.id] = (job.x, job.y)
    return total


def analyze(data: DispatchData) -> RoutingAnalysis:
    suggestions, unassigned, opt_drive, techs_used = _optimize(data)
    base_drive = _baseline_drive(data)
    totals = RoutingTotals(
        jobs=len(data.jobs),
        assigned=len(suggestions),
        unassigned=len(unassigned),
        techs_used=techs_used,
        drive_minutes_optimized=opt_drive,
        drive_minutes_baseline=base_drive,
        drive_minutes_saved=max(0, base_drive - opt_drive),
    )
    return RoutingAnalysis(data.as_of, suggestions, unassigned, totals, _hash_inputs(data))


def _hash_inputs(data: DispatchData) -> str:
    payload = {
        "as_of": data.as_of.isoformat(),
        "jobs": sorted((asdict(j) for j in data.jobs), key=lambda r: r["id"]),
        "techs": sorted((asdict(t) for t in data.technicians), key=lambda r: r["id"]),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
