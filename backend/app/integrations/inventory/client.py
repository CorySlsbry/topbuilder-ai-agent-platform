"""Inventory adapter boundary for the Inventory agent (fixture now, ServiceTitan when live)."""
from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from app.agents.inventory.models import (
    MaterialUsage,
    Part,
    ReorderState,
    TruckStockCount,
    VendorQuote,
)
from app.agents.inventory.proration import LotProrationInput
from app.config import Settings, get_settings


@runtime_checkable
class InventoryClient(Protocol):
    async def get_parts(self) -> list[Part]: ...
    async def get_reorder_state(self) -> list[ReorderState]: ...
    async def get_truck_stock(self) -> list[TruckStockCount]: ...
    async def get_material_usage(self) -> list[MaterialUsage]: ...
    async def get_vendor_quotes(self) -> list[VendorQuote]: ...
    # Partial-consumable proration inputs: one LotProrationInput per consumable lot pulled from
    # inventory (spools, copper coils) + the jobs it served over its lifespan.
    async def get_consumable_lots(self) -> list[LotProrationInput]: ...


def get_inventory_client(
    *, as_of: date | None = None, settings: Settings | None = None
) -> InventoryClient:
    settings = settings or get_settings()
    if settings.inventory_mode.lower() == "servicetitan":
        from app.integrations.inventory.servicetitan_inventory_client import (
            ServiceTitanInventoryClient,
        )

        return ServiceTitanInventoryClient(settings)

    from app.integrations.inventory.fixture_client import FixtureInventoryClient

    return FixtureInventoryClient()
