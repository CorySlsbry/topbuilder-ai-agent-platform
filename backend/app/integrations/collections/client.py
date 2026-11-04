"""The A/R adapter boundary for the Collections agent (fixture now; QBO/ServiceTitan when live).

A/R aging is the reconciled book of record, so the primary live source is QuickBooks Online
(``AgedReceivables`` / ``AgedReceivableDetail`` + ``Invoice WHERE Balance > '0'``, see
``docs/QBO_DATA_MAP.md`` §2/§3.1). ServiceTitan's Accounting module can cross-check invoice-level AR.
The factory returns the fixture-backed client by default (offline demo) or the fail-closed live
skeleton when ``COLLECTIONS_MODE=quickbooks`` / ``servicetitan``.
"""
from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from app.agents.collections.models import ContactPreference, OpenInvoice, PromiseToPay
from app.config import Settings, get_settings


@runtime_checkable
class CollectionsClient(Protocol):
    """Read-only surface the Collections agent needs to build the worklist."""

    async def get_open_invoices(self) -> list[OpenInvoice]: ...
    async def get_promises(self) -> list[PromiseToPay]: ...
    async def get_contacts(self) -> list[ContactPreference]: ...


def get_collections_client(
    *, as_of: date | None = None, settings: Settings | None = None
) -> CollectionsClient:
    settings = settings or get_settings()
    mode = getattr(settings, "collections_mode", "fixture").lower()
    if mode in ("quickbooks", "servicetitan", "live"):
        from app.integrations.collections.live_client import LiveCollectionsClient

        return LiveCollectionsClient(settings)

    from app.integrations.collections.fixture_client import FixtureCollectionsClient

    return FixtureCollectionsClient(as_of=as_of)
