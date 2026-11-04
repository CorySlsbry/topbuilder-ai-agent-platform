"""Deterministic quote engine for the field tech's custom-quote builder.

The tech adds/removes services from the pricebook on their phone; this prices whatever is selected:
line totals, subtotal, tax (on taxable lines only), and grand total. Pure and exact — the same numbers
on the phone, the persisted estimate, and (when pushed) ServiceTitan. No LLM, no rounding drift.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.fieldops.models import PricebookService, QuoteLineItem

DEFAULT_TAX_RATE = 0.086  # configure per tenant/jurisdiction when live


class QuoteError(ValueError):
    """An unknown service code or a non-positive quantity."""


@dataclass(frozen=True)
class PricedLine:
    service_code: str
    name: str
    qty: int
    unit_price_cents: int
    line_total_cents: int
    taxable: bool


@dataclass(frozen=True)
class QuoteResult:
    lines: list[PricedLine]
    subtotal_cents: int
    taxable_subtotal_cents: int
    tax_rate: float
    tax_cents: int
    total_cents: int


def price_quote(
    pricebook: list[PricebookService],
    line_items: list[QuoteLineItem],
    *,
    tax_rate: float = DEFAULT_TAX_RATE,
) -> QuoteResult:
    by_code = {s.code: s for s in pricebook}
    lines: list[PricedLine] = []
    for item in line_items:
        svc = by_code.get(item.service_code)
        if svc is None:
            raise QuoteError(f"unknown service '{item.service_code}'")
        if item.qty <= 0:
            raise QuoteError(f"qty must be positive for '{item.service_code}'")
        lines.append(
            PricedLine(
                service_code=svc.code, name=svc.name, qty=item.qty,
                unit_price_cents=svc.unit_price_cents,
                line_total_cents=svc.unit_price_cents * item.qty, taxable=svc.taxable,
            )
        )
    subtotal = sum(line.line_total_cents for line in lines)
    taxable_subtotal = sum(line.line_total_cents for line in lines if line.taxable)
    tax = round(taxable_subtotal * tax_rate)
    return QuoteResult(
        lines=lines,
        subtotal_cents=subtotal,
        taxable_subtotal_cents=taxable_subtotal,
        tax_rate=tax_rate,
        tax_cents=tax,
        total_cents=subtotal + tax,
    )
