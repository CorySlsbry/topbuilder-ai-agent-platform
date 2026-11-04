"""Live ServiceTitan inventory client — skeleton (ADR 0005). Selected by INVENTORY_MODE=servicetitan.

Reuses ServiceTitan OAuth (see integrations/servicetitan/live_client.py). Per-entity mapping is left
to verify against a real tenant's inventory module.
"""
from __future__ import annotations

from app.agents.inventory.models import (
    MaterialUsage,
    Part,
    ReorderState,
    TruckStockCount,
    VendorQuote,
)
from app.agents.inventory.proration import LotProrationInput
from app.config import Settings


class ServiceTitanInventoryClient:
    def __init__(self, settings: Settings) -> None:
        self._s = settings

    async def get_parts(self) -> list[Part]:
        # GET /inventory/v2/tenant/{tenant}/purchase-order-markups + pricebook materials
        raise NotImplementedError("Map ST pricebook materials -> Part (cost + billable price).")

    async def get_reorder_state(self) -> list[ReorderState]:
        # ST inventory balances + usage history -> on_hand / avg_daily_usage / lead time
        raise NotImplementedError("Map ST inventory balances + usage -> ReorderState.")

    async def get_truck_stock(self) -> list[TruckStockCount]:
        # GET /inventory/v2/tenant/{tenant}/trucks + counts -> expected vs counted
        raise NotImplementedError("Map ST truck inventory counts -> TruckStockCount.")

    async def get_material_usage(self) -> list[MaterialUsage]:
        # Completed jobs' materials with billed flag -> MaterialUsage
        raise NotImplementedError("Map ST job materials (billed flag) -> MaterialUsage.")

    async def get_vendor_quotes(self) -> list[VendorQuote]:
        # ST vendor pricebook / purchase orders -> VendorQuote
        raise NotImplementedError("Map ST vendor pricing -> VendorQuote.")

    async def get_consumable_lots(self) -> list[LotProrationInput]:
        # Consumable lots: a PO/inventory purchase of a spool/coil (total qty + cost + pull date) joined
        # to the jobs it served until the replenish PO (depletion). Usage proxy = linear feet logged on
        # the job's materials, else None (engine falls back to even). ADR 0005: raise, never fabricate.
        raise NotImplementedError(
            "Map ST inventory consumable lots (PO purchase qty/cost + served jobs) -> LotProrationInput."
        )
