"""Deterministic partial-consumable cost proration engine (ADR 0003 — pure, no LLM, no randomness).

The pain (Alex discovery, 2026-06-16): consumables (metal vent spools, copper coils) are pulled from
inventory and used PARTIALLY across many jobs over the lot's lifespan, but techs never log the per-job
draw. Today the whole lot's cost is dumped on the single "replenish" job ("law of averages"), so every
OTHER job it served is undercosted and that one job is wildly overcosted.

This engine takes a consumable lot (total quantity, total cost, the pull→depletion window) and the jobs
served in that window, and PRORATES the lot cost across those jobs. Three allocation methods:

  * ``even``           — split equally across the jobs (the transcript's "law of averages", but spread
                          across all jobs instead of dumped on one).
  * ``by_usage_proxy`` — split proportional to a per-job usage proxy (linear feet of vent/copper, or any
                          quantity estimate). The most accurate when techs can give even a rough draw.
  * ``by_job_count``   — alias of ``even`` kept explicit for callers who think in "per job" terms.

Invariants (property-tested):
  * Money is integer CENTS end to end; dollars only at the API boundary (schemas layer).
  * Allocations sum EXACTLY to the lot's total cost — no rounding leak. The remainder cent(s) are
    absorbed by the largest-share job (by proxy) or the last job (even), deterministically.
  * Output is reproducible; a stable ``inputs_hash`` supports idempotency/audit.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import date

# Allocation method identifiers (kept as module constants so callers/tests don't pass magic strings).
METHOD_EVEN = "even"
METHOD_BY_USAGE = "by_usage_proxy"
METHOD_BY_JOB_COUNT = "by_job_count"
_VALID_METHODS = (METHOD_EVEN, METHOD_BY_USAGE, METHOD_BY_JOB_COUNT)


# --------------------------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class ConsumableLot:
    """One physical lot of a partially-consumed consumable (e.g. a 500 ft copper coil, a 50 ft vent
    spool). ``total_cost_cents`` is the lot's purchase cost in integer cents."""

    sku: str
    name: str
    unit: str  # "ft", "lb", "ea" — descriptive only; the engine is unit-agnostic
    total_quantity: float
    total_cost_cents: int
    pull_date: date
    depletion_date: date  # when the lot ran out / was replenished
    # Optional explicit material category ("linear"/"weight"/"discrete"; see proration_catalog). When
    # None the catalog classifies from unit + name/sku keywords. Set it to override the classifier.
    # Appended LAST with a default for backward compatibility; included in the inputs_hash via asdict().
    category: str | None = None


@dataclass(frozen=True)
class ConsumableJobUsage:
    """A job the lot served during its lifespan. ``usage_proxy`` is an OPTIONAL per-job draw estimate
    (linear feet, pounds, count) used by the by-usage method; ``None`` means 'unknown' and the engine
    falls back to an even split for that lot."""

    job_id: str
    usage_proxy: float | None = None
    job_revenue_cents: int | None = None  # optional, for context only — never drives the split


@dataclass(frozen=True)
class LotProrationInput:
    lot: ConsumableLot
    jobs: list[ConsumableJobUsage]
    method: str = "auto"  # "auto" picks by_usage_proxy when every job has a proxy, else even


# --------------------------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class JobAllocation:
    job_id: str
    allocated_cost_cents: int
    usage_proxy: float | None
    share_pct: float  # allocated_cost_cents as a % of the lot, rounded for display
    reasoning: str


@dataclass(frozen=True)
class LotProrationResult:
    sku: str
    name: str
    unit: str
    method: str
    total_cost_cents: int
    total_quantity: float
    job_count: int
    allocations: list[JobAllocation]
    # The value story: today the whole lot lands on ONE job. Proration spreads it. The accuracy delta
    # is the total miscosting that proration corrects = the over-cost removed from the dump job PLUS the
    # cost restored to the jobs that were previously getting it for free. By construction that equals
    # 2 * (lot_cost - dump_job's_fair_share).
    dump_job_id: str
    miscost_corrected_cents: int
    reasoning: str
    inputs_hash: str


@dataclass(frozen=True)
class ConsumableProrationAnalysis:
    as_of: date
    lots: list[LotProrationResult]
    total_prorated_cents: int
    total_miscost_corrected_cents: int
    inputs_hash: str


