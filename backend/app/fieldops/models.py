"""Domain models for the field-ops quote builder (dependency-free, stdlib only)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PricebookService:
    code: str
    name: str
    category: str
    unit_price_cents: int
    taxable: bool = True


@dataclass(frozen=True)
class QuoteLineItem:
    service_code: str
    qty: int = 1


@dataclass(frozen=True)
class CatalogItem:
    """A pickable item for the equipment-driven margin quote builder.

    ``kind`` is ``equipment`` / ``labor`` / ``material``; equipment carries the labor it pulls
    (``sold_hours``) and a per-item target gross margin. Both price and cost are cents.
    """

    code: str
    name: str
    kind: str
    category: str
    cost_cents: int
    price_cents: int
    brand: str = ""
    sold_hours: float = 0.0
    target_margin_pct: float | None = None
