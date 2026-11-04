"""Field-ops service: the tech's pricebook, today's jobs, and the custom-quote builder.

Jobs are sourced from the dispatch adapter (the same jobs the Routing agent plans). Building a quote is
pure compute; submitting it proposes a `create_estimate` action through the human-approved action gate
(per the agent's autonomy policy) so the estimate can flow to ServiceTitan.
"""
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass
from datetime import date

from app.actions import service as actions_service
from app.actions.schemas import ActionOut, ProposeActionIn
from app.fieldops.margin import (
    DEFAULT_TARGET_MARGIN_PCT,
    LineKind,
    MarginQuoteInput,
    MarginQuoteResult,
    QuoteLine,
    compute_margin_quote,
)
from app.fieldops.models import CatalogItem, PricebookService, QuoteLineItem
from app.fieldops.quote import DEFAULT_TAX_RATE, QuoteError, QuoteResult, price_quote
from app.integrations.dispatch.client import get_dispatch_client
from app.security import Principal

_FIXTURES = pathlib.Path(__file__).parent / "fixtures"
_PRICEBOOK_PATH = _FIXTURES / "pricebook.json"
_EQUIPMENT_PATH = _FIXTURES / "equipment.json"
_MATERIALS_PATH = _FIXTURES / "materials.json"


def load_pricebook() -> list[PricebookService]:
    return [PricebookService(**row) for row in json.loads(_PRICEBOOK_PATH.read_text(encoding="utf-8"))]


def load_margin_catalog() -> list[CatalogItem]:
    """Equipment + labor + materials the tech picks from to build an equipment-driven margin quote.

    Equipment rows are ``kind="equipment"``; a material row's ``kind`` follows its ``category`` so a
    labor line costs out as labor (and is excluded from the excess-material check). The fixtures carry
    the cents directly so the catalog is the single source of cost/price/sold-hours.
    """
    items: list[CatalogItem] = []
    for row in json.loads(_EQUIPMENT_PATH.read_text(encoding="utf-8")):
        items.append(CatalogItem(kind="equipment", **row))
    for row in json.loads(_MATERIALS_PATH.read_text(encoding="utf-8")):
        kind = "labor" if row.get("category") == "labor" else "material"
        items.append(CatalogItem(kind=kind, **row))
    return items


@dataclass(frozen=True)
class MarginLineRequest:
    code: str
    qty: int = 1
    target_margin_pct: float | None = None


def build_margin_quote(
    requested: list[MarginLineRequest],
    *,
    target_margin_pct: float = DEFAULT_TARGET_MARGIN_PCT,
    sqft: int | None = None,
    avg_price_per_sqft_cents: int | None = None,
) -> MarginQuoteResult:
    """Resolve the picked catalog codes into priced quote lines and compute the margin + flags."""
    by_code = {c.code: c for c in load_margin_catalog()}
    lines: list[QuoteLine] = []
    for item in requested:
        cat = by_code.get(item.code)
        if cat is None:
            raise QuoteError(f"unknown item '{item.code}'")
        if item.qty <= 0:
            raise QuoteError(f"qty must be positive for '{item.code}'")
        lines.append(
            QuoteLine(
                kind=LineKind(cat.kind),
                name=cat.name,
                brand=cat.brand,
                code=cat.code,
                price_cents=cat.price_cents,
                cost_cents=cat.cost_cents,
                qty=item.qty,
                sold_hours=cat.sold_hours,
                target_margin_pct=item.target_margin_pct
                if item.target_margin_pct is not None
                else cat.target_margin_pct,
            )
        )
    return compute_margin_quote(
        MarginQuoteInput(
            lines=lines,
            target_margin_pct=target_margin_pct,
            sqft=sqft,
            avg_price_per_sqft_cents=avg_price_per_sqft_cents,
        )
    )


async def get_jobs(as_of: date):
    """Today's jobs for the field (from the dispatch adapter)."""
    client = get_dispatch_client(as_of=as_of)
    return await client.get_jobs(as_of)


def build_quote(line_items: list[QuoteLineItem], tax_rate: float | None = None) -> QuoteResult:
    rate = DEFAULT_TAX_RATE if tax_rate is None else tax_rate
    return price_quote(load_pricebook(), line_items, tax_rate=rate)


async def submit_quote(
    principal: Principal, *, job_ref: str | None, line_items: list[QuoteLineItem], tax_rate: float | None = None
) -> ActionOut:
    quote = build_quote(line_items, tax_rate)
    payload = ProposeActionIn(
        agent="fieldops",
        kind="create_estimate",
        params={
            "job_ref": job_ref,
            "total_cents": quote.total_cents,
            "lines": [
                {"service_code": line.service_code, "qty": line.qty, "line_total_cents": line.line_total_cents}
                for line in quote.lines
            ],
        },
    )
    return await actions_service.propose_action(principal, payload)
