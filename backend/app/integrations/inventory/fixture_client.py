"""Fixture-backed inventory client (static stock snapshot)."""
from __future__ import annotations

import json
import pathlib

from datetime import date

from app.agents.inventory.models import (
    MaterialUsage,
    Part,
    ReorderState,
    TruckStockCount,
    VendorQuote,
)
from app.agents.inventory.proration import (
    ConsumableJobUsage,
    ConsumableLot,
    LotProrationInput,
)

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"


def _load(name: str) -> list[dict]:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


class FixtureInventoryClient:
    async def get_parts(self) -> list[Part]:
        return [Part(**row) for row in _load("parts.json")]

    async def get_reorder_state(self) -> list[ReorderState]:
        return [ReorderState(**row) for row in _load("reorder_state.json")]

    async def get_truck_stock(self) -> list[TruckStockCount]:
        return [TruckStockCount(**row) for row in _load("truck_stock.json")]

    async def get_material_usage(self) -> list[MaterialUsage]:
        return [MaterialUsage(**row) for row in _load("material_usage.json")]

    async def get_vendor_quotes(self) -> list[VendorQuote]:
        return [VendorQuote(**row) for row in _load("vendor_quotes.json")]

    async def get_consumable_lots(self) -> list[LotProrationInput]:
        out: list[LotProrationInput] = []
        for row in _load("consumable_lots.json"):
            lot = ConsumableLot(
                sku=row["sku"],
                name=row["name"],
                unit=row["unit"],
                total_quantity=row["total_quantity"],
                total_cost_cents=row["total_cost_cents"],
                pull_date=date.fromisoformat(row["pull_date"]),
                depletion_date=date.fromisoformat(row["depletion_date"]),
            )
            jobs = [
                ConsumableJobUsage(
                    job_id=j["job_id"],
                    usage_proxy=j.get("usage_proxy"),
                    job_revenue_cents=j.get("job_revenue_cents"),
                )
                for j in row["jobs"]
            ]
            out.append(LotProrationInput(lot=lot, jobs=jobs, method=row.get("method", "auto")))
        return out
