"""Fixture-backed documents client — a realistic batch of inbound, unfiled documents + known customers."""
from __future__ import annotations

import json
import pathlib
from datetime import date

from app.agents.documents.ap_models import OpenJob, VendorBill
from app.agents.documents.models import Document, KnownCustomer
from app.agents.documents.warranty_models import InstalledEquipment

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"


def _load(name: str) -> list[dict]:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


class FixtureDocumentsClient:
    async def get_documents(self, as_of: date) -> list[Document]:
        return [Document(**row) for row in _load("documents.json")]

    async def get_customers(self) -> list[KnownCustomer]:
        return [KnownCustomer(**row) for row in _load("customers.json")]

    async def get_vendor_bills(self, as_of: date) -> list[VendorBill]:
        return [VendorBill(**{**row, "bill_date": _parse_date(row["bill_date"])})
                for row in _load("vendor_bills.json")]

    async def get_open_jobs(self) -> list[OpenJob]:
        return [OpenJob(**row) for row in _load("open_jobs.json")]

    async def get_installed_equipment(self, as_of: date) -> list[InstalledEquipment]:
        return [InstalledEquipment(**{**row, "install_date": _parse_date(row["install_date"])})
                for row in _load("installed_equipment.json")]
