"""Fixture-backed accounting client. AR/AP dates are day offsets from `as_of` (evergreen demo)."""
from __future__ import annotations

import json
import pathlib
from datetime import date, timedelta

from app.agents.financial.models import (
    APBill,
    ARInvoice,
    CompanyFinancials,
    Job,
    PaymentVelocity,
)

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"


def _load(name: str):
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


class FixtureAccountingClient:
    def __init__(self, as_of: date | None = None) -> None:
        self.as_of = as_of or date.today()
        self._company = _load("company.json")
        self._jobs = _load("jobs.json")
        self._ar = _load("ar_invoices.json")
        self._ap = _load("ap_bills.json")
        self._velocity = _load("payment_velocity.json")

    async def get_company_financials(self) -> CompanyFinancials:
        return CompanyFinancials(**self._company)

    async def get_jobs(self) -> list[Job]:
        return [Job(**row) for row in self._jobs]

    async def get_ar_invoices(self) -> list[ARInvoice]:
        return [
            ARInvoice(
                id=row["id"],
                customer_segment=row["customer_segment"],
                amount=float(row["amount"]),
                issued=self.as_of + timedelta(days=int(row["issued_offset"])),
                due=self.as_of + timedelta(days=int(row["due_offset"])),
                paid=row.get("paid", False),
            )
            for row in self._ar
        ]

    async def get_ap_bills(self) -> list[APBill]:
        return [
            APBill(
                id=row["id"],
                vendor=row["vendor"],
                amount=float(row["amount"]),
                due=self.as_of + timedelta(days=int(row["due_offset"])),
                paid=row.get("paid", False),
            )
            for row in self._ap
        ]

    async def get_payment_velocity(self) -> list[PaymentVelocity]:
        return [PaymentVelocity(**row) for row in self._velocity]
