"""Unit tests for the deterministic document-filing engine.

Hand-computed oracle (10 docs, 3 known customers):
  auto_filed 7 · needs_signature 1 (unsigned contract) · needs_human 2 (unknown type + no customer) ·
  expiring_soon 1 (COI ≤30d) · extracted_value 203,000¢ ($2,030 across the 3 docs with amounts).
"""
from __future__ import annotations

from datetime import date

from app.agents.documents import analytics as a
from app.agents.documents.models import Document, DocumentsData, KnownCustomer

AS_OF = date(2026, 6, 9)
CUSTOMERS = [
    KnownCustomer("CUST-1", "Whitfield Residence"),
    KnownCustomer("CUST-2", "Mercer Building"),
    KnownCustomer("CUST-3", "Okafor Property"),
]


def _doc(did: str, **kw) -> Document:
    base = {"filename": f"{did}.pdf", "mime_type": "application/pdf"}
    base.update(kw)
    return Document(id=did, **base)


def _scenario() -> DocumentsData:
    docs = [
        _doc("DOC1", declared_type="invoice", customer_hint="Whitfield Residence", amount_cents=48000),
        _doc("DOC2", declared_type="estimate", customer_hint="Mercer Building", amount_cents=120000),
        _doc("DOC3", declared_type="insurance_coi", customer_hint="Okafor Property", expiry_in_days=15),
        _doc("DOC4", declared_type="contract", customer_hint="Whitfield Residence", signed=False),
        _doc("DOC5", declared_type="permit", customer_hint="Mercer Building"),
        _doc("DOC6", declared_type="photo", customer_hint="Whitfield Residence"),
        _doc("DOC7", filename="scan_001.pdf", customer_hint="Whitfield Residence"),  # unclassifiable
        _doc("DOC8", declared_type="invoice", customer_hint="Nobody Inc", amount_cents=35000),  # no match
        _doc("DOC9", declared_type="insurance_coi", customer_hint="Okafor Property", expiry_in_days=90),
        _doc("DOC10", declared_type="w9", customer_hint="Mercer Building"),
    ]
    return DocumentsData(as_of=AS_OF, documents=docs, customers=CUSTOMERS)


class TestDocumentsEngine:
    def test_totals(self) -> None:
        t = a.analyze(_scenario()).totals
        assert (t.documents_processed, t.auto_filed, t.needs_signature, t.needs_human, t.expiring_soon) == (10, 7, 1, 2, 1)
        assert t.extracted_value_cents == 203_000

    def test_routing_and_actions(self) -> None:
        by = {f.doc_id: f for f in a.analyze(_scenario()).filings}
        assert (by["DOC1"].department, by["DOC1"].st_folder, by["DOC1"].action) == ("finance", "Invoices", "file")
        assert (by["DOC2"].department, by["DOC2"].st_folder) == ("sales", "Estimates")
        assert by["DOC4"].action == "needs_signature"          # unsigned contract
        assert by["DOC3"].action == "expiring"                  # COI ≤ 30d
        assert by["DOC9"].action == "file"                      # COI 90d is fine
        assert by["DOC1"].customer_ref == "CUST-1"

    def test_needs_human_reasons(self) -> None:
        nh = {u.doc_id: u.reason.lower() for u in a.analyze(_scenario()).needs_human}
        assert "classify" in nh["DOC7"]                          # unknown type
        assert "customer" in nh["DOC8"]                          # no match

    def test_inputs_hash_stable_and_hex(self) -> None:
        h1, h2 = a.analyze(_scenario()).inputs_hash, a.analyze(_scenario()).inputs_hash
        assert h1 == h2 and len(h1) == 64
