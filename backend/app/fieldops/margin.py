"""Deterministic quoting-MARGIN engine for the field tech's equipment-driven quote builder.

Pure, dependency-free (stdlib only), no LLM, no randomness: identical inputs always yield identical
figures (ADR 0003). The agent's reasoning node narrates these; it never recomputes them. Money is
carried as integer **cents** end-to-end so the same number lands on the phone, the persisted estimate,
and (when pushed) ServiceTitan — no float drift.

Models how the client (Summit Heat Pumps) actually quotes, captured in the Alex discovery call
(2026-06-16, see ``docs/ALEX_BUILD_SPEC.md`` workstream "Quote builder"):

  * Quotes are **EQUIPMENT-driven**: each equipment item carries a COST, the SOLD HOURS of labor it
    pulls, and a TARGET gross margin. The quote price = the equipment price + the labor it sells +
    any materials.
  * **Average-sqft pricing** is the cross-check: a heat-pump / install job has a rough $/sqft the shop
    expects; if the equipment-built quote falls below that benchmark the quote is probably underpriced.
  * **True gross margin = (price - cost) / price** — NEVER markup-on-cost. Mixing the two is the
    classic estimating error (a "50% markup" is only 33% margin), so the engine computes margin one way.
  * **The leak Alex named — "sell the company, not the box":** a premium BRAND bought in at a high cost
    but quoted at NO extra margin is pure leakage (you paid more for the box and gave the upside away).
    The engine flags any high-cost line whose margin is at/under target as ``brand_low_margin``.
  * **Excess material:** consumables (metal spools, copper) get over-pulled and dumped on one job; the
    engine flags a line whose material cost runs above an expected ceiling for the job size.

The output is everything the builder needs to *see the margin before it sends the quote*: the grand
total, the **blended** gross margin %, a per-line margin, and the red flags — plus a stable
``inputs_hash`` for audit/idempotency.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import Enum

# --------------------------------------------------------------------------------------------
# Defaults (overridable per call). Percentages are whole numbers (e.g. 45.0 == 45%).
# --------------------------------------------------------------------------------------------
DEFAULT_TARGET_MARGIN_PCT = 45.0
# A line whose cost is at/above this is treated as a "premium box" for the brand-leak check.
HIGH_COST_LINE_CENTS = 300_000  # $3,000 — a premium condenser/air-handler tier
# Excess-material guard: a material line costing more than this multiple of the job's
# expected material budget (sold-hours-driven) is flagged for review.
EXCESS_MATERIAL_MULTIPLE = 1.5
# Expected material spend per sold labor-hour (the "law of averages" budget the shop assumes).
MATERIAL_BUDGET_PER_HOUR_CENTS = 4_500  # $45/sold-hour of consumables
# Average-sqft benchmark tolerance: a quote more than this fraction UNDER the sqft benchmark
# is flagged as below the shop's average pricing.
SQFT_UNDERPRICE_TOLERANCE = 0.10


class LineKind(str, Enum):
    EQUIPMENT = "equipment"
    LABOR = "labor"
    MATERIAL = "material"


class FlagCode(str, Enum):
    LOW_MARGIN_LINE = "low_margin_line"
    BRAND_LOW_MARGIN = "brand_low_margin"
    EXCESS_MATERIAL = "excess_material"
    BELOW_SQFT_BENCHMARK = "below_sqft_benchmark"
    BLENDED_BELOW_TARGET = "blended_below_target"


# --------------------------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class QuoteLine:
    """One line on the equipment-driven quote.

    ``price_cents`` is what the customer is charged for this line; ``cost_cents`` is the shop's cost.
    Equipment lines carry ``sold_hours`` (the labor the box pulls) and an optional per-line
    ``target_margin_pct`` (falls back to the quote target). ``brand`` is free text used only for the
    "sell the company, not the box" surfacing.
    """

    kind: LineKind
    name: str
    price_cents: int
    cost_cents: int
    qty: int = 1
    sold_hours: float = 0.0
    target_margin_pct: float | None = None
    brand: str = ""
    code: str = ""


@dataclass(frozen=True)
class MarginQuoteInput:
    lines: list[QuoteLine]
    target_margin_pct: float = DEFAULT_TARGET_MARGIN_PCT
    sqft: int | None = None
    avg_price_per_sqft_cents: int | None = None


# --------------------------------------------------------------------------------------------
# Pure primitives (property-tested)
# --------------------------------------------------------------------------------------------
def gross_margin_pct(price_cents: int, cost_cents: int) -> float:
    """True gross margin: (price - cost) / price, as a whole-number percent.

    Markup-on-cost is intentionally NOT used. A $0 price yields 0.0 (no margin to speak of); a
    negative-margin (cost > price) line returns a negative percent so the loss is visible.
    """
    if price_cents <= 0:
        return 0.0
    return round((price_cents - cost_cents) / price_cents * 100, 2)


def price_for_margin(cost_cents: int, target_margin_pct: float) -> int:
    """The price (cents) that hits a target gross margin for a given cost: cost / (1 - margin).

    The inverse of :func:`gross_margin_pct`; the builder uses it to show "price to target". A target
    at/above 100% is clamped just under 100% (an infinite price is meaningless to a quote).
    """
    m = min(max(target_margin_pct, 0.0), 99.99) / 100.0
    return round(cost_cents / (1 - m))


# --------------------------------------------------------------------------------------------
# Outputs
# --------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class PricedMarginLine:
    kind: str
    name: str
    brand: str
    code: str
    qty: int
    sold_hours: float
    unit_price_cents: int
    unit_cost_cents: int
    line_price_cents: int
    line_cost_cents: int
    margin_pct: float
    target_margin_pct: float
    below_target: bool
    flags: list[str]


@dataclass(frozen=True)
class MarginFlag:
    code: str
    line_name: str
    message: str


@dataclass(frozen=True)
class MarginQuoteResult:
    lines: list[PricedMarginLine]
    total_price_cents: int
    total_cost_cents: int
    gross_profit_cents: int
    blended_margin_pct: float
    target_margin_pct: float
    total_sold_hours: float
    sqft: int | None
    sqft_price_per_unit_cents: int | None
    benchmark_price_cents: int | None
    flags: list[MarginFlag]
    inputs_hash: str

    @property
    def has_blocking_flag(self) -> bool:
        return any(f.code != FlagCode.BELOW_SQFT_BENCHMARK.value for f in self.flags)


# --------------------------------------------------------------------------------------------
# The engine
# --------------------------------------------------------------------------------------------
def _hash_inputs(data: MarginQuoteInput) -> str:
    payload = {
        "target_margin_pct": data.target_margin_pct,
        "sqft": data.sqft,
        "avg_price_per_sqft_cents": data.avg_price_per_sqft_cents,
        "lines": [
            {k: (v.value if isinstance(v, Enum) else v) for k, v in asdict(line).items()}
            for line in data.lines
        ],
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def compute_margin_quote(data: MarginQuoteInput) -> MarginQuoteResult:
    """Price an equipment-driven quote and surface the margin + the leak flags.

    Deterministic and exact in integer cents. Per-line margin uses true gross margin; the blended
    margin is gross profit over total price (not an average of per-line margins). Flags are ordered
    by line, then quote-level (blended-below-target, sqft) appended last.
    """
    target = data.target_margin_pct
    priced: list[PricedMarginLine] = []
    flags: list[MarginFlag] = []
    total_price = 0
    total_cost = 0
    total_hours = 0.0
    material_cost_total = 0

    for line in data.lines:
        qty = max(line.qty, 1)
        line_price = line.price_cents * qty
        line_cost = line.cost_cents * qty
        line_target = line.target_margin_pct if line.target_margin_pct is not None else target
        margin = gross_margin_pct(line_price, line_cost)
        below = margin < line_target
        line_flags: list[str] = []

        if below:
            line_flags.append(FlagCode.LOW_MARGIN_LINE.value)
            flags.append(
                MarginFlag(
                    code=FlagCode.LOW_MARGIN_LINE.value,
                    line_name=line.name,
                    message=(
                        f"{line.name}: {margin:.1f}% margin is below the {line_target:.0f}% target "
                        f"(price to target ${price_for_margin(line_cost, line_target) / 100:,.0f})."
                    ),
                )
            )
        # "Sell the company, not the box": a premium high-cost line at/under target margin is leaking
        # the upside you paid for. Only fire when it isn't already a plain low-margin flag is noisy —
        # surface it as the distinct, higher-signal reason on a premium box.
        if line.kind == LineKind.EQUIPMENT and line_cost >= HIGH_COST_LINE_CENTS and margin <= line_target:
            line_flags.append(FlagCode.BRAND_LOW_MARGIN.value)
            brand = f" {line.brand}" if line.brand else ""
            flags.append(
                MarginFlag(
                    code=FlagCode.BRAND_LOW_MARGIN.value,
                    line_name=line.name,
                    message=(
                        f"Premium{brand} unit at ${line_cost / 100:,.0f} cost is quoted at only "
                        f"{margin:.1f}% margin — sell the company, not the box."
                    ),
                )
            )

        priced.append(
            PricedMarginLine(
                kind=line.kind.value, name=line.name, brand=line.brand, code=line.code,
                qty=qty, sold_hours=line.sold_hours,
                unit_price_cents=line.price_cents, unit_cost_cents=line.cost_cents,
                line_price_cents=line_price, line_cost_cents=line_cost,
                margin_pct=margin, target_margin_pct=line_target, below_target=below,
                flags=line_flags,
            )
        )
        total_price += line_price
        total_cost += line_cost
        total_hours += line.sold_hours * qty
        if line.kind == LineKind.MATERIAL:
            material_cost_total += line_cost

    # Excess-material check: total material cost vs the sold-hours-driven budget.
    material_budget = round(total_hours * MATERIAL_BUDGET_PER_HOUR_CENTS)
    if material_budget > 0 and material_cost_total > round(material_budget * EXCESS_MATERIAL_MULTIPLE):
        flags.append(
            MarginFlag(
                code=FlagCode.EXCESS_MATERIAL.value,
                line_name="Materials",
                message=(
                    f"Material cost ${material_cost_total / 100:,.0f} runs above the expected "
                    f"${material_budget / 100:,.0f} for {total_hours:.1f} sold hours — confirm what "
                    f"this job actually consumed (don't dump a whole spool here)."
                ),
            )
        )

    gross_profit = total_price - total_cost
    blended = gross_margin_pct(total_price, total_cost)
    if total_price > 0 and blended < target:
        flags.append(
            MarginFlag(
                code=FlagCode.BLENDED_BELOW_TARGET.value,
                line_name="Quote",
                message=(
                    f"Blended margin {blended:.1f}% is below the {target:.0f}% target — "
                    f"${(price_for_margin(total_cost, target) - total_price) / 100:,.0f} short of target price."
                ),
            )
        )

    # Average-sqft cross-check.
    sqft_unit: int | None = None
    benchmark: int | None = None
    if data.sqft and data.sqft > 0:
        sqft_unit = round(total_price / data.sqft)
        if data.avg_price_per_sqft_cents and data.avg_price_per_sqft_cents > 0:
            benchmark = data.avg_price_per_sqft_cents * data.sqft
            if total_price < round(benchmark * (1 - SQFT_UNDERPRICE_TOLERANCE)):
                flags.append(
                    MarginFlag(
                        code=FlagCode.BELOW_SQFT_BENCHMARK.value,
                        line_name="Quote",
                        message=(
                            f"${total_price / 100:,.0f} is under the ${benchmark / 100:,.0f} "
                            f"average-sqft benchmark ({data.sqft:,} sqft x "
                            f"${data.avg_price_per_sqft_cents / 100:.2f}/sqft) — likely underpriced."
                        ),
                    )
                )

    return MarginQuoteResult(
        lines=priced,
        total_price_cents=total_price,
        total_cost_cents=total_cost,
        gross_profit_cents=gross_profit,
        blended_margin_pct=blended,
        target_margin_pct=target,
        total_sold_hours=total_hours,
        sqft=data.sqft,
        sqft_price_per_unit_cents=sqft_unit,
        benchmark_price_cents=benchmark,
        flags=flags,
        inputs_hash=_hash_inputs(data),
    )
