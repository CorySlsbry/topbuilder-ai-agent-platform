"""API schemas (spec-shaped) + mapper for the Documents agent."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.agents.documents.analytics import DocumentsAnalysis
from app.agents.documents.ap import ApAnalysis
from app.agents.documents.warranty import WarrantyAnalysis


def _usd(cents: int | None) -> float | None:
    return None if cents is None else round(cents / 100, 2)


class DocumentFilingOut(BaseModel):
    doc_id: str
    filename: str
    doc_type: str
    customer_ref: str
    customer_name: str
    department: str
    st_folder: str
    amount_usd: float | None
    expiry_in_days: int | None
    action: str  # file | expiring | needs_signature
    confidence: float
    reasoning: str


class UnfiledDocumentOut(BaseModel):
    doc_id: str
    filename: str
    doc_type: str
    reason: str


class DocumentsTotals(BaseModel):
    documents_processed: int
    auto_filed: int
    needs_signature: int
    needs_human: int
    expiring_soon: int
    extracted_value_usd: float


# --- PO/AP-from-email lane (A6) ---------------------------------------------------------------
class ApDraftOut(BaseModel):
    bill_id: str
    vendor: str
    doc_number: str
    amount_usd: float
    job_ref: str
    job_name: str
    customer_name: str
    confidence: float
    action: str
    reasoning: str


class UnmatchedBillOut(BaseModel):
    bill_id: str
    vendor: str
    doc_number: str
    amount_usd: float
    extracted_job_ref: str | None
    job_ref_source: str
    reason: str


class ApTotalsOut(BaseModel):
    bills_processed: int
    auto_proposed: int
    needs_human: int
    auto_value_usd: float
    needs_human_value_usd: float


class ApSectionOut(BaseModel):
    drafts: list[ApDraftOut]
    needs_human: list[UnmatchedBillOut]
    totals: ApTotalsOut


# --- Warranty-registration lane (A10) ---------------------------------------------------------
class WarrantyPacketOut(BaseModel):
    equipment_id: str
    job_ref: str
    customer_name: str
    brand: str
    model: str
    serial: str
    portal: str
    fields: dict[str, str]
    confidence: float
    reasoning: str


class WarrantyExceptionOut(BaseModel):
    equipment_id: str
    job_ref: str
    brand: str
    reason: str


class WarrantyTotalsOut(BaseModel):
    equipment_processed: int
    packets_ready: int
    needs_human: int


class WarrantySectionOut(BaseModel):
    packets: list[WarrantyPacketOut]
    needs_human: list[WarrantyExceptionOut]
    totals: WarrantyTotalsOut


class DocumentsRunResult(BaseModel):
    run_id: uuid.UUID | None = None
    agent: str = "documents"
    source_system: str = "ServiceTitan"  # the tenant's field-service system of record (fsm_provider)
    analysis_timestamp: datetime
    as_of: date
    filings: list[DocumentFilingOut]
    needs_human: list[UnfiledDocumentOut]
    totals: DocumentsTotals
    accounts_payable: ApSectionOut | None = None  # A6 PO/AP-from-email
    warranty: WarrantySectionOut | None = None    # A10 warranty registration
    reasoning_logs: str
    inputs_hash: str


def _ap_section(ap: ApAnalysis) -> ApSectionOut:
    return ApSectionOut(
        drafts=[
            ApDraftOut(
                bill_id=d.bill_id, vendor=d.vendor, doc_number=d.doc_number,
                amount_usd=round(d.amount_cents / 100, 2), job_ref=d.job_ref, job_name=d.job_name,
                customer_name=d.customer_name, confidence=d.confidence, action=d.action,
                reasoning=d.reasoning,
            )
            for d in ap.drafts
        ],
        needs_human=[
            UnmatchedBillOut(
                bill_id=b.bill_id, vendor=b.vendor, doc_number=b.doc_number,
                amount_usd=round(b.amount_cents / 100, 2), extracted_job_ref=b.extracted_job_ref,
                job_ref_source=b.job_ref_source, reason=b.reason,
            )
            for b in ap.needs_human
        ],
        totals=ApTotalsOut(
            bills_processed=ap.totals.bills_processed, auto_proposed=ap.totals.auto_proposed,
            needs_human=ap.totals.needs_human,
            auto_value_usd=round(ap.totals.auto_value_cents / 100, 2),
            needs_human_value_usd=round(ap.totals.needs_human_value_cents / 100, 2),
        ),
    )


def _warranty_section(wr: WarrantyAnalysis) -> WarrantySectionOut:
    return WarrantySectionOut(
        packets=[
            WarrantyPacketOut(
                equipment_id=p.equipment_id, job_ref=p.job_ref, customer_name=p.customer_name,
                brand=p.brand, model=p.model, serial=p.serial, portal=p.portal, fields=p.fields,
                confidence=p.confidence, reasoning=p.reasoning,
            )
            for p in wr.packets
        ],
        needs_human=[
            WarrantyExceptionOut(equipment_id=x.equipment_id, job_ref=x.job_ref, brand=x.brand,
                                 reason=x.reason)
            for x in wr.needs_human
        ],
        totals=WarrantyTotalsOut(
            equipment_processed=wr.totals.equipment_processed, packets_ready=wr.totals.packets_ready,
            needs_human=wr.totals.needs_human,
        ),
    )


def build_result(
    analysis: DocumentsAnalysis,
    *,
    narrative: str,
    analysis_timestamp: datetime,
    run_id: uuid.UUID | None = None,
    source_system: str = "ServiceTitan",
    ap_analysis: ApAnalysis | None = None,
    warranty_analysis: WarrantyAnalysis | None = None,
) -> DocumentsRunResult:
    filings = [
        DocumentFilingOut(
            doc_id=f.doc_id, filename=f.filename, doc_type=f.doc_type, customer_ref=f.customer_ref,
            customer_name=f.customer_name, department=f.department, st_folder=f.st_folder,
            amount_usd=_usd(f.amount_cents), expiry_in_days=f.expiry_in_days, action=f.action,
            confidence=f.confidence, reasoning=f.reasoning,
        )
        for f in analysis.filings
    ]
    needs_human = [
        UnfiledDocumentOut(doc_id=u.doc_id, filename=u.filename, doc_type=u.doc_type, reason=u.reason)
        for u in analysis.needs_human
    ]
    t = analysis.totals
    totals = DocumentsTotals(
        documents_processed=t.documents_processed,
        auto_filed=t.auto_filed,
        needs_signature=t.needs_signature,
        needs_human=t.needs_human,
        expiring_soon=t.expiring_soon,
        extracted_value_usd=round(t.extracted_value_cents / 100, 2),
    )
    return DocumentsRunResult(
        run_id=run_id,
        source_system=source_system,
        analysis_timestamp=analysis_timestamp,
        as_of=analysis.as_of,
        filings=filings,
        needs_human=needs_human,
        totals=totals,
        accounts_payable=_ap_section(ap_analysis) if ap_analysis is not None else None,
        warranty=_warranty_section(warranty_analysis) if warranty_analysis is not None else None,
        reasoning_logs=narrative,
        inputs_hash=analysis.inputs_hash,
    )
