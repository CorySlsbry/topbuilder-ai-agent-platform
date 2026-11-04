"""Deterministic document-filing engine: classify -> match customer -> route -> decide action.

No LLM, no randomness. Decides each document's type, the customer it belongs to, the ServiceTitan
folder + owning department it files into, and whether a human is needed (unsigned contract, expiring
COI, unrecognized type, or no customer match). The reasoning layer narrates; it never decides. Filing,
generating, and sending for signature are WRITES — they flow through the action gate per the agent's
autonomy policy (ADR 0007).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date

from app.agents.documents.models import Document, DocumentsData, KnownCustomer

EXPIRY_THRESHOLD_DAYS = 30

# type -> (owning department, ServiceTitan folder)
ROUTING: dict[str, tuple[str, str]] = {
    "invoice": ("finance", "Invoices"),
    "estimate": ("sales", "Estimates"),
    "permit": ("dispatch", "Permits"),
    "insurance_coi": ("compliance", "Insurance"),
    "contract": ("sales", "Contracts"),
    "photo": ("dispatch", "Job Photos"),
    "inspection": ("dispatch", "Inspections"),
    "w9": ("finance", "Vendor W9s"),
}
KNOWN_TYPES = set(ROUTING)

# filename keyword -> type (used only when the source didn't declare a type)
_KEYWORDS: list[tuple[str, str]] = [
    ("invoice", "invoice"), ("estimate", "estimate"), ("quote", "estimate"), ("permit", "permit"),
    ("coi", "insurance_coi"), ("insurance", "insurance_coi"), ("contract", "contract"),
    ("agreement", "contract"), ("inspection", "inspection"), ("w9", "w9"), ("w-9", "w9"),
    (".jpg", "photo"), (".jpeg", "photo"), (".png", "photo"), ("photo", "photo"),
]


# --------------------------------------------------------------------------------------------
# Result types
# --------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class DocumentFiling:
    doc_id: str
    filename: str
    doc_type: str
    customer_ref: str
    customer_name: str
    department: str
    st_folder: str
    amount_cents: int | None
    expiry_in_days: int | None
    action: str          # file | expiring | needs_signature
    confidence: float
    reasoning: str


@dataclass(frozen=True)
class UnfiledDocument:
    doc_id: str
    filename: str
    doc_type: str
    reason: str


@dataclass(frozen=True)
class DocumentsTotals:
    documents_processed: int
    auto_filed: int
    needs_signature: int
    needs_human: int
    expiring_soon: int
    extracted_value_cents: int


@dataclass(frozen=True)
class DocumentsAnalysis:
    as_of: date
    filings: list[DocumentFiling]
    needs_human: list[UnfiledDocument]
    totals: DocumentsTotals
    inputs_hash: str


# --------------------------------------------------------------------------------------------
# Pure primitives
# --------------------------------------------------------------------------------------------
def _normalize(s: str) -> str:
    return " ".join(s.lower().split())


def classify(doc: Document) -> tuple[str, float]:
    if doc.declared_type and doc.declared_type in KNOWN_TYPES:
        return doc.declared_type, 0.95
    fn = doc.filename.lower()
    for keyword, dtype in _KEYWORDS:
        if keyword in fn:
            return dtype, 0.8
    return "unknown", 0.4


def match_customer(doc: Document, customers: list[KnownCustomer]) -> KnownCustomer | None:
    if not doc.customer_hint:
        return None
    hint = _normalize(doc.customer_hint)
    for c in customers:
        name = _normalize(c.name)
        if hint == name or hint in name or name in hint:
            return c
    return None


# --------------------------------------------------------------------------------------------
# Engine
# --------------------------------------------------------------------------------------------
def analyze(data: DocumentsData) -> DocumentsAnalysis:
    filings: list[DocumentFiling] = []
    needs_human: list[UnfiledDocument] = []

    for doc in data.documents:
        dtype, confidence = classify(doc)
        if dtype == "unknown":
            needs_human.append(UnfiledDocument(doc.id, doc.filename, dtype, "could not classify document type"))
            continue
        customer = match_customer(doc, data.customers)
        if customer is None:
            needs_human.append(
                UnfiledDocument(doc.id, doc.filename, dtype, f"no matching customer for '{doc.customer_hint}'")
            )
            continue

        department, folder = ROUTING[dtype]
        if dtype == "contract" and doc.signed is False:
            action = "needs_signature"
            note = "route for e-signature"
        elif dtype == "insurance_coi" and doc.expiry_in_days is not None and doc.expiry_in_days <= EXPIRY_THRESHOLD_DAYS:
            action = "expiring"
            note = f"COI expires in {doc.expiry_in_days}d — flag compliance"
        else:
            action = "file"
            note = f"file to {department}/{folder}"

        filings.append(
            DocumentFiling(
                doc_id=doc.id, filename=doc.filename, doc_type=dtype, customer_ref=customer.ref,
                customer_name=customer.name, department=department, st_folder=folder,
                amount_cents=doc.amount_cents, expiry_in_days=doc.expiry_in_days, action=action,
                confidence=confidence,
                reasoning=f"{doc.filename}: {dtype} for {customer.name} (conf {confidence:.2f}); {note}.",
            )
        )

    totals = DocumentsTotals(
        documents_processed=len(data.documents),
        auto_filed=sum(1 for f in filings if f.action in ("file", "expiring")),
        needs_signature=sum(1 for f in filings if f.action == "needs_signature"),
        needs_human=len(needs_human),
        expiring_soon=sum(1 for f in filings if f.action == "expiring"),
        extracted_value_cents=sum(d.amount_cents or 0 for d in data.documents),
    )
    return DocumentsAnalysis(data.as_of, filings, needs_human, totals, _hash_inputs(data))


def _hash_inputs(data: DocumentsData) -> str:
    payload = {
        "as_of": data.as_of.isoformat(),
        "documents": sorted((asdict(d) for d in data.documents), key=lambda r: r["id"]),
        "customers": sorted((asdict(c) for c in data.customers), key=lambda r: r["ref"]),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
