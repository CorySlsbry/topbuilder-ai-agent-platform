"""Action ownership map (PURE — no DB, no IO).

Which agent OWNS each gated action KIND. The owning agent — not the propose-time ``agent`` field,
which the proposer supplies and can differ from the kind — is the authority for every department-scope
check on an action: at propose time (routes_actions) AND at approve / execute / undo / list time (the
gate, ADR 0007 + per-employee approval). Kept DB-free so both the route layer and the service layer
import it without a circular import.
"""
from __future__ import annotations

# Each gated action KIND belongs to one owning agent. The caller must have access to that owning agent
# (derived from the KIND), not merely the agent self-declared in the payload, which can differ from the
# kind — e.g. a payload could claim agent='collections' on kind='payroll_adjustment' (a Workforce pay
# write). Authorizing against the OWNING agent closes that cross-department escalation.
KIND_OWNER: dict[str, str] = {
    "payroll_adjustment": "workforce",
    "send_dunning_email": "collections", "send_dunning_sms": "collections", "place_dunning_call": "collections",
    "update_pricebook_item": "pricebook",
    "create_ap_draft": "documents", "register_warranty": "documents",
    "file_document": "documents", "request_signature": "documents",
    "book_appointment": "booking", "create_estimate": "booking",
    # Ads-CRM (ADR 0009) — all five ad-platform writes are owned by the operator-only 'ads' agent.
    "ads.create_campaign": "ads", "ads.update_budget": "ads", "ads.activate_campaign": "ads",
    "ads.pause_campaign": "ads", "ads.sync_conversion": "ads",
    # email/seo kinds are operator-only surfaces gated elsewhere; unmapped -> fall back to payload.agent.
}


def derive_owning_agent(kind: str, agent: str) -> str:
    """The agent that OWNS this action kind (authoritative for department authorization). Falls back to
    the stored/declared ``agent`` only for kinds with no fixed owner."""
    return KIND_OWNER.get(kind, agent)
