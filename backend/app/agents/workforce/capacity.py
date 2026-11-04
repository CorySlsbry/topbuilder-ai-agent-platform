"""Rolling per-technician, per-job-type duration model — the self-learning capacity layer.

Pure + deterministic (ADR 0003): identical inputs yield identical estimates; the reasoning/LLM layer
narrates these, it never recomputes them.

From each completed job's ACTUAL time on site (clock-in at dispatch -> clock-out at completion), this
maintains a **recency-weighted rolling average of how long technician T takes on job type J** — a
*moving target* that re-adjusts as every new job completes: recent jobs dominate via time-decay, so the
estimate tracks a tech getting faster or slower. When a (tech, job_type) pair has few samples it is
**credibility-blended toward the job-type baseline** so one outlier job can't swing the number.

Those learned durations drive two things ServiceTitan's static routing does NOT:
  * **Proactive overtime limiting** — project a tech's upcoming week from their assigned jobs x their
    real per-type durations, flag overtime BEFORE it is worked, and surface same-trade slack to absorb it.
  * **Efficiency-aware assignment** — the per-(tech, type) estimate says who is genuinely fast at a job
    type, so dispatch can prefer the efficient tech (a learned signal layered on ST's drive-time routing).

Re-run the model as new jobs land and the estimate self-adjusts — that IS the moving target. Money/hours
stay deterministic; no randomness.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from app.agents.workforce.models import Technician

# Defaults (overridable per call).
DEFAULT_HALF_LIFE_DAYS = 60.0   # a job's weight halves every ~2 months -> recent work dominates
DEFAULT_MIN_SAMPLES = 3         # below this, lean on the job-type baseline
DEFAULT_SHRINKAGE_K = 4.0       # credibility constant: tech weight = n / (n + k)
DEFAULT_JOB_HOURS = 2.0         # last-resort duration when neither a learned estimate nor a baseline exists


# --------------------------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class CompletedJob:
    """One finished job's ACTUAL on-site hours (clock-in at dispatch -> clock-out at completion)."""

    technician_id: str
    job_type: str
    trade: str
    actual_hours: float
    completed_date: date


@dataclass(frozen=True)
class AssignedJob:
    """An upcoming/booked job assigned to a technician, by type — for the week projection.

    The booked time estimate is deliberately ignored; we project from the LEARNED per-tech duration.
    """

    technician_id: str
    job_type: str
    trade: str


# --------------------------------------------------------------------------------------------
# Pure primitives (property-tested)
# --------------------------------------------------------------------------------------------
def recency_weight(age_days: float, half_life_days: float) -> float:
    """Time-decay weight in (0, 1]: halves every ``half_life_days``; age 0 -> 1.0."""
    if half_life_days <= 0:
        return 1.0
    return 0.5 ** (max(0.0, age_days) / half_life_days)


def weighted_mean(values: list[float], weights: list[float]) -> float | None:
    """Sum(w*v) / Sum(w); ``None`` when there is no positive weight."""
    total_w = sum(weights)
    if total_w <= 0:
        return None
    return sum(v * w for v, w in zip(values, weights)) / total_w


def credibility_blend(tech_estimate: float, baseline: float, n: int, k: float) -> float:
    """Shrink the tech estimate toward the baseline by sample size: weight = n / (n + k).

    One job barely moves the estimate off the baseline; a long history of a tech's own jobs dominates.
    """
    if n <= 0:
        return baseline
    w = n / (n + k)
    return w * tech_estimate + (1.0 - w) * baseline


def sample_confidence(n: int, min_samples: int) -> float:
    """0..1 confidence from sample volume: ~0.5 at ``min_samples``, ~0.875 at 3x, asymptotes to 1."""
    if n <= 0 or min_samples <= 0:
        return 0.0
    return round(1.0 - 0.5 ** (n / min_samples), 4)


def overtime_hours(projected_hours: float, contracted_hours: float) -> float:
    return max(0.0, projected_hours - contracted_hours)


# --------------------------------------------------------------------------------------------
# Result types
# --------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class TechJobTypeDuration:
    technician_id: str
    job_type: str
    trade: str
    estimate_hours: float          # credibility-blended rolling estimate (the moving target we schedule on)
    rolling_hours: float           # the tech's own recency-weighted estimate (pre-blend)
    baseline_hours: float          # job-type baseline across all techs
    sample_size: int
    confidence: float              # 0..1 from sample size
    efficiency_delta_hours: float  # estimate - baseline; NEGATIVE => faster than baseline (efficient)


@dataclass(frozen=True)
class TechWeekProjection:
    technician_id: str
    trade: str
    job_count: int
    projected_hours: float
    contracted_hours: float
    overtime_hours: float
    confidence: float              # mean confidence of the durations used
    redistribute_to: list[str]     # same-trade techs with slack who can absorb the overflow
    reasoning: str


