"""The documents adapter boundary for the Documents agent (read-only; ADR 0005)."""
from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from app.agents.documents.ap_models import OpenJob, VendorBill
from app.agents.documents.models import Document, KnownCustomer
from app.agents.documents.warranty_models import InstalledEquipment
from app.config import Settings, get_settings


@runtime_checkable
class DocumentsClient(Protocol):
    async def get_documents(self, as_of: date) -> list[Document]: ...
    async def get_customers(self) -> list[KnownCustomer]: ...
    # Alex's PO/AP-from-email lane (A6): inbound vendor bills + the open jobs to cost them against.
    async def get_vendor_bills(self, as_of: date) -> list[VendorBill]: ...
    async def get_open_jobs(self) -> list[OpenJob]: ...
    # Alex's warranty-registration lane (A10): equipment installed on recently completed jobs.
    async def get_installed_equipment(self, as_of: date) -> list[InstalledEquipment]: ...


def get_documents_client(
    *, as_of: date | None = None, settings: Settings | None = None
) -> DocumentsClient:
    settings = settings or get_settings()
    if settings.documents_mode.lower() == "servicetitan":
        from app.integrations.documents.servicetitan_documents_client import ServiceTitanDocumentsClient

        return ServiceTitanDocumentsClient(settings)

    from app.integrations.documents.fixture_client import FixtureDocumentsClient

    return FixtureDocumentsClient()
