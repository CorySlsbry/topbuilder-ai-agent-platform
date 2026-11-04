"""The Pricebook adapter boundary for the Pricebook agent (fixture now; ServiceTitan when live).

The Pricebook lives in ServiceTitan's Pricebook module (services/materials/equipment with a bill of
materials + a price). The vendor price update is the contractor's quarterly cost feed (a vendor catalog
export / price-increase letter). The factory returns the fixture-backed client by default (offline demo)
or the fail-closed live skeleton when ``PRICEBOOK_MODE=servicetitan``.
"""
from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from app.agents.pricebook.models import PricebookItem, VendorPriceUpdate
from app.config import Settings, get_settings


@runtime_checkable
class PricebookClient(Protocol):
    """Read-only surface the Pricebook agent needs to re-price the catalog."""

    async def get_items(self) -> list[PricebookItem]: ...
    async def get_vendor_updates(self) -> list[VendorPriceUpdate]: ...


def get_pricebook_client(
    *, as_of: date | None = None, settings: Settings | None = None
) -> PricebookClient:
    settings = settings or get_settings()
    mode = getattr(settings, "pricebook_mode", "fixture").lower()
    if mode in ("servicetitan", "live"):
        from app.integrations.pricebook.live_client import LivePricebookClient

        return LivePricebookClient(settings)

    from app.integrations.pricebook.fixture_client import FixturePricebookClient

    return FixturePricebookClient(as_of=as_of)