# --------------------------------------------------------------------------------------------
# Pure primitives
# --------------------------------------------------------------------------------------------
def largest_remainder_allocation(total_cents: int, weights: list[float]) -> list[int]:
    """Apportion ``total_cents`` across len(weights) buckets proportional to ``weights`` so the parts
    sum EXACTLY to ``total_cents`` (largest-remainder / Hamilton method).

    Rules:
      * Non-positive total weight -> fall back to an EVEN split (so a lot with no/zero proxies still
        allocates fully).
      * The leftover cent(s) after flooring go to the buckets with the largest fractional remainders;
        ties break toward the larger weight, then the lower index — fully deterministic.
    """
    n = len(weights)
    if n == 0:
        return []
    total_weight = sum(weights)
    if total_weight <= 0:
        weights = [1.0] * n
        total_weight = float(n)

    exact = [total_cents * w / total_weight for w in weights]
    floors = [int(x) for x in exact]  # truncates toward zero; weights are >= 0 so this is floor
    remainder = total_cents - sum(floors)

    # Order buckets by fractional part desc, then weight desc, then index asc -> deterministic.
    order = sorted(
        range(n),
        key=lambda i: (-(exact[i] - floors[i]), -weights[i], i),
    )
    for k in range(remainder):
        floors[order[k]] += 1
    return floors


def even_allocation(total_cents: int, n: int) -> list[int]:
    """Even split where the LAST bucket absorbs the remainder cent(s) — deterministic and order-stable."""
    if n <= 0:
        return []
    base = total_cents // n
    parts = [base] * n
    parts[-1] += total_cents - base * n
    return parts


def _all_jobs_have_proxy(jobs: list[ConsumableJobUsage]) -> bool:
    return bool(jobs) and all(j.usage_proxy is not None and j.usage_proxy > 0 for j in jobs)


def _resolve_method(inp: LotProrationInput) -> str:
    method = inp.method
    if method == "auto":
        if _all_jobs_have_proxy(inp.jobs):
            return METHOD_BY_USAGE
        return METHOD_EVEN
    if method not in _VALID_METHODS:
        raise ValueError(f"unknown proration method {method!r}; expected one of auto/{_VALID_METHODS}")
    # by_job_count is an even split by definition.
    return METHOD_EVEN if method == METHOD_BY_JOB_COUNT else method


# --------------------------------------------------------------------------------------------
# Engine
# --------------------------------------------------------------------------------------------
def _catalog_basis_note(lot: ConsumableLot) -> str:
    """When auto falls back to an even split because no usage proxy was captured, consult the
    consumable catalog: a DISCRETE material (fittings, filters) is rightly split per job, so there's
    nothing to capture; a LINEAR/WEIGHT material (line set, charge) WOULD be split more fairly by its
    draw — return a note telling the shop what to log next time. Empty string when no note applies."""
    # Local import keeps proration.py free of any dependency on the catalog (catalog imports from here).
    from app.agents.inventory.proration_catalog import (
        CATEGORY_DISCRETE,
        CATEGORY_PROXY_LABEL,
        resolve_category,
    )

    category = resolve_category(lot.name, lot.sku, lot.unit, lot.category)
    if category == CATEGORY_DISCRETE:
        return ""  # per-job IS the right basis for discrete consumables — no data gap to flag.
    label = CATEGORY_PROXY_LABEL.get(category, "per-job usage")
    return (
        f" Recommended basis for this {category} material is by_usage_proxy — "
        f"capture {label} per job to prorate it accurately next time."
    )


