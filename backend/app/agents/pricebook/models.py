"""Domain models for the Pricebook re-pricing agent (dependency-free, stdlib only).

The ServiceTitan Pricebook drives the whole residential-contractor business: every catalog item carries
the labor (sold hours) and the materials (a bill of material lines) needed to do the job. Money is carried
as integer **cents** (ADR 0003); dollars only at the API boundary.

Alex's sold-hour pricing model (verbatim):

    price = sold_hours * sold_hour_rate + materials_cost + (materials_cost * material_markup)

where materials_cost for an item = sum over its material lines of (qty * vendor_unit_cost). When a vendor
publishes new unit costs (e.g. quarterly), the agent recomputes each affected item's materials_cost, then
its price under this model, and surfaces the deltas.

The pricebook + vendor price list are read from an adapter (fixture now; fail-closed ServiceTitan
Pricebook live skeleton) — see ``app/integrations/pricebook``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class MaterialLine:
    """One material on a pricebook item's bill of materials: a SKU, a quantity, and a vendor unit cost.

    ``unit_cost_cents`` is the contractor's CURRENT cost for one unit of the SKU; ``qty`` may be
    fractional (e.g. 1.5 lb of refrigerant, 20 ft of copper)."""

    sku: str
    qty: float
    unit_cost_cents: int  # current vendor cost for ONE unit of this SKU, integer cents
    description: str | None = None


@dataclass(frozen=True)
class PricebookItem:
    """One ServiceTitan Pricebook item (a service/material the contractor sells).

    ``current_price_cents`` is the price on the existing sheet; the engine recomputes the baseline price
    from the sold-hour model so a re-price is an apples-to-apples model delta, not sheet-vs-model drift."""

    code: str  # the pricebook item code (e.g. "P-AC")
    name: str
    sold_hours: float  # billable "sold" labor hours priced into the item
    sold_hour_rate_cents: int  # the contractor's sold-hour rate, integer cents
    markup_pct: float  # material markup percent applied on top of materials_cost (e.g. 25.0 = +25%)
    material_lines: list[MaterialLine] = field(default_factory=list)
    category: str = "Service"  # Install | Service | Maintenance | ... (free text, ST category)
    current_price_cents: int = 0  # the existing sheet price (display/reference only)


@dataclass(frozen=True)
class VendorPriceUpdate:
    """A new unit cost published by a vendor for a SKU (the quarterly price update)."""

    sku: str
    vendor: str
    new_unit_cost_cents: int  # the NEW cost for one unit of this SKU, integer cents
    effective_date: date
    note: str | None = None


@dataclass(frozen=True)
class PricebookData:
    as_of: date
    items: list[PricebookItem]
    updates: list[VendorPriceUpdate] = field(default_factory=list)
    # An item whose recomputed price moves by more than this percent (of its old price) is FLAGGED for a
    # human to review before it reaches a customer-facing quote (e.g. a vendor data error).
    price_change_tolerance_pct: float = 5.0