# --------------------------------------------------------------------------------------------
# Engine
# --------------------------------------------------------------------------------------------
def estimate_tech_durations(
    completed_jobs: list[CompletedJob],
    baselines: dict[str, float] | None = None,
    *,
    as_of: date,
    half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
    min_samples: int = DEFAULT_MIN_SAMPLES,
    shrinkage_k: float = DEFAULT_SHRINKAGE_K,
) -> dict[tuple[str, str], TechJobTypeDuration]:
    """The rolling per-(technician, job_type) duration estimates as of ``as_of``.

    ``baselines`` is an optional job_type -> hours prior (e.g. from ``JobDurationStat.mean_hours``); any
    job_type missing from it falls back to the all-technician recency-weighted mean computed here.
    """
    provided = dict(baselines or {})

    # All-tech recency-weighted baseline per job_type (the fallback prior + the comparison line).
    by_type: dict[str, list[tuple[float, float]]] = defaultdict(list)  # job_type -> [(actual, weight)]
    by_tech_type: dict[tuple[str, str], list[CompletedJob]] = defaultdict(list)
    for j in completed_jobs:
        w = recency_weight((as_of - j.completed_date).days, half_life_days)
        by_type[j.job_type].append((j.actual_hours, w))
        by_tech_type[(j.technician_id, j.job_type)].append(j)

    def baseline_for(job_type: str) -> float | None:
        if job_type in provided:
            return provided[job_type]
        pairs = by_type.get(job_type, [])
        return weighted_mean([v for v, _ in pairs], [w for _, w in pairs])

    out: dict[tuple[str, str], TechJobTypeDuration] = {}
    for (tech_id, job_type), jobs in by_tech_type.items():
        baseline = baseline_for(job_type)
        if baseline is None:
            continue  # no signal at all for this type
        weights = [recency_weight((as_of - j.completed_date).days, half_life_days) for j in jobs]
        rolling = weighted_mean([j.actual_hours for j in jobs], weights)
        if rolling is None:
            continue
        n = len(jobs)
        estimate = credibility_blend(rolling, baseline, n, shrinkage_k)
        out[(tech_id, job_type)] = TechJobTypeDuration(
            technician_id=tech_id,
            job_type=job_type,
            trade=jobs[0].trade,
            estimate_hours=round(estimate, 3),
            rolling_hours=round(rolling, 3),
            baseline_hours=round(baseline, 3),
            sample_size=n,
            confidence=sample_confidence(n, min_samples),
            efficiency_delta_hours=round(estimate - baseline, 3),
        )
    return out


def _duration_for(
    tech_id: str,
    job_type: str,
    durations: dict[tuple[str, str], TechJobTypeDuration],
    baselines: dict[str, float],
) -> tuple[float, float | None]:
    """(hours, confidence) for a tech's job-type: learned estimate, else baseline, else default."""
    d = durations.get((tech_id, job_type))
    if d is not None:
        return d.estimate_hours, d.confidence
    if job_type in baselines:
        return baselines[job_type], 0.0
    return DEFAULT_JOB_HOURS, 0.0


def project_tech_overtime(
    technicians: list[Technician],
    assigned_jobs: list[AssignedJob],
    durations: dict[tuple[str, str], TechJobTypeDuration],
    baselines: dict[str, float] | None = None,
    *,
    slack_fraction: float = 0.95,
) -> list[TechWeekProjection]:
    """Project each tech's week from their assigned jobs x learned durations; flag + route overtime.

    A tech is "has slack" when their own projection is below ``slack_fraction`` of contracted hours;
    those same-trade techs are offered as redistribution targets for an over-loaded colleague.
    """
    base = dict(baselines or {})
    jobs_by_tech: dict[str, list[AssignedJob]] = defaultdict(list)
    for a in assigned_jobs:
        jobs_by_tech[a.technician_id].append(a)

    # First pass: every tech's projected hours (needed to know who has slack).
    projected: dict[str, float] = {}
    confidences: dict[str, list[float]] = defaultdict(list)
    for tech in technicians:
        total = 0.0
        for a in jobs_by_tech.get(tech.id, []):
            hrs, conf = _duration_for(tech.id, a.job_type, durations, base)
            total += hrs
            if conf is not None:
                confidences[tech.id].append(conf)
        projected[tech.id] = total

    by_trade: dict[str, list[Technician]] = defaultdict(list)
    for tech in technicians:
        by_trade[tech.trade].append(tech)

    out: list[TechWeekProjection] = []
    for tech in technicians:
        jobs = jobs_by_tech.get(tech.id, [])
        proj = round(projected[tech.id], 2)
        ot = round(overtime_hours(proj, tech.contracted_weekly_hours), 2)
        confs = confidences.get(tech.id, [])
        conf = round(sum(confs) / len(confs), 3) if confs else 0.0

        redistribute: list[str] = []
        if ot > 1e-6:
            redistribute = [
                other.id
                for other in by_trade[tech.trade]
                if other.id != tech.id
                and projected[other.id] < other.contracted_weekly_hours * slack_fraction
            ]

        if ot > 1e-6:
            reasoning = (
                f"{tech.name} ({tech.trade}): {len(jobs)} assigned job(s) project to {proj:.1f}h vs "
                f"{tech.contracted_weekly_hours:.0f}h contracted -> {ot:.1f}h overtime, on learned "
                f"per-job durations (confidence {conf:.0%})."
            )
            reasoning += (
                f" Same-trade slack to absorb it: {', '.join(redistribute)}."
                if redistribute
                else " No same-trade slack; defer lower-priority work or add capacity."
            )
        else:
            reasoning = (
                f"{tech.name} ({tech.trade}): {len(jobs)} job(s) project to {proj:.1f}h, within the "
                f"{tech.contracted_weekly_hours:.0f}h contracted week (no projected overtime)."
            )

        out.append(
            TechWeekProjection(
                technician_id=tech.id,
                trade=tech.trade,
                job_count=len(jobs),
                projected_hours=proj,
                contracted_hours=tech.contracted_weekly_hours,
                overtime_hours=ot,
                confidence=conf,
                redistribute_to=redistribute,
                reasoning=reasoning,
            )
        )

    out.sort(key=lambda p: p.overtime_hours, reverse=True)
    return out
