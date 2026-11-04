"""Pure oracle tests for the event normalizer (ADR 0010)."""
from __future__ import annotations

import pytest

from app.sync import normalize
from app.sync.models import SOURCE_INAPP, SOURCE_QUICKBOOKS, SOURCE_SERVICETITAN


def test_st_export_bill_row_maps_to_canonical_event():
    row = {"id": 8842, "modifiedOn": "2026-06-27T10:00:00Z", "jobNumber": "J-8842", "total": 412.50}
    event = normalize.normalize_st_export_row("bill", row, verb="created")

    assert event.source == SOURCE_SERVICETITAN
    assert event.entity == "bill"
    assert event.event_type == "accounting.bill.created"
    assert event.provider_id == "8842"
    assert event.job_ref == "J-8842"
    assert event.natural_key == "servicetitan:bill:8842:2026-06-27T10:00:00Z"


def test_st_export_row_without_id_is_rejected():
    with pytest.raises(ValueError):
        normalize.normalize_st_export_row("bill", {"modifiedOn": "2026-06-27T10:00:00Z"})


def test_qbo_cdc_bill_row_uses_metadata_last_updated():
    row = {"Id": "42", "MetaData": {"LastUpdatedTime": "2026-06-27T10:00:00-07:00"}, "TotalAmt": 412.5}
    event = normalize.normalize_qbo_row("Bill", row)

    assert event is not None
    assert event.source == SOURCE_QUICKBOOKS
    assert event.entity == "bill"
    assert event.provider_id == "42"
    assert event.external_modified_at == "2026-06-27T10:00:00-07:00"
    assert event.natural_key == "quickbooks:bill:42:2026-06-27T10:00:00-07:00"


def test_qbo_attachable_maps_to_attachment_entity():
    row = {"Id": "99", "MetaData": {"LastUpdatedTime": "2026-06-27T12:00:00Z"}}
    event = normalize.normalize_qbo_row("Attachable", row)

    assert event is not None
    assert event.entity == "attachment"
    assert event.event_type == "documents.attachment.changed"


def test_unmapped_qbo_entity_returns_none_not_a_guess():
    assert normalize.normalize_qbo_row("TaxAgency", {"Id": "1"}) is None
    assert normalize.normalize_qbo_webhook_entity({"name": "TaxAgency", "id": "1"}) is None


def test_qbo_webhook_and_cdc_row_for_same_change_share_natural_key():
    # The collapse property: a webhook (fast path) and the poll row (completeness) for the SAME bill
    # change must produce the SAME natural_key so the inbox dedupe merges them into one row.
    modified = "2026-06-27T10:00:00-07:00"
    cdc = normalize.normalize_qbo_row(
        "Bill", {"Id": "42", "MetaData": {"LastUpdatedTime": modified}}
    )
    hook = normalize.normalize_qbo_webhook_entity(
        {"name": "Bill", "id": "42", "operation": "Update", "lastUpdated": modified}
    )

    assert cdc is not None and hook is not None
    assert cdc.natural_key == hook.natural_key == "quickbooks:bill:42:2026-06-27T10:00:00-07:00"
    # ...even though the verbs differ (CDC is state-only, the webhook knows it was an update).
    assert cdc.event_type == "accounting.bill.changed"
    assert hook.event_type == "accounting.bill.updated"


def test_inapp_emit_is_sourced_inapp_with_supplied_id():
    event = normalize.normalize_inapp(
        "attachment", {"blob": "k1"}, provider_id="receipt-k1", job_ref="J-8842"
    )
    assert event.source == SOURCE_INAPP
    assert event.entity == "attachment"
    assert event.provider_id == "receipt-k1"
    assert event.job_ref == "J-8842"
    assert event.natural_key == "inapp:attachment:receipt-k1:na"
