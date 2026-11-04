"""Assemble an InventoryData bundle from an InventoryClient (DB-free)."""
from __future__ import annotations

from datetime import date

from app.agents.inventory.models import InventoryData
from app.integrations.inventory.client import InventoryClient


async def assemble_inventory_data(client: InventoryClient, *, as_of: date) -> InventoryData:
    return InventoryData(
        as_of=as_of,
        parts=await client.get_parts(),
        reorder_state=await client.get_reorder_state(),
        truck_stock=await client.get_truck_stock(),
        material_usage=await client.get_material_usage(),
        vendor_quotes=await client.get_vendor_quotes(),
    )
