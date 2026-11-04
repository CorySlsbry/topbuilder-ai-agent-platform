"""Deterministic Pricebook re-pricing engine (ADR 0003). No LLM, no randomness, integer cents.

Ingests the contractor's ServiceTitan Pricebook (each item = sold hours + a bill of materials) plus a
vendor price update (new unit costs for some SKUs), and recomputes every affected item's price under
Alex's sold-hour model:

    price = sold_hours * sold_hour_rate + materials_cost + (materials_cost * material_markup)
    materials_cost = sum over the item's material lines of (qty * vendor_unit_cost)

For each item it emits a ``PricebookItemChange``: the OLD (current-cost) materials_cost + price, the NEW
(post-update) materials_cost + price, the deltas, the margin impact, and which SKUs on that item changed.
Items whose price moves beyond the tolerance are flagged for human review. The reasoning node narrates
these; it never decides them.

Margin definition (CPA-sane): an item's margin = price - true_cost, where true_cost = labor + materials
priced AT COST. Under this model that equals materials_cost * markup_pct (the labor is sold at its rate
with no separate cost line), so a vendor cost increase that flows through the markup actually RAISES the
absolute margin dollars while the markup percent is unchanged — exactly what the sold-hour model intends.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.agents.pricebook.models import (
    MaterialLine,
    PricebookData,
    PricebookItem,
    VendorPriceUpdate,
)


# --------------------------------------------------------------------------------------------
# Pure pricing primitives
# --------------------------------------------------------------------------------------------
def _round_cents(value: Decimal) -> int:
    """Round a Decimal cents value to a whole cent, half-up (deterministic, no float drift)."""
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def materials_cost_cents(lines: list[MaterialLine]) -> int:
    """Sum (qty * unit_cost_cents) over an item's material lines, rounded to whole cents."""
    total = Decimal(0)
    for line in lines:
        total += Decimal(str(line.qty)) * Decimal(line.unit_cost_cents)
    return _round_cents(total)


def price_cents(
    sold_hours: float, sold_hour_rate_cents: int, materials_cost_cents: int, markup_pct: float
) -> int:
    """Alex's sold-hour price: labor + materials + (materials * markup). Integer cents, half-up."""
    labor = Decimal(str(sold_hours)) * Decimal(sold_hour_rate_cents)
    markup = Decimal(materials_cost_cents) * (Decimal(str(markup_pct)) / Decimal(100))
    return _round_cents(labor + Decimal(materials_cost_cents) + markup)


def labor_cost_cents(sold_hours: float, sold_hour_rate_cents: int) -> int:
    return _round_cents(Decimal(str(sold_hours)) * Decimal(sold_hour_rate_cents))


# --------------------------------------------------------------------------------------------
# Result types
# --------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class MaterialLineChange:
    sku: str
    qty: float
    old_unit_cost_cents: int
    new_unit_cost_cents: int
    old_line_cost_cents: int
    new_line_cost_cents: int
    vendor: str | None  # the vendor that published the new cost (None when unchanged)


@dataclass(frozen=True)
class PricebookItemChange:
    code: str
    name: str
    category: str
    sold_hours: float
    sold_hour_rate_cents: int
    markup_pct: float
    labor_cost_cents: int
    old_materials_cost_cents: int
    new_materials_cost_cents: int
    materials_delta_cents: int
    old_price_cents: int  # baseline recomputed from the model at CURRENT costs
    new_price_cents: int  # price after the vendor update
    price_delta_cents: int
    price_delta_pct: float  # delta / old_price * 100 (0 when old_price is 0)
    old_margin_cents: int  # old_price - (labor + old_materials)
    new_margin_cents: int
    margin_delta_cents: int
    changed_skus: list[str]  # SKUs on this item the vendor update touched
    beyond_tolerance: bool
    lines: list[MaterialLineChange]


@dataclass(frozen=True)
class PricebookTotals:
    items: int
    items_affected: int  # items with a non-zero price delta
    items_flagged: int  # items beyond the price-change tolerance
    total_price_delta_cents: int  # sum of price deltas across all items (net repricing impact)
    distinct_skus: int  # distinct SKUs across the whole pricebook
    skus_updated: int  # distinct SKUs the vendor update actually covers (and that appear in the book)
    vendor_coverage_pct: float  # skus_updated / distinct_skus * 100 (0 when no SKUs)
    avg_markup_pct: float  # average markup across items (0 when no items)


@dataclass(frozen=True)
class PricebookAnalysis:
    as_of: date
    changes: list[PricebookItemChange]
    totals: PricebookTotals
    tolerance_pct: float
    inputs_hash: str


# --------------------------------------------------------------------------------------------
# Engine
# --------------------------------------------------------------------------------------------
def _round_pct(n: int, d: int) -> float:
    return round((n / d) * 100, 2) if d else 0.0


