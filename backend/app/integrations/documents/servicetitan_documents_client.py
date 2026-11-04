"""Live ServiceTitan documents client — skeleton (ADR 0005). Selected by DOCUMENTS_MODE=servicetitan.

Inbound files arrive via ServiceTitan attachments / email-to-ST / a watched inbox; an OCR/extraction
step (e.g. an LLM or a document-AI provider) populates `Document` fields. Known customers come from the
ServiceTitan Customers API. Filing back, generating, and e-signature are writes via the action gate.
Left to verify against a real tenant — mirrors the other live-client skeletons.
"""
from __future__ import annotations

from datetime import date

from app.agents.documents.ap_models import OpenJob, VendorBill
from app.agents.documents.models import Document, KnownCustomer
from app.agents.documents.warranty_models import InstalledEquipment
from app.config import Settings


class ServiceTitanDocumentsClient:
    def __init__(self, settings: Settings) -> None:
        self._s = settings

    async def get_documents(self, as_of: date) -> list[Document]:
        # Pull unfiled attachments + run OCR/extraction -> Document fields.
        raise NotImplementedError("Map ServiceTitan attachments + OCR extraction -> Document.")

    async def get_customers(self) -> list[KnownCustomer]:
        # GET /crm/v2/tenant/{tenant}/customers -> KnownCustomer (for matching).
        raise NotImplementedError("Map ServiceTitan customers -> KnownCustomer.")

    async def get_vendor_bills(self, as_of: date) -> list[VendorBill]:
        # Drain emailed vendor bills (watched inbox / ST email-to-ST) + OCR the PO/job number.
        raise NotImplementedError("Map emailed vendor bills + OCR job# -> VendorBill (job_ref_source).")

    async def get_open_jobs(self) -> list[OpenJob]:
        # GET /jpm/v2/tenant/{tenant}/jobs?jobStatus=Open -> OpenJob (ref = ST job id/number).
        raise NotImplementedError("Map ServiceTitan open jobs -> OpenJob.")

    async def get_installed_equipment(self, as_of: date) -> list[InstalledEquipment]:
        # Equipment installed on recently completed jobs; serial OCR'd from the serial-plate photo.
        raise NotImplementedError("Map ServiceTitan installed equipment + serial photo OCR -> InstalledEquipment.")
