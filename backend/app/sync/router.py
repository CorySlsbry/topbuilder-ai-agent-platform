"""Pure routing table: a normalized event -> the owning agent (+ the action it would propose).

Source-agnostic by entity: a `bill` routes to the Documents agent (create_ap_draft's owner) whether it arrived from a
ServiceTitan accounting `/export` row or a QuickBooks `Bill` webhook. `action_kind` is the standard
write for that entity (or `None` for advisory-only); whether anything is actually proposed, and the
exact params, is decided by the drain service's per-entity handlers + the ADR-0007 gate. Money/legal
kinds (`create_ap_draft`, dunning, payroll, pricebook price) are `ALWAYS_HITL` in the gate regardless.
"""
from __future__ import annotations

from app.sync.models import RouteDecision

# entity -> RouteDecision. action_kind=None means advisory-only (the agent assesses; any write it
# proposes, e.g. conditional dunning on an overdue invoice, is built by the service handler).
_ROUTES: dict[str, RouteDecision] = {
    # Accounting / AP / AR
    # create_ap_draft's OWNING agent is 'documents' (actions/ownership.KIND_OWNER): the stored agent
    # must match the owner or the approvals inbox and run narration disagree about who owns the row.
    # (documents and financial are both in the finance department, so approver scope is unchanged.)
    "bill": RouteDecision(agent="documents", action_kind="create_ap_draft"),
    "purchase": RouteDecision(agent="documents", action_kind="create_ap_draft"),
    "vendor_credit": RouteDecision(agent="financial"),
    "invoice": RouteDecision(agent="collections"),
    "payment": RouteDecision(agent="collections"),
    "deposit": RouteDecision(agent="financial"),
    "journal_entry": RouteDecision(agent="financial"),
    "vendor": RouteDecision(agent="financial"),
    "customer": RouteDecision(agent="collections"),
    # Inventory
    "purchase_order": RouteDecision(agent="inventory"),
    "po_receipt": RouteDecision(agent="inventory"),
    "inventory_return": RouteDecision(agent="inventory"),
    "inventory_adjustment": RouteDecision(agent="inventory"),
    "inventory_transfer": RouteDecision(agent="inventory"),
    # Jobs / dispatch
    "job": RouteDecision(agent="financial"),
    "appointment": RouteDecision(agent="routing"),
    # CRM
    "booking": RouteDecision(agent="booking"),
    "lead": RouteDecision(agent="booking"),
    # Payroll
    "timesheet": RouteDecision(agent="workforce"),
    "gross_pay_item": RouteDecision(agent="workforce"),
    "payroll_adjustment": RouteDecision(agent="workforce"),
    # Pricebook
    "pricebook_material": RouteDecision(agent="pricebook"),
    "pricebook_service": RouteDecision(agent="pricebook"),
    "pricebook_equipment": RouteDecision(agent="pricebook"),
    # Documents / attachments (receipt images)
    "attachment": RouteDecision(agent="documents"),
}


def route(source: str, entity: str, event_type: str) -> RouteDecision | None:
    """Resolve the owning agent for an event. Returns `None` for an unmapped entity — a typed
    'no route' the caller records as processed, never a silent drop."""
    return _ROUTES.get(entity)


def known_entities() -> frozenset[str]:
    return frozenset(_ROUTES)