def prorate_lot(inp: LotProrationInput) -> LotProrationResult:
    lot = inp.lot
    jobs = list(inp.jobs)
    if not jobs:
        raise ValueError(f"lot {lot.sku} has no jobs to prorate across")
    resolved = _resolve_method(inp)
    # Auto fell back to even ONLY because the lot's jobs lack usage proxies (an explicit even/by_job_count
    # request is the caller's deliberate choice, not a data gap). In that fallback case, consult the
    # consumable catalog so a human knows the basis to capture next time.
    catalog_note = (
        _catalog_basis_note(lot)
        if inp.method == "auto" and resolved == METHOD_EVEN and not _all_jobs_have_proxy(jobs)
        else ""
    )

    if resolved == METHOD_BY_USAGE:
        weights = [float(j.usage_proxy or 0.0) for j in jobs]
        parts = largest_remainder_allocation(lot.total_cost_cents, weights)
    else:  # even
        parts = even_allocation(lot.total_cost_cents, len(jobs))

    allocations: list[JobAllocation] = []
    for job, cents in zip(jobs, parts):
        share = round(cents / lot.total_cost_cents * 100, 2) if lot.total_cost_cents else 0.0
        if resolved == METHOD_BY_USAGE:
            why = (
                f"Job {job.job_id}: {job.usage_proxy:g} {lot.unit} of {lot.name} "
                f"-> ${cents / 100:,.2f} ({share:g}% of the ${lot.total_cost_cents / 100:,.2f} lot)."
            )
        else:
            why = (
                f"Job {job.job_id}: even share of {lot.name} across {len(jobs)} jobs "
                f"-> ${cents / 100:,.2f} ({share:g}% of the ${lot.total_cost_cents / 100:,.2f} lot)."
            )
        allocations.append(
            JobAllocation(
                job_id=job.job_id,
                allocated_cost_cents=cents,
                usage_proxy=job.usage_proxy,
                share_pct=share,
                reasoning=why,
            )
        )

    # Value story. Today the whole lot is dumped on one job (the replenish job = the LAST job in the
    # window). Proration corrects the miscost: that job was over-costed by (lot - its_fair_share), and
    # the rest were collectively under-costed by the same amount. Total absolute miscosting corrected:
    by_id = {al.job_id: al for al in allocations}
    dump_job_id = jobs[-1].job_id  # replenish/last job in the window absorbs the lot today
    dump_fair_share = by_id[dump_job_id].allocated_cost_cents
    miscost = 2 * (lot.total_cost_cents - dump_fair_share)

    reasoning = (
        f"{lot.name} ({lot.sku}): a {lot.total_quantity:g}{lot.unit} lot costing "
        f"${lot.total_cost_cents / 100:,.2f} served {len(jobs)} job(s) from "
        f"{lot.pull_date.isoformat()} to {lot.depletion_date.isoformat()}. Prorated by {resolved}; "
        f"today the full lot is dumped on job {dump_job_id}, overstating its cost by "
        f"${ (lot.total_cost_cents - dump_fair_share) / 100:,.2f} and undercosting the rest by the same. "
        f"Job-costing accuracy improves by ${miscost / 100:,.2f}."
        f"{catalog_note}"
    )

    return LotProrationResult(
        sku=lot.sku,
        name=lot.name,
        unit=lot.unit,
        method=resolved,
        total_cost_cents=lot.total_cost_cents,
        total_quantity=lot.total_quantity,
        job_count=len(jobs),
        allocations=allocations,
        dump_job_id=dump_job_id,
        miscost_corrected_cents=miscost,
        reasoning=reasoning,
        inputs_hash=_hash_lot_input(inp, resolved),
    )


def analyze_consumables(inputs: list[LotProrationInput], *, as_of: date) -> ConsumableProrationAnalysis:
    lots = [prorate_lot(inp) for inp in inputs]
    lots.sort(key=lambda r: r.miscost_corrected_cents, reverse=True)
    total_prorated = sum(r.total_cost_cents for r in lots)
    total_miscost = sum(r.miscost_corrected_cents for r in lots)
    return ConsumableProrationAnalysis(
        as_of=as_of,
        lots=lots,
        total_prorated_cents=total_prorated,
        total_miscost_corrected_cents=total_miscost,
        inputs_hash=_hash_analysis(inputs, as_of),
    )


# --------------------------------------------------------------------------------------------
# Hashing (stable, for idempotency/audit)
# --------------------------------------------------------------------------------------------
def _lot_payload(inp: LotProrationInput, resolved_method: str) -> dict:
    return {
        "method": resolved_method,
        "lot": {**asdict(inp.lot), "pull_date": inp.lot.pull_date.isoformat(),
                "depletion_date": inp.lot.depletion_date.isoformat()},
        "jobs": [asdict(j) for j in inp.jobs],
    }


def _hash_lot_input(inp: LotProrationInput, resolved_method: str) -> str:
    blob = json.dumps(_lot_payload(inp, resolved_method), sort_keys=True, separators=(",", ":"),
                      default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _hash_analysis(inputs: list[LotProrationInput], as_of: date) -> str:
    payload = {
        "as_of": as_of.isoformat(),
        "lots": sorted(
            (_lot_payload(inp, _resolve_method(inp)) for inp in inputs),
            key=lambda p: p["lot"]["sku"],
        ),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
