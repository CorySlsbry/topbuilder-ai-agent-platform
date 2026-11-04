"""Assemble a FinancialData bundle from an AccountingClient (DB-free).

Jobs/WIP and payment velocity are fetched best-effort (the same pattern as
`agents/documents/data.py`): a client that doesn't implement a lane, or whose live skeleton raises
(ADR 0005 fail-closed — e.g. QBO's `get_jobs`/`get_payment_velocity` stay unmapped until verified
against a real company), yields an empty list for that lane — so a live QBO tenant still completes
a run on the lanes that ARE available (cash, AR, AP) instead of failing the whole run.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import date
from typing import TypeVar

from app.agents.financial.models import FinancialData
from app.integrations.accounting.client import AccountingClient

T = TypeVar("T")


async def _best_effort(coro_factory: Callable[[], Awaitable[list[T]]]) -> list[T]:
    """Run an optional adapter call; an absent method or a fail-closed raise -> [] (never blocks)."""
    try:
        return await coro_factory()
    except (AttributeError, NotImplementedError):
        return []


async def assemble_financial_data(client: AccountingClient, *, as_of: date) -> FinancialData:
    company = await client.get_company_financials()
    return FinancialData(
        as_of=as_of,
        starting_cash=company.starting_cash,
        target_gross_margin=company.target_gross_margin,
        jobs=await _best_effort(lambda: client.get_jobs()),
        ar_invoices=await client.get_ar_invoices(),
        ap_bills=await client.get_ap_bills(),
        payment_velocity=await _best_effort(lambda: client.get_payment_velocity()),
    )
