"""Pure normalization: every detection source -> one canonical `InboundEvent` (ADR 0010).

A ServiceTitan `/export` row, a QuickBooks CDC row, a ServiceTitan or QuickBooks webhook payload, and
an in-house emit all collapse to the same shape with the same `natural_key`, so the dedupe layer can
merge a webhook (fast path) and the poll row (completeness) for the *same* change into one inbox row.
"""
from __future__ import annotations

from app.sync.models import (
    SOURCE_INAPP,
    SOURCE_QUICKBOOKS,
    SOURCE_SERVICETITAN,
    InboundEvent,
)

# QuickBooks entity name (PascalCase, as it appears in CDC + webhook notifications) -> our canonical
# lowercase entity. Entities absent here are not (yet) handled -> a typed no-map (None), never guessed.
_QBO_ENTITY: dict[str, str] = {
    "Bill": "bill",
    "Purchase": "purchase",
    "BillPayment": "payment",
    "Payment": "payment",
    "Invoice": "invoice",
    "JournalEntry": "journal_entry",
    "PurchaseOrder": "purchase_order",
    "VendorCredit": "vendor_credit",
    "Vendor": "vendor",
    "Customer": "customer",
    "Item": "pricebook_material",
    "Deposit": "deposit",
    "Attachable": "attachment",
}

# canonical entity -> the API module that forms the dotted event_type prefix.
_MODULE: dict[str, str] = {
    "bill": "accounting", "purchase": "accounting", "payment": "accounting",
    "invoice": "accounting", "journal_entry": "accounting", "vendor_credit": "accounting",
    "deposit": "accounting", "vendor": "accounting",
    "purchase_order": "inventory", "po_receipt": "inventory", "inventory_return": "inventory",
    "inventory_adjustment": "inventory", "inventory_transfer": "inventory",
    "job": "jpm", "appointment": "jpm", "project": "jpm",
    "booking": "crm", "lead": "crm", "customer": "crm", "location": "crm",
    "timesheet": "payroll", "gross_pay_item": "payroll", "payroll_adjustment": "payroll",
    "pricebook_material": "pricebook", "pricebook_service": "pricebook",
    "pricebook_equipment": "pricebook",
    "attachment": "documents",
}

# QuickBooks webhook operation -> canonical verb.
_QBO_OP: dict[str, str] = {
    "Create": "created", "Update": "updated", "Delete": "deleted",
    "Merge": "merged", "Void": "voided", "Emailed": "emailed",
}


def module_for(entity: str) -> str:
    return _MODULE.get(entity, "unknown")


def canonical_event_type(entity: str, verb: str) -> str:
    return f"{module_for(entity)}.{entity}.{verb}"


def canonical_qbo_entity(qbo_name: str) -> str | None:
    return _QBO_ENTITY.get(qbo_name)


def _job_ref(row: dict) -> str | None:
    for key in ("jobNumber", "jobId", "job_id", "jobRef"):
        value = row.get(key)
        if value:
            return str(value)
    job = row.get("job")
    if isinstance(job, dict):
        value = job.get("number") or job.get("id")
        if value:
            return str(value)
    return None


def normalize_st_export_row(entity: str, row: dict, *, verb: str = "changed") -> InboundEvent:
    """A ServiceTitan `/export` (or modified-since list) row -> InboundEvent. Raises if the row has
    no id (it could not be deduped) so the caller can dead-letter it rather than guess."""
    provider_id = row.get("id") if row.get("id") is not None else row.get("Id")
    return InboundEvent.of(
        source=SOURCE_SERVICETITAN,
        entity=entity,
        event_type=canonical_event_type(entity, verb),
        provider_id="" if provider_id is None else str(provider_id),
        modified_at=row.get("modifiedOn") or row.get("modifiedOnUtc"),
        job_ref=_job_ref(row),
        payload=row,
    )


def normalize_qbo_row(qbo_entity: str, row: dict, *, verb: str = "changed") -> InboundEvent | None:
    """A QuickBooks CDC entity row -> InboundEvent, or None if the entity is not mapped."""
    entity = canonical_qbo_entity(qbo_entity)
    if entity is None:
        return None
    provider_id = row.get("Id") if row.get("Id") is not None else row.get("id")
    meta = row.get("MetaData") or {}
    modified = meta.get("LastUpdatedTime") or row.get("lastUpdated")
    return InboundEvent.of(
        source=SOURCE_QUICKBOOKS,
        entity=entity,
        event_type=canonical_event_type(entity, verb),
        provider_id="" if provider_id is None else str(provider_id),
        modified_at=modified,
        job_ref=_job_ref(row),
        payload=row,
    )


def normalize_qbo_webhook_entity(notification: dict) -> InboundEvent | None:
    """One entity entry from a QBO webhook (`eventNotifications[].dataChangeEvent.entities[]`) ->
    InboundEvent, or None if the entity is not mapped. Carries the same natural_key as the CDC/poll
    row for the same change, so webhook + poll collapse to one inbox row."""
    entity = canonical_qbo_entity(str(notification.get("name", "")))
    if entity is None:
        return None
    provider_id = notification.get("id")
    verb = _QBO_OP.get(str(notification.get("operation", "")), "changed")
    return InboundEvent.of(
        source=SOURCE_QUICKBOOKS,
        entity=entity,
        event_type=canonical_event_type(entity, verb),
        provider_id="" if provider_id is None else str(provider_id),
        modified_at=notification.get("lastUpdated"),
        payload=notification,
    )


def normalize_inapp(
    entity: str,
    payload: dict,
    *,
    provider_id: str,
    modified_at: str | None = None,
    verb: str = "created",
    job_ref: str | None = None,
) -> InboundEvent:
    """An app-owned emit (field-PWA receipt snap, email-in) -> InboundEvent. The instant, clean-OCR
    path; the caller supplies a stable provider_id (e.g. the stored blob id)."""
    return InboundEvent.of(
        source=SOURCE_INAPP,
        entity=entity,
        event_type=canonical_event_type(entity, verb),
        provider_id=provider_id,
        modified_at=modified_at,
        job_ref=job_ref,
        payload=payload,
    )
