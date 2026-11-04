"""Assemble a DocumentsData bundle from a DocumentsClient (DB-free).

Pulls the core filing inputs (documents + customers) plus Alex's two extra lanes (A6 PO/AP-from-email:
vendor bills + open jobs; A10 warranty: installed equipment). The extra lanes are fetched best-effort:
a client that doesn't implement them, or whose live skeleton raises (ADR 0005 fail-closed), yields an
empty list for that lane — so the core filing run is never broken by an unmapped extra lane.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import date
from typing import TypeVar

from app.agents.documents.models import DocumentsData
from app.integrations.documents.client import DocumentsClient

T = TypeVar("T")


async def _best_effort(coro_factory: Callable[[], Awaitable[list[T]]]) -> list[T]:
    """Run an optional adapter call; an absent method or a fail-closed raise -> [] (never blocks)."""
    try:
        return await coro_factory()
    except (AttributeError, NotImplementedError):
        return []


async def assemble_documents_data(client: DocumentsClient, *, as_of: date) -> DocumentsData:
    return DocumentsData(
        as_of=as_of,
        documents=await client.get_documents(as_of),
        customers=await client.get_customers(),
        vendor_bills=await _best_effort(lambda: client.get_vendor_bills(as_of)),
        open_jobs=await _best_effort(lambda: client.get_open_jobs()),
        installed_equipment=await _best_effort(lambda: client.get_installed_equipment(as_of)),
    )
