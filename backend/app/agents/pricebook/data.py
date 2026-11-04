"""Assemble a PricebookData bundle from a PricebookClient (DB-free, easy to preview)."""
from __future__ import annotations

from datetime import date

from app.agents.pricebook.models import PricebookData
from app.integrations.pricebook.client import PricebookClient


async def assemble_pricebook_data(
    client: PricebookClient, *, as_of: date, tolerance_pct: float = 5.0
) -> PricebookData:
    return PricebookData(
        as_of=as_of,
        items=await client.get_items(),
        updates=await client.get_vendor_updates(),
        price_change_tolerance_pct=tolerance_pct,
    )
