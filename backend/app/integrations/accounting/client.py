"""Accounting adapter boundary for the Financial agent (fixture now, QuickBooks when creds land)."""
from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from app.agents.financial.models import (
    APBill,
    ARInvoice,
    CompanyFinancials,
    Job,
    PaymentVelocity,
)
from app.config import Settings, get_settings


@runtime_checkable
class AccountingClient(Protocol):
    async def get_company_financials(self) -> CompanyFinancials: ...
    async def get_jobs(self) -> list[Job]: ...
    async def get_ar_invoices(self) -> list[ARInvoice]: ...
    async def get_ap_bills(self) -> list[APBill]: ...
    async def get_payment_velocity(self) -> list[PaymentVelocity]: ...


def get_accounting_client(
    *, as_of: date | None = None, settings: Settings | None = None
) -> AccountingClient:
    settings = settings or get_settings()
    if settings.accounting_mode.lower() == "quickbooks":
        from app.integrations.accounting.quickbooks_client import QuickBooksClient

        return QuickBooksClient(settings)

    from app.integrations.accounting.fixture_client import FixtureAccountingClient

    return FixtureAccountingClient(as_of=as_of)
