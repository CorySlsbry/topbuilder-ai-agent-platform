"""Deterministic Inventory & Supply Chain engine.

No LLM, no randomness — reproducible figures (ADR 0003). Flags reorders, truck-stock shrinkage,
unbilled materials, and vendor-arbitrage savings.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date

from app.agents.inventory.models import InventoryData

REORDER_CYCLES = 2
SHRINKAGE_MIN_VALUE_CENTS = 5_000  # $50 — ignore trivial variances
USAGE_SATURATION_DAYS = 90


# --------------------------------------------------------------------------------------------
# Result types
# --------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class ReorderRecommendation:
    sku: str
    name: str
    on_hand: float
    avg_daily_usage: float
    lead_time_days: float
    dynamic_reorder_point: float
    days_to_stockout: float | None
    recommended_order_qty: int
    stockout_exposure_cents: int
    margin_class: str
    confidence: float
    reasoning: str


@dataclass(frozen=True)
class ShrinkageAlert:
    technician_id: str
    sku: str
    name: str
    expected_qty: float
    counted_qty: float
    variance: float
    shrinkage_value_cents: int
    confidence: float
    reasoning: str


@dataclass(frozen=True)
class UnbilledMaterial:
    job_id: str
    sku: str
    name: str
    qty_used: float
    unbilled_value_cents: int
    reasoning: str


@dataclass(frozen=True)
class ArbitrageOpportunity:
    sku: str
    name: str
    current_unit_cost: float
    best_vendor: str
    best_unit_price: float
    annual_savings_cents: int
    reasoning: str


@dataclass(frozen=True)
class InventoryAnalysis:
    as_of: date
    critical_reorders: list[ReorderRecommendation]
    shrinkage_alerts: list[ShrinkageAlert]
    unbilled_materials: list[UnbilledMaterial]
    arbitrage: list[ArbitrageOpportunity]
    inputs_hash: str


# --------------------------------------------------------------------------------------------
# Pure primitives
# --------------------------------------------------------------------------------------------
def demand_during_lead(avg_daily_usage: float, lead_time_days: float) -> float:
    return avg_daily_usage * lead_time_days


def dynamic_reorder_point(avg_daily_usage: float, lead_time_days: float, safety_stock: float) -> float:
    return avg_daily_usage * lead_time_days + safety_stock


def days_to_stockout(on_hand: float, avg_daily_usage: float) -> float:
    return on_hand / avg_daily_usage if avg_daily_usage > 0 else float("inf")


def shrinkage_value_cents(variance: float, unit_cost: float) -> int:
    return round(variance * unit_cost * 100)


def unbilled_value_cents(qty_used: float, billable_price: float) -> int:
    return round(qty_used * billable_price * 100)


def stockout_exposure_cents(units_short: float, billable_price: float) -> int:
    return round(units_short * billable_price * 100)


def arbitrage_annual_savings_cents(current_cost: float, quote_price: float, daily_usage: float) -> int:
    return max(0, round((current_cost - quote_price) * daily_usage * 365 * 100))


def _reorder_confidence(usage_sample_days: int) -> float:
    return round(0.4 + 0.6 * min(1.0, usage_sample_days / USAGE_SATURATION_DAYS), 3)


# --------------------------------------------------------------------------------------------
# Engine
# --------------------------------------------------------------------------------------------
def analyze(data: InventoryData) -> InventoryAnalysis:
    parts = {p.sku: p for p in data.parts}
    usage_by_sku = {r.sku: r.avg_daily_usage for r in data.reorder_state}

    reorders: list[ReorderRecommendation] = []
    for r in data.reorder_state:
        rop = dynamic_reorder_point(r.avg_daily_usage, r.lead_time_days, r.safety_stock)
        if r.on_hand > rop:
            continue
        part = parts.get(r.sku)
        billable = part.billable_price if part else 0.0
        name = part.name if part else r.sku
        ddl = demand_during_lead(r.avg_daily_usage, r.lead_time_days)
        dts = days_to_stockout(r.on_hand, r.avg_daily_usage)
        units_short = max(0.0, ddl - r.on_hand)
        exposure = stockout_exposure_cents(units_short, billable)
        rec_qty = max(0, math.ceil(REORDER_CYCLES * ddl + r.safety_stock - r.on_hand))
        reorders.append(
            ReorderRecommendation(
                sku=r.sku,
                name=name,
                on_hand=r.on_hand,
                avg_daily_usage=r.avg_daily_usage,
                lead_time_days=r.lead_time_days,
                dynamic_reorder_point=round(rop, 2),
                days_to_stockout=(round(dts, 2) if math.isfinite(dts) else None),
                recommended_order_qty=rec_qty,
                stockout_exposure_cents=exposure,
                margin_class=part.margin_class if part else "standard",
                confidence=_reorder_confidence(r.usage_sample_days),
                reasoning=(
                    f"{name} ({r.sku}): {r.on_hand:g} on hand vs reorder point {rop:.1f} "
                    f"({r.avg_daily_usage:g}/day x {r.lead_time_days:g}d lead + {r.safety_stock:g} safety); "
                    f"~{dts:.1f} days to stockout. Order {rec_qty}. "
                    f"Stockout exposure ~${exposure / 100:,.0f}."
                ),
            )
        )

    shrinkage: list[ShrinkageAlert] = []
    for tc in data.truck_stock:
        variance = tc.expected_qty - tc.counted_qty
        if variance <= 0:
            continue
        part = parts.get(tc.sku)
        value = shrinkage_value_cents(variance, part.unit_cost if part else 0.0)
        if value < SHRINKAGE_MIN_VALUE_CENTS:
            continue
        shrinkage.append(
            ShrinkageAlert(
                technician_id=tc.technician_id,
                sku=tc.sku,
                name=part.name if part else tc.sku,
                expected_qty=tc.expected_qty,
                counted_qty=tc.counted_qty,
                variance=variance,
                shrinkage_value_cents=value,
                confidence=0.9,
                reasoning=(
                    f"Truck {tc.technician_id}: {tc.sku} expected {tc.expected_qty:g}, counted "
                    f"{tc.counted_qty:g} (short {variance:g}) -> ${value / 100:,.0f} variance "
                    "(shrinkage or unbilled usage)."
                ),
            )
        )

    unbilled: list[UnbilledMaterial] = []
    for mu in data.material_usage:
        if mu.billed:
            continue
        part = parts.get(mu.sku)
        value = unbilled_value_cents(mu.qty_used, part.billable_price if part else 0.0)
        unbilled.append(
            UnbilledMaterial(
                job_id=mu.job_id,
                sku=mu.sku,
                name=part.name if part else mu.sku,
                qty_used=mu.qty_used,
                unbilled_value_cents=value,
                reasoning=(
                    f"Job {mu.job_id}: {mu.qty_used:g} x {mu.sku} used but unbilled -> "
                    f"${value / 100:,.0f} revenue at risk."
                ),
            )
        )

    quotes_by_sku: dict[str, list] = defaultdict(list)
    for q in data.vendor_quotes:
        quotes_by_sku[q.sku].append(q)
    arbitrage: list[ArbitrageOpportunity] = []
    for sku, part in parts.items():
        quotes = quotes_by_sku.get(sku)
        if not quotes:
            continue
        best = min(quotes, key=lambda q: q.unit_price)
        if best.unit_price >= part.unit_cost:
            continue
        annual = arbitrage_annual_savings_cents(part.unit_cost, best.unit_price, usage_by_sku.get(sku, 0.0))
        arbitrage.append(
            ArbitrageOpportunity(
                sku=sku,
                name=part.name,
                current_unit_cost=part.unit_cost,
                best_vendor=best.vendor,
                best_unit_price=best.unit_price,
                annual_savings_cents=annual,
                reasoning=(
                    f"{part.name} ({sku}): current ${part.unit_cost:,.2f}/unit vs {best.vendor} "
                    f"${best.unit_price:,.2f} -> ~${annual / 100:,.0f}/yr at current usage."
                ),
            )
        )

    reorders.sort(key=lambda r: r.stockout_exposure_cents, reverse=True)
    shrinkage.sort(key=lambda s: s.shrinkage_value_cents, reverse=True)
    unbilled.sort(key=lambda u: u.unbilled_value_cents, reverse=True)
    arbitrage.sort(key=lambda o: o.annual_savings_cents, reverse=True)

    return InventoryAnalysis(
        as_of=data.as_of,
        critical_reorders=reorders,
        shrinkage_alerts=shrinkage,
        unbilled_materials=unbilled,
        arbitrage=arbitrage,
        inputs_hash=_hash_inputs(data),
    )


def _hash_inputs(data: InventoryData) -> str:
    payload = {
        "as_of": data.as_of.isoformat(),
        "parts": sorted((asdict(p) for p in data.parts), key=lambda r: r["sku"]),
        "reorder_state": sorted((asdict(r) for r in data.reorder_state), key=lambda r: r["sku"]),
        "truck_stock": sorted(
            (asdict(t) for t in data.truck_stock), key=lambda r: (r["technician_id"], r["sku"])
        ),
        "material_usage": sorted(
            (asdict(m) for m in data.material_usage), key=lambda r: (r["job_id"], r["sku"])
        ),
        "vendor_quotes": sorted(
            (asdict(q) for q in data.vendor_quotes), key=lambda r: (r["sku"], r["vendor"])
        ),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
