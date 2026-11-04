"""Domain models for the PO/AP-from-email lane of the Documents agent (stdlib only).

A `VendorBill` is the structured record of an inbound vendor bill that arrived by email (the
OCR/extraction layer — external when live — hands us these fields). The engine matches it to an open
job and proposes an A/P entry; when the job number was extracted cleanly it can auto-propose, when it
was missing or only present as a low-confidence/handwritten value it routes to a human (Alex's ~90%
auto, ~10% human split). ADR-0003: deterministic compute here; the LLM only narrates.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class OpenJob:
    """An open ServiceTitan job a bill can be costed against (ref is the job number on the PO)."""

    ref: str
    name: str
    customer_name: str


@dataclass(frozen=True)
class VendorBill:
    """An inbound vendor bill (the extraction layer populates these fields).

    `extracted_job_ref` is the job number read off the PO/invoice; `job_ref_source` records HOW it was
    read so confidence reflects extraction quality (Alex: a clean printed job# ≈ 90% auto; a missing or
    handwritten one goes to a human). Money is integer cents.
    """

    id: str
    vendor: str
    amount_cents: int
    doc_number: str  # the vendor's invoice/bill number
    bill_date: date
    extracted_job_ref: str | None = None
    # how the job number was obtained: "printed" (clean OCR), "handwritten" (low-confidence OCR),
    # or "missing" (not found at all). Anything but a clean printed match is a human exception.
    job_ref_source: str = "missing"
    due_in_days: int | None = None


@dataclass(frozen=True)
class VendorBillsData:
    as_of: date
    bills: list[VendorBill]
    open_jobs: list[OpenJob] = field(default_factory=list)
