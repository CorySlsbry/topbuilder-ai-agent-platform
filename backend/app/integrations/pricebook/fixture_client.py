"""Fixture-backed Pricebook client. Vendor update effective dates are day offsets from `as_of` (evergreen).

The fixture mirrors a residential HVAC contractor's ServiceTitan Pricebook: real materials (copper line,
R-410A refrigerant, sheet metal, fittings, a condenser, a line set, a filter, a thermostat) wired into a
handful of catalog items priced under the sold-hour model, plus a quarterly vendor price update that
raises a few SKUs (copper + refrigerant especially) so the re-price has real signal.
"""
from __future__ import annotations

import json
import pathlib
from datetime import date, timedelta

from app.agents.pricebook.models import MaterialLine, PricebookItem, VendorPriceUpdate

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"


def _load(name: str):
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


class FixturePricebookClient:
    def __init__(self, as_of: date | None = None) -> None:
        self.as_of = as_of or date.today()
        self._items = _load("items.json")
        self._updates = _load("vendor_updates.json")

    async def get_items(self) -> list[PricebookItem]:
        return [
            PricebookItem(
                code=row["code"],
                name=row["name"],
                sold_hours=float(row["sold_hours"]),
                sold_hour_rate_cents=int(row["sold_hour_rate_cents"]),
                markup_pct=float(row["markup_pct"]),
                category=row.get("category", "Service"),
                current_price_cents=int(row.get("current_price_cents", 0)),
                material_lines=[
                    MaterialLine(
                        sku=line["sku"],
                        qty=float(line["qty"]),
                        unit_cost_cents=int(line["unit_cost_cents"]),
                        description=line.get("description"),
                    )
                    for line in row.get("material_lines", [])
                ],
            )
            for row in self._items
        ]

    async def get_vendor_updates(self) -> list[VendorPriceUpdate]:
        return [
            VendorPriceUpdate(
                sku=row["sku"],
                vendor=row["vendor"],
                new_unit_cost_cents=int(row["new_unit_cost_cents"]),
                effective_date=self.as_of + timedelta(days=int(row.get("effective_offset", 0))),
                note=row.get("note"),
            )
            for row in self._updates
        ]
