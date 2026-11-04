"""Deterministic dispatch TRIAGE engine: P1/P2/P3 classification + revenue-ranked, skill-aware
technician recommendation + a 3-day call board. Pure stdlib, no LLM, no randomness (ADR 0003).

This EXTENDS the drive-time engine in ``analytics.py``. The Summit dispatcher runs a human priority
matrix (P1 = emergency / "no heat" first), respects technician **skills**, and is **comp'd on revenue**
(so a skilled, high-revenue, nearby tech wins). Leadership also wants "what do the next 3 days look
like" — a per-day capacity-vs-booked board with the unassigned queue ordered P1->P3.

Every figure here is computed by tested pure functions; the reasoning layer only narrates it.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date, timedelta

from app.agents.routing.analytics import _drive, _manhattan, eligible_techs
from app.agents.routing.models import P1, P2, P3, PRIORITY_LABELS, DispatchData, DispatchJob, FieldTech

# Severity keyword -> priority. Checked first against the explicit `severity` label, then `job_type`.
# Emergency / loss-of-essential-service => P1. Same-day comfort => P2. Maintenance / flexible => P3.
_P1_KEYWORDS = ("emergency", "no_heat", "no heat", "no_cool", "no cool", "no_ac", "gas_leak",
                "gas leak", "sewer_backup", "flood", "burst", "outage")
_P2_KEYWORDS = ("comfort", "same_day", "same day", "leak", "repair", "not_working", "warm", "intermittent")
_P3_KEYWORDS = ("maintenance", "tune_up", "tune up", "inspection", "filter", "estimate", "install",
                "scheduled", "flexible", "thermostat")

# Revenue-rank weighting. The dispatcher is paid on revenue, so the tech ranking blends three normalized
# signals: skill fit, drive-time proximity (closer = better), and the tech's revenue strength. Weights
# sum to 1.0; expressed as integer basis points so the score is exact/hand-computable (no float drift).
_W_SKILL_BP = 3000      # 0.30 — does the tech have the required skill (gate already applied; tie-break depth)
_W_PROXIMITY_BP = 3000  # 0.30 — nearer techs reduce windshield time
_W_REVENUE_BP = 4000    # 0.40 — the dispatcher is comp'd on revenue (the heaviest signal)

_MAX_DRIVE_MIN = 120    # proximity normalizer: a 2h+ drive scores 0 proximity


# --------------------------------------------------------------------------------------------
# Result types
# --------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class TechRank:
    tech_id: str
    tech_name: str
    has_skill: bool
    drive_minutes: int
    avg_ticket_cents: int
    conversion_pct: int
    revenue_score_bp: int   # 0..10000 the tech's revenue strength (avg_ticket x conversion), normalized
    score_bp: int           # 0..10000 overall rank score (higher = better pick)
    reason: str


@dataclass(frozen=True)
class TriagedJob:
    job_id: str
    customer_name: str
    trade: str
    required_skill: str
    job_type: str
    priority: int           # 1=P1, 2=P2, 3=P3
    priority_label: str
    severity_source: str    # "severity" | "job_type" | "default"
    revenue_cents: int
    recommended_tech_id: str | None
    recommended_tech_name: str | None
    candidates: list[TechRank]
    assignable: bool
    reason: str


@dataclass(frozen=True)
class BoardDay:
    day: str                # ISO date
    capacity_min: int       # sum of techs' available shift minutes that day
    booked_min: int         # sum of scheduled job durations on that day
    free_min: int           # capacity - booked (>= 0; 0 when over capacity)
    over_capacity_min: int  # booked - capacity (>= 0; 0 when within capacity)
    utilization_pct: int    # booked / capacity * 100 (0 when no capacity)
    job_count: int
    unavailable_tech_ids: list[str]  # gray blocks: techs with no shift that day


@dataclass(frozen=True)
class TriageTotals:
    jobs: int
    p1: int
    p2: int
    p3: int
    assignable: int
    needs_human: int


@dataclass(frozen=True)
class TriageAnalysis:
    as_of: date
    triaged: list[TriagedJob]       # ordered P1 -> P3 (then revenue desc, then id)
    board: list[BoardDay]           # the 3-day call board
    unassigned_queue: list[str]     # job ids needing a human, ordered P1 -> P3
    totals: TriageTotals
    inputs_hash: str


# --------------------------------------------------------------------------------------------
# Pure primitives
# --------------------------------------------------------------------------------------------
def classify_priority(job: DispatchJob) -> tuple[int, str]:
    """Return (priority, source). Explicit `severity` wins; else derive from `job_type` keywords;
    else default to P3 (flexible/maintenance — never block the board on an unknown)."""
    sev = (job.severity or "").strip().lower()
    if sev:
        if _matches(sev, _P1_KEYWORDS):
            return P1, "severity"
        if _matches(sev, _P2_KEYWORDS):
            return P2, "severity"
        if _matches(sev, _P3_KEYWORDS):
            return P3, "severity"
    jt = (job.job_type or "").strip().lower()
    if _matches(jt, _P1_KEYWORDS):
        return P1, "job_type"
    if _matches(jt, _P2_KEYWORDS):
        return P2, "job_type"
    if _matches(jt, _P3_KEYWORDS):
        return P3, "job_type"
    return P3, "default"


def _matches(text: str, keywords: tuple[str, ...]) -> bool:
    return any(k in text for k in keywords)


def revenue_score_bp(tech: FieldTech) -> int:
    """A tech's revenue strength in basis points (0..10000). Combines average ticket and conversion
    so a tech who books big AND closes often outranks one strong on only one axis. Reference scale:
    avg_ticket $1,000 (100_000c) and 50% conversion each map to ~full strength on their axis."""
    ticket_bp = min(10000, tech.avg_ticket_cents * 10000 // _TICKET_REF_CENTS) if _TICKET_REF_CENTS else 0
    conv_bp = min(10000, max(0, tech.conversion_pct) * 10000 // 100)
    # geometric-ish blend via average of the two normalized axes (exact integer math)
    return (ticket_bp + conv_bp) // 2


_TICKET_REF_CENTS = 100_000  # $1,000 reference average ticket -> full ticket axis


def _proximity_bp(drive_minutes: int) -> int:
    if drive_minutes >= _MAX_DRIVE_MIN:
        return 0
    return (_MAX_DRIVE_MIN - drive_minutes) * 10000 // _MAX_DRIVE_MIN


def rank_techs(job: DispatchJob, techs: list[FieldTech]) -> list[TechRank]:
    """Rank skill-eligible techs for a job by the revenue-weighted blend. Highest score first; ties
    broken by lower drive time, then tech id (deterministic)."""
    cands = eligible_techs(job, techs)
    ranks: list[TechRank] = []
    for t in cands:
        drive = _drive(_manhattan(t.home_x, t.home_y, job.x, job.y))
        rev_bp = revenue_score_bp(t)
        prox_bp = _proximity_bp(drive)
        score = (_W_SKILL_BP * 10000 + _W_PROXIMITY_BP * prox_bp + _W_REVENUE_BP * rev_bp) // 10000
        ranks.append(
            TechRank(
                tech_id=t.id, tech_name=t.name, has_skill=True, drive_minutes=drive,
                avg_ticket_cents=t.avg_ticket_cents, conversion_pct=t.conversion_pct,
                revenue_score_bp=rev_bp, score_bp=score,
                reason=(
                    f"{t.name}: {drive}min drive, ${t.avg_ticket_cents // 100} avg ticket, "
                    f"{t.conversion_pct}% close -> score {score / 100:.0f}/100."
                ),
            )
        )
    ranks.sort(key=lambda r: (-r.score_bp, r.drive_minutes, r.tech_id))
    return ranks


# --------------------------------------------------------------------------------------------
# Engine
# --------------------------------------------------------------------------------------------
def _triage_jobs(data: DispatchData) -> list[TriagedJob]:
    out: list[TriagedJob] = []
    for job in data.jobs:
        priority, source = classify_priority(job)
        ranks = rank_techs(job, data.technicians)
        if ranks:
            top = ranks[0]
            out.append(
                TriagedJob(
                    job_id=job.id, customer_name=job.customer_name, trade=job.trade,
                    required_skill=job.required_skill, job_type=job.job_type, priority=priority,
                    priority_label=PRIORITY_LABELS[priority], severity_source=source,
                    revenue_cents=job.revenue_cents, recommended_tech_id=top.tech_id,
                    recommended_tech_name=top.tech_name, candidates=ranks, assignable=True,
                    reason=(
                        f"{PRIORITY_LABELS[priority]} {job.trade} -> {top.tech_name} "
                        f"(best skill+revenue+proximity match)."
                    ),
                )
            )
        else:
            out.append(
                TriagedJob(
                    job_id=job.id, customer_name=job.customer_name, trade=job.trade,
                    required_skill=job.required_skill, job_type=job.job_type, priority=priority,
                    priority_label=PRIORITY_LABELS[priority], severity_source=source,
                    revenue_cents=job.revenue_cents, recommended_tech_id=None,
                    recommended_tech_name=None, candidates=[], assignable=False,
                    reason=f"no technician has skill '{job.required_skill}' — needs a human.",
                )
            )
    # Order P1 -> P3, then revenue desc (dispatcher is comp'd on revenue), then id (stable).
    out.sort(key=lambda j: (j.priority, -j.revenue_cents, j.job_id))
    return out


def _shift_minutes(tech: FieldTech) -> int:
    return max(0, tech.shift_end_min - tech.shift_start_min)


def _build_board(data: DispatchData, *, days: int = 3) -> list[BoardDay]:
    """Per-day capacity-vs-booked board for the next `days` days starting at as_of.

    Capacity = sum of all techs' shift minutes (every tech is assumed available each day unless a future
    per-day availability feed says otherwise; the live adapter fills `unavailable_tech_ids`). Booked =
    sum of scheduled job durations whose `scheduled_date` falls on that day (blank => the as_of day)."""
    capacity = sum(_shift_minutes(t) for t in data.technicians)
    # techs with a zero-length (or inverted) shift are unavailable -> gray block
    unavailable = sorted(t.id for t in data.technicians if _shift_minutes(t) <= 0)
    board: list[BoardDay] = []
    for offset in range(days):
        day = data.as_of + timedelta(days=offset)
        day_iso = day.isoformat()
        jobs_today = [
            j for j in data.jobs
            if (j.scheduled_date or data.as_of.isoformat()) == day_iso
        ]
        booked = sum(j.duration_min for j in jobs_today)
        free = max(0, capacity - booked)
        over = max(0, booked - capacity)
        util = (booked * 100 // capacity) if capacity else 0
        board.append(
            BoardDay(
                day=day_iso, capacity_min=capacity, booked_min=booked, free_min=free,
                over_capacity_min=over, utilization_pct=util, job_count=len(jobs_today),
                unavailable_tech_ids=list(unavailable),
            )
        )
    return board


def analyze_triage(data: DispatchData, *, board_days: int = 3) -> TriageAnalysis:
    triaged = _triage_jobs(data)
    board = _build_board(data, days=board_days)
    unassigned_queue = [j.job_id for j in triaged if not j.assignable]  # already P1->P3 ordered
    totals = TriageTotals(
        jobs=len(triaged),
        p1=sum(1 for j in triaged if j.priority == P1),
        p2=sum(1 for j in triaged if j.priority == P2),
        p3=sum(1 for j in triaged if j.priority == P3),
        assignable=sum(1 for j in triaged if j.assignable),
        needs_human=sum(1 for j in triaged if not j.assignable),
    )
    return TriageAnalysis(
        as_of=data.as_of, triaged=triaged, board=board, unassigned_queue=unassigned_queue,
        totals=totals, inputs_hash=_hash_inputs(data, board_days),
    )


def _hash_inputs(data: DispatchData, board_days: int) -> str:
    payload = {
        "as_of": data.as_of.isoformat(),
        "board_days": board_days,
        "jobs": sorted((asdict(j) for j in data.jobs), key=lambda r: r["id"]),
        "techs": sorted((asdict(t) for t in data.technicians), key=lambda r: r["id"]),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
