"""Fail-closed live Pricebook client (ADR 0005): raises rather than fabricate pricebook figures.

Wiring point (direct first-party ServiceTitan Pricebook API, NO Zapier):
  * ``get_items`` -> ServiceTitan ``pricebook/v2`` Services + Materials + Equipment, each with its
    cost members (the bill of materials) + the existing price. Map each to a ``PricebookItem`` with the
    material lines (sku, qty, unit_cost) and the sold hours + sold-hour rate from the item's labor config.
    Money read as integer cents.
  * ``get_vendor_updates`` -> the contractor's vendor cost feed (a vendor catalog export / price-increase
    letter parsed to (sku, new_unit_cost) rows), or ServiceTitan's vendor price list when present.

Until each is mapped + verified against a live company, every method raises ``NotImplementedError`` so a
partial connection surfaces as a clear error, never a wrong price (ADR 0003).
"""
from __future__ import annotations

from app.agents.pricebook.models import PricebookItem, VendorPriceUpdate
from app.config import Settings


class LivePricebookClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def get_items(self) -> list[PricebookItem]:
        raise NotImplementedError(
            "live Pricebook read is not yet wired; map ServiceTitan pricebook/v2 "
            "Services/Materials/Equipment (with cost members + labor config) to PricebookItem (cents) "
            "and verify against a real company (ADR 0005)."
        )

    async def get_vendor_updates(self) -> list[VendorPriceUpdate]:
        raise NotImplementedError(
            "live vendor price-update read is not yet wired; source from the contractor's vendor cost "
            "feed / ServiceTitan vendor price list and map to VendorPriceUpdate (cents)."
        )
