"""Pure tests for the event->agent router (ADR 0010)."""
from __future__ import annotations

from app.actions.service import ALWAYS_HITL_KINDS
from app.sync import router


def test_bill_routes_to_documents_with_ap_draft():
    decision = router.route("servicetitan", "bill", "accounting.bill.created")
    assert decision is not None
    assert decision.agent == "documents"  # create_ap_draft owner (KIND_OWNER alignment)
    assert decision.action_kind == "create_ap_draft"
    assert decision.advisory_only is False


def test_invoice_routes_to_collections_advisory():
    decision = router.route("quickbooks", "invoice", "accounting.invoice.created")
    assert decision is not None
    assert decision.agent == "collections"
    assert decision.advisory_only is True


def test_attachment_routes_to_documents():
    decision = router.route("quickbooks", "attachment", "documents.attachment.changed")
    assert decision is not None
    assert decision.agent == "documents"


def test_unmapped_entity_returns_typed_no_route():
    assert router.route("servicetitan", "telecom_call", "telecom.telecom_call.created") is None


def test_every_proposing_route_uses_an_always_hitl_money_kind():
    # Any entity whose standard action writes money/legal must propose a kind the gate forces to a
    # human even under auto. This locks the safety contract into the routing table itself.
    money_entities = {"bill", "purchase"}
    for entity in money_entities:
        decision = router.route("servicetitan", entity, f"accounting.{entity}.created")
        assert decision is not None and decision.action_kind in ALWAYS_HITL_KINDS
