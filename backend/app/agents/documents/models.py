"""Domain models for the Documents agent (dependency-free, stdlib only).

A `Document` is the structured record of an inbound file (the OCR/extraction layer — external when live —
hands us these fields). The engine classifies it, matches it to a known customer, and decides where it
files in ServiceTitan and whether it needs a human (signature, expiring, or unrecognized).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app.agents.documents.ap_models import OpenJob, VendorBill
from app.agents.documents.warranty_models import InstalledEquipment


@dataclass(frozen=True)
class KnownCustomer:
    ref: str
    name: str


@dataclass(frozen=True)
class Document:
    id: str
    filename: str
    mime_type: str
    declared_type: str | None = None   # if the source already typed it; else inferred from the filename
    customer_hint: str | None = None   # name as it appears on the doc
    amount_cents: int | None = None    # extracted $ (invoices/estimates)
    due_in_days: int | None = None
    expiry_in_days: int | None = None  # for insurance COIs
    signed: bool | None = None         # for contracts
    related_job_ref: str | None = None


@dataclass(frozen=True)
class DocumentsData:
    as_of: date
    documents: list[Document]
    customers: list[KnownCustomer] = field(default_factory=list)
    # Alex's two extra lanes (A6 PO/AP-from-email, A10 warranty registration). Default-empty so the
    # core filing engine + every existing caller/test is unchanged; the service runs each lane only
    # when its inputs are present.
    vendor_bills: list[VendorBill] = field(default_factory=list)
    open_jobs: list[OpenJob] = field(default_factory=list)
    installed_equipment: list[InstalledEquipment] = field(default_factory=list)