def _reprice_item(
    item: PricebookItem,
    updates_by_sku: dict[str, VendorPriceUpdate],
    tolerance_pct: float,
) -> PricebookItemChange:
    labor = labor_cost_cents(item.sold_hours, item.sold_hour_rate_cents)

    old_lines: list[MaterialLine] = list(item.material_lines)
    new_lines: list[MaterialLine] = []
    line_changes: list[MaterialLineChange] = []
    changed_skus: list[str] = []
    for line in old_lines:
        update = updates_by_sku.get(line.sku)
        new_unit_cost = update.new_unit_cost_cents if update else line.unit_cost_cents
        new_line = MaterialLine(
            sku=line.sku, qty=line.qty, unit_cost_cents=new_unit_cost, description=line.description
        )
        new_lines.append(new_line)
        old_line_cost = materials_cost_cents([line])
        new_line_cost = materials_cost_cents([new_line])
        if update is not None and new_unit_cost != line.unit_cost_cents:
            changed_skus.append(line.sku)
        line_changes.append(
            MaterialLineChange(
                sku=line.sku,
                qty=line.qty,
                old_unit_cost_cents=line.unit_cost_cents,
                new_unit_cost_cents=new_unit_cost,
                old_line_cost_cents=old_line_cost,
                new_line_cost_cents=new_line_cost,
                vendor=update.vendor if (update and new_unit_cost != line.unit_cost_cents) else None,
            )
        )

    old_materials = materials_cost_cents(old_lines)
    new_materials = materials_cost_cents(new_lines)
    old_price = price_cents(item.sold_hours, item.sold_hour_rate_cents, old_materials, item.markup_pct)
    new_price = price_cents(item.sold_hours, item.sold_hour_rate_cents, new_materials, item.markup_pct)
    price_delta = new_price - old_price
    # margin = price - true cost (labor sold at rate + materials at cost). Equals the markup dollars.
    old_margin = old_price - (labor + old_materials)
    new_margin = new_price - (labor + new_materials)
    delta_pct = round((price_delta / old_price) * 100, 2) if old_price else 0.0
    beyond = abs(delta_pct) > tolerance_pct

    return PricebookItemChange(
        code=item.code,
        name=item.name,
        category=item.category,
        sold_hours=item.sold_hours,
        sold_hour_rate_cents=item.sold_hour_rate_cents,
        markup_pct=item.markup_pct,
        labor_cost_cents=labor,
        old_materials_cost_cents=old_materials,
        new_materials_cost_cents=new_materials,
        materials_delta_cents=new_materials - old_materials,
        old_price_cents=old_price,
        new_price_cents=new_price,
        price_delta_cents=price_delta,
        price_delta_pct=delta_pct,
        old_margin_cents=old_margin,
        new_margin_cents=new_margin,
        margin_delta_cents=new_margin - old_margin,
        changed_skus=changed_skus,
        beyond_tolerance=beyond,
        lines=line_changes,
    )


def analyze(data: PricebookData) -> PricebookAnalysis:
    # Last update wins per SKU (the most-recently-published cost), keyed deterministically.
    updates_by_sku: dict[str, VendorPriceUpdate] = {}
    for u in sorted(data.updates, key=lambda u: (u.effective_date, u.sku)):
        updates_by_sku[u.sku] = u

    tolerance = data.price_change_tolerance_pct
    changes = [_reprice_item(item, updates_by_sku, tolerance) for item in data.items]
    # Largest price move first — exactly how a pricing desk reviews a re-price batch.
    changes.sort(key=lambda c: (abs(c.price_delta_cents), c.code), reverse=True)

    all_skus = {line.sku for item in data.items for line in item.material_lines}
    skus_updated = {sku for sku in updates_by_sku if sku in all_skus}
    items_affected = sum(1 for c in changes if c.price_delta_cents != 0)
    items_flagged = sum(1 for c in changes if c.beyond_tolerance)
    total_price_delta = sum(c.price_delta_cents for c in changes)
    avg_markup = round(sum(i.markup_pct for i in data.items) / len(data.items), 2) if data.items else 0.0

    totals = PricebookTotals(
        items=len(data.items),
        items_affected=items_affected,
        items_flagged=items_flagged,
        total_price_delta_cents=total_price_delta,
        distinct_skus=len(all_skus),
        skus_updated=len(skus_updated),
        vendor_coverage_pct=_round_pct(len(skus_updated), len(all_skus)),
        avg_markup_pct=avg_markup,
    )
    return PricebookAnalysis(
        as_of=data.as_of,
        changes=changes,
        totals=totals,
        tolerance_pct=tolerance,
        inputs_hash=_hash_inputs(data),
    )


def _hash_inputs(data: PricebookData) -> str:
    payload = {
        "as_of": data.as_of.isoformat(),
        "tolerance_pct": data.price_change_tolerance_pct,
        "items": sorted(
            (
                {
                    "code": i.code,
                    "name": i.name,
                    "category": i.category,
                    "sold_hours": i.sold_hours,
                    "sold_hour_rate_cents": i.sold_hour_rate_cents,
                    "markup_pct": i.markup_pct,
                    "current_price_cents": i.current_price_cents,
                    "lines": sorted(
                        (asdict(line) for line in i.material_lines), key=lambda r: r["sku"]
                    ),
                }
                for i in data.items
            ),
            key=lambda r: r["code"],
        ),
        "updates": sorted(
            (
                {**asdict(u), "effective_date": u.effective_date.isoformat()}
                for u in data.updates
            ),
            key=lambda r: (r["sku"], r["effective_date"]),
        ),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
