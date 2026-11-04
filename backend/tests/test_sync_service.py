"""Pure tests for the drain's planning logic + the Phase-1 bill handler (ADR 0010)."""
from __future__ import annotations

from app.sync import service


def _bill_envelope(*, job_ref: str | None, row: dict) -> dict:
    return {"entity": "bill", "provider_id": str(row.get("id") or ""), "job_ref": job_ref, "row": row}


def test_parse_entity_pulls_the_middle_segment():
    assert service.parse_entity("accounting.bill.created") == "bill"
    assert service.parse_entity("documents.attachment.changed") == "attachment"
    assert service.parse_entity("garbage") == ""


def test_amount_cents_prefers_explicit_then_dollar_fields():
    assert service._amount_cents({"amount_cents": 41250}) == 41250
    assert service._amount_cents({"total": 412.50}) == 41250
    assert service._amount_cents({"TotalAmt": 1000}) == 100000
    assert service._amount_cents({}) == 0


def test_bill_with_a_matched_job_proposes_an_ap_draft():
    envelope = _bill_envelope(
        job_ref="J-8842",
        row={"id": 8842, "total": 412.50, "vendor": "Ferguson", "docNumber": "INV-1"},
    )
    plan = service.plan_event(
        source="servicetitan",
        event_type="accounting.bill.created",
        external_id="servicetitan:bill:8842:2026-06-27T10:00:00Z",
        payload=envelope,
    )

    assert plan.outcome == "propose"
    assert plan.agent == "documents"
    assert plan.proposal is not None
    assert plan.proposal.kind == "create_ap_draft"
    assert plan.proposal.params == {
        "bill_id": "8842",
        "job_ref": "J-8842",
        "amount_cents": 41250,
        "vendor": "Ferguson",
        "doc_number": "INV-1",
        "intake_id": "servicetitan:bill:8842:2026-06-27T10:00:00Z",
    }


def test_bill_without_a_job_match_degrades_to_advisory_never_guesses():
    envelope = _bill_envelope(job_ref=None, row={"id": 8842, "total": 412.50})
    plan = service.plan_event(
        source="quickbooks",
        event_type="accounting.bill.created",
        external_id="quickbooks:bill:8842:na",
        payload=envelope,
    )
    assert plan.outcome == "advisory"
    assert plan.agent == "documents"
    assert plan.proposal is None


def test_invoice_routes_to_collections_advisory_no_proposal():
    plan = service.plan_event(
        source="quickbooks",
        event_type="accounting.invoice.created",
        external_id="quickbooks:invoice:1:na",
        payload={"entity": "invoice", "row": {"Id": "1"}},
    )
    assert plan.outcome == "advisory"
    assert plan.agent == "collections"
    assert plan.proposal is None


def test_unmapped_entity_is_no_route_not_a_drop():
    plan = service.plan_event(
        source="servicetitan",
        event_type="telecom.telecom_call.created",
        external_id="servicetitan:telecom_call:1:na",
        payload={"row": {}},
    )
    assert plan.outcome == "no_route"
    assert plan.proposal is None
