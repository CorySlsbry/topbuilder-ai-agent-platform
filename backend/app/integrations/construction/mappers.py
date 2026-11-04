"""Pure mappers from construction-platform API payloads to canonical domain models.

These document the field-level transformations so a go-live is fill-in-the-blanks: each docstring names
the source fields -> canonical model fields. The bodies raise `NotImplementedError` because the exact
field names and units must be verified against a real tenant before they're trusted (ADR 0005 / the
ADR-0003 figure firewall — never guess a number). Construction platforms serve the jobs/documents/
accounting domains only. Mirrors `app/integrations/servicetitan/mappers.py`.
"""
from __future__ import annotations

from app.agents.documents.models import Document, KnownCustomer
from app.agents.financial.models import APBill, ARInvoice
from app.agents.routing.models import DispatchJob

# --- Buildertrend -------------------------------------------------------------------------


def map_buildertrend_job_to_job(row: dict) -> DispatchJob:
    """Buildertrend job/schedule -> DispatchJob (jobs domain).

    {id, jobName/title, jobType, jobsiteAddress->(x,y) zone coords, estimatedDurationMinutes,
    priority, requiredTrade->required_skill, scheduledStart->window_start_min,
    scheduledEnd->window_end_min, status}. Address geocodes to zone coords (or a drive-time matrix).
    """
    raise NotImplementedError(
        "Verify Buildertrend job/schedule field names + address->zone-coord projection."
    )


def map_buildertrend_document_to_document(row: dict) -> Document:
    """Buildertrend document/selection -> Document (documents domain).

    {id, fileName->filename, contentType->mime_type, documentType->declared_type,
    ownerName->customer_hint, amountCents->amount_cents, dueInDays->due_in_days,
    coiExpiresInDays->expiry_in_days, isSigned->signed, jobId->related_job_ref}.
    """
    raise NotImplementedError(
        "Verify Buildertrend document/selection field names + OCR-extracted amount/expiry/signed."
    )


def map_buildertrend_customer_to_customer(row: dict) -> KnownCustomer:
    """Buildertrend customer/owner -> KnownCustomer (documents-domain match key).

    {id->ref, displayName/ownerName->name}.
    """
    raise NotImplementedError("Verify Buildertrend customer/owner id + display-name fields.")


def map_buildertrend_invoice_to_accounting(row: dict) -> ARInvoice:
    """Buildertrend invoice -> ARInvoice (accounting domain — invoices/POs/budgets).

    {id, ownerSegment->customer_segment, totalAmount->amount, invoiceDate->issued,
    dueDate->due, status=='paid'->paid}.
    """
    raise NotImplementedError(
        "Verify Buildertrend invoice amount units + issued/due date fields + paid status."
    )


def map_buildertrend_po_to_accounting(row: dict) -> APBill:
    """Buildertrend purchase-order/budget line -> APBill (accounting domain — invoices/POs/budgets).

    {id, vendorName->vendor, amount->amount, dueDate->due, status=='paid'->paid}.
    """
    raise NotImplementedError(
        "Verify Buildertrend PO/budget vendor + amount units + due date + paid status."
    )


# --- Procore ------------------------------------------------------------------------------


def map_procore_project_to_job(row: dict) -> DispatchJob:
    """Procore project -> DispatchJob (jobs domain).

    {id, name/display_name->customer_name, project_type->trade, address->(x,y) zone coords,
    duration->duration_min, flag/priority->priority, trade->required_skill,
    start_date->window_start_min, completion_date->window_end_min, active/status->status}.
    Address geocodes to zone coords (or a drive-time matrix).
    """
    raise NotImplementedError(
        "Verify Procore project field names + address->zone-coord projection."
    )


def map_procore_rfi_to_document(row: dict) -> Document:
    """Procore RFI/submittal/daily-log -> Document (documents domain).

    {id, subject/title->filename, 'application/pdf'->mime_type, 'rfi'/'submittal'->declared_type,
    assignee/contact->customer_hint, cost_impact_cents->amount_cents, due_date->due_in_days,
    expiration->expiry_in_days, signed/approved->signed, project_id->related_job_ref}.
    """
    raise NotImplementedError(
        "Verify Procore RFI/submittal/daily-log field names + e-sign/amount/expiry extraction."
    )


def map_procore_vendor_to_customer(row: dict) -> KnownCustomer:
    """Procore vendor/contact -> KnownCustomer (documents-domain match key).

    {id->ref, name/company_name->name}.
    """
    raise NotImplementedError("Verify Procore vendor/contact id + name fields.")


def map_procore_prime_contract_to_accounting(row: dict) -> ARInvoice:
    """Procore prime-contract/owner-invoice -> ARInvoice (accounting domain — budgets/prime-contracts/
    change-orders).

    {id, owner_segment->customer_segment, grand_total->amount, created_at->issued,
    due_date->due, status=='paid'->paid}.
    """
    raise NotImplementedError(
        "Verify Procore prime-contract amount units + issued/due date fields + paid status."
    )


def map_procore_commitment_to_accounting(row: dict) -> APBill:
    """Procore commitment/change-order (subcontract/PO) -> APBill (accounting domain — budgets/
    prime-contracts/change-orders).

    {id, vendor.name->vendor, grand_total->amount, due_date->due, status=='paid'->paid}.
    """
    raise NotImplementedError(
        "Verify Procore commitment/change-order vendor + amount units + due date + paid status."
    )
