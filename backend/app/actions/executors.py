"""Action executors (ADR 0007): a `kind` -> the actual write to a system of record.

Fixture mode returns a deterministic synthetic confirmation so the whole approve->execute gate is
offline-testable (ADR 0003/0005); live mode performs the real write via the system-of-record adapter,
left as a typed, fail-closed skeleton until verified against a real tenant.
"""
from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable

from app.config import Settings

Executor = Callable[[dict, Settings], Awaitable[dict]]
UndoExecutor = Callable[[dict, dict, Settings], Awaitable[dict]]  # (params, prior_result, settings)


class ActionError(Exception):
    """Raised when an action cannot be executed (unknown/disabled kind, bad params, upstream failure)."""


async def _book_appointment(params: dict, settings: Settings) -> dict:
    intake_id = params.get("intake_id")
    if not intake_id:
        raise ActionError("book_appointment requires 'intake_id'")
    if settings.servicetitan_mode.lower() == "live":
        # POST the appointment to ServiceTitan via the live OAuth2 client (the human approval is already
        # recorded on the action). Typed skeleton — fail-closed until verified against a real tenant.
        raise ActionError(
            "live ServiceTitan booking write is not yet wired; implement against the ST "
            "Jobs/Appointments API behind the live adapter (ADR 0005/0007)."
        )
    # Fixture: deterministic confirmation, no external call, no randomness (stable for tests).
    return {
        "system": "servicetitan",
        "mode": "fixture",
        "external_ref": f"st-appt-{intake_id}",
        "intake_id": intake_id,
        "trade": params.get("trade"),
        "scheduled_for": params.get("proposed_date"),
        "status": "booked",
    }


async def _file_document(params: dict, settings: Settings) -> dict:
    doc_id = params.get("doc_id")
    if not doc_id:
        raise ActionError("file_document requires 'doc_id'")
    if settings.servicetitan_mode.lower() == "live":
        raise ActionError("live ServiceTitan document filing is not yet wired (attachments API).")
    return {
        "system": "servicetitan", "mode": "fixture", "external_ref": f"st-file-{doc_id}",
        "doc_id": doc_id, "customer_ref": params.get("customer_ref"),
        "filed_to": f"{params.get('department')}/{params.get('st_folder')}", "status": "filed",
    }


async def _request_signature(params: dict, settings: Settings) -> dict:
    doc_id = params.get("doc_id")
    if not doc_id:
        raise ActionError("request_signature requires 'doc_id'")
    if settings.servicetitan_mode.lower() == "live":
        raise ActionError("live e-signature request is not yet wired (e-sign provider).")
    return {
        "system": "esign", "mode": "fixture", "external_ref": f"esign-{doc_id}",
        "doc_id": doc_id, "customer_ref": params.get("customer_ref"), "status": "sent_for_signature",
    }


async def _create_estimate(params: dict, settings: Settings) -> dict:
    if settings.servicetitan_mode.lower() == "live":
        raise ActionError("live ServiceTitan estimate creation is not yet wired (Estimates API).")
    ref = params.get("job_ref") or "adhoc"
    total = params.get("total_cents") or 0
    return {
        "system": "servicetitan", "mode": "fixture", "external_ref": f"st-est-{ref}",
        "job_ref": params.get("job_ref"), "total_usd": round(total / 100, 2),
        "line_count": len(params.get("lines") or []), "status": "estimate_created",
    }


async def _send_email_reply(params: dict, settings: Settings) -> dict:
    email_id = params.get("email_id")
    if not email_id:
        raise ActionError("send_email_reply requires 'email_id'")
    if settings.email_mode.lower() == "live":
        raise ActionError("live email send is not yet wired; implement via the Gmail/Workspace adapter.")
    return {
        "system": "email", "mode": "fixture", "external_ref": f"em-reply-{email_id}",
        "email_id": email_id, "draft_subject": params.get("draft_subject"), "status": "sent",
    }


async def _delete_emails(params: dict, settings: Settings) -> dict:
    ids = params.get("email_ids") or []
    if not ids:
        raise ActionError("delete_emails requires 'email_ids'")
    if settings.email_mode.lower() == "live":
        raise ActionError("live email trash is not yet wired; implement via the Gmail/Workspace adapter.")
    return {
        "system": "email", "mode": "fixture", "external_ref": f"em-trash-{len(ids)}",
        "email_ids": ids, "deleted_count": len(ids), "status": "trashed",
    }


async def _rewrite_workflow(params: dict, settings: Settings) -> dict:
    workflow_id = params.get("workflow_id")
    if not workflow_id:
        raise ActionError("rewrite_workflow requires 'workflow_id'")
    if settings.email_mode.lower() == "live":
        raise ActionError("live workflow rewrite is not yet wired (sequence provider adapter).")
    return {
        "system": "email", "mode": "fixture", "external_ref": f"em-wf-{workflow_id}",
        "workflow_id": workflow_id, "new_subject": params.get("subject"), "status": "rewritten",
    }


async def _payroll_adjustment(params: dict, settings: Settings) -> dict:
    """Post a manual payroll adjustment for a worker whose pay-form hours diverged from the clock.

    Mirrors the client's manual flow (job actions -> payroll adjustment, keyed by hand): the human
    approval is already recorded on the action; this performs the write. Fixture mode returns a
    deterministic confirmation; live mode fails closed until the ST payroll-adjustment write is
    verified against a real tenant (ADR 0005/0007) — never fabricate a write.
    """
    worker_id = params.get("worker_id")
    if not worker_id:
        raise ActionError("payroll_adjustment requires 'worker_id'")
    if settings.servicetitan_mode.lower() == "live":
        # Build the real ST request to PROVE the field mapping is correct (claimed-vs-clocked gap ->
        # hours from the verified clock, postedOn = period_end, memo quoting the gap), then fail closed:
        # the HTTP send is intentionally NOT wired until verified against a real tenant (ADR 0005/0007).
        # Never POST, never fabricate a success.
        from app.integrations.servicetitan.payroll_writeback import (
            build_payroll_adjustment_request,
        )

        path, _body = build_payroll_adjustment_request(params)
        raise ActionError(
            f"live ServiceTitan payroll adjustment request is assembled and ready (POST {path}) but "
            "the HTTP send is not yet wired; implement against the ST Payroll adjustments API behind "
            "the live adapter (ADR 0005/0007)."
        )
    period_start = params.get("period_start")
    period_end = params.get("period_end")
    return {
        "system": "servicetitan",
        "mode": "fixture",
        "external_ref": f"st-payadj-{worker_id}-{period_start}",
        "worker_id": worker_id,
        "worker_name": params.get("worker_name"),
        "period": [period_start, period_end],
        "claimed_hours": params.get("claimed_hours"),
        "computed_hours": params.get("computed_hours"),
        "hours_discrepancy": params.get("hours_discrepancy"),
        "status": "adjustment_posted",
    }


async def _create_ap_draft(params: dict, settings: Settings) -> dict:
    """Create an A/P draft entry for a matched vendor bill + attach it to the job (Alex's PO/AP lane).

    The agent matched a printed job number on an emailed bill to an open ServiceTitan job and proposed
    this A/P entry; the human approval is already recorded on the action. Fixture mode returns a
    deterministic confirmation; live mode fails closed until the ST/QBO A/P write is verified against a
    real tenant (ADR 0005/0007) — never fabricate a write.
    """
    bill_id = params.get("bill_id")
    job_ref = params.get("job_ref")
    if not bill_id:
        raise ActionError("create_ap_draft requires 'bill_id'")
    if not job_ref:
        raise ActionError("create_ap_draft requires 'job_ref' (the matched job number)")
    if settings.servicetitan_mode.lower() == "live":
        raise ActionError(
            "live A/P draft creation is not yet wired; implement against the ServiceTitan "
            "Accounting (bills/AP) API + job attachment behind the live adapter (ADR 0005/0007)."
        )
    amount_cents = int(params.get("amount_cents") or 0)
    return {
        "system": "servicetitan", "mode": "fixture", "external_ref": f"st-ap-{bill_id}",
        "bill_id": bill_id, "vendor": params.get("vendor"), "doc_number": params.get("doc_number"),
        "job_ref": job_ref, "amount_usd": round(amount_cents / 100, 2), "status": "ap_drafted",
    }


async def _register_warranty(params: dict, settings: Settings) -> dict:
    """Register installed equipment on the vendor's warranty portal, then write it back to the job.

    HARD SAFETY RULE (Alex): the agent NEVER signs in. Registration requires a HUMAN-established vendor
    session — a person logs into the vendor portal first and hands the agent an opaque session handle
    (`human_login_token`). This executor carries NO credentials: if no human session is present it
    REFUSES. Fixture mode returns a deterministic confirmation; live mode fails closed until the
    provider-agnostic vendor-portal automation is verified (ADR 0005/0007).
    """
    equipment_id = params.get("equipment_id")
    if not equipment_id:
        raise ActionError("register_warranty requires 'equipment_id'")
    # The never-sign-in rule, enforced at the write boundary: no human session => refuse.
    human_session = params.get("human_login_token")
    if not human_session:
        raise ActionError(
            "register_warranty refuses to run without a human-established vendor session: the agent "
            "never signs into a vendor portal itself. A person must sign in and pass a "
            "'human_login_token'."
        )
    if settings.servicetitan_mode.lower() == "live":
        raise ActionError(
            "live warranty registration is not yet wired; implement the provider-agnostic vendor-portal "
            "automation (drive the human-authenticated session) + ST job write-back (ADR 0005/0007)."
        )
    return {
        "system": "vendor_portal", "mode": "fixture",
        "external_ref": f"warranty-{equipment_id}",
        "equipment_id": equipment_id, "job_ref": params.get("job_ref"),
        "portal": params.get("portal"), "field_count": len(params.get("fields") or {}),
        "status": "registered",
    }


async def _publish_blog_post(params: dict, settings: Settings) -> dict:
    keyword = params.get("keyword")
    if not keyword:
        raise ActionError("publish_blog_post requires 'keyword'")
    if settings.seo_mode.lower() == "live":
        raise ActionError("live blog publish is not yet wired (CMS adapter).")
    slug = "-".join(str(keyword).lower().split())[:64]
    return {
        "system": "cms", "mode": "fixture", "external_ref": f"post-{slug}",
        "keyword": keyword, "title": params.get("title"), "status": "published",
    }


async def _post_comment(params: dict, settings: Settings) -> dict:
    url = params.get("url")
    if not url:
        raise ActionError("post_comment requires 'url'")
    if settings.seo_mode.lower() == "live":
        raise ActionError("live comment posting is not yet wired (platform adapters; owner-approved only).")
    # sha256, not hash(): Python's hash() is salted per-process, so the "deterministic" fixture
    # ref would change across restarts and break idempotency comparison.
    ref = hashlib.sha256(str(url).encode()).hexdigest()[:10]
    return {
        "system": params.get("platform") or "community", "mode": "fixture",
        "external_ref": f"comment-{ref}", "url": url, "status": "posted",
    }


async def _send_outreach_email(params: dict, settings: Settings) -> dict:
    """Send ONE outreach email to a CRM contact via Resend, on the dedicated sending subdomain.

    Defense-in-depth, PARAM-TRUST-SAFE: every compliance fact (consent, country, bounce,
    unsubscribe, suppression) is resolved from the AUTHORITATIVE store (outreach_contacts +
    email_suppression, migration 0027) — proposer-supplied flags in params are IGNORED, so a forged
    `consent=true` or an omitted country can never bypass the CASL/GDPR hold; an unresolvable
    contact is HELD (fail-safe). The warm-up daily cap is enforced against the outreach_sends
    ledger and every successful send is recorded to it. Fixture mode returns a deterministic
    confirmation; live mode sends via Resend and fails closed without RESEND_API_KEY.
    """
    import datetime as _dt
    import uuid as _uuid

    from app.db import tenant_session
    from app.outreach.compliance import (
        ALLOW,
        OutreachMessage,
        authoritative_send_decision,
        can_spam_issues,
        warmup_daily_cap,
    )
    from app.repositories import outreach as outreach_repo

    to_email = (params.get("to_email") or "").strip()
    contact_id = params.get("contact_id")
    if not to_email:
        raise ActionError("send_outreach_email requires 'to_email'")
    if not contact_id:
        raise ActionError("send_outreach_email requires 'contact_id' (the authoritative contact record)")
    tenant_raw = params.get("_tenant_id")  # injected server-side at execute; never proposer-controlled
    if not tenant_raw:
        raise ActionError("send_outreach_email held: no tenant context (missing server-injected _tenant_id)")

    msg = OutreachMessage(
        subject=params.get("subject", ""),
        html=params.get("html", ""),
        text=params.get("text", ""),
        from_email=settings.outreach_from_email,
        from_name=settings.outreach_from_name,
        unsubscribe_url=params.get("unsubscribe_url"),
        physical_address=settings.outreach_physical_address or None,
    )
    issues = can_spam_issues(msg)
    if issues:
        raise ActionError("send_outreach_email blocked (CAN-SPAM): " + ",".join(issues))
    # The unsubscribe link must live on OUR configured base — an off-domain (attacker-supplied)
    # URL passes the presence check but breaks the actual CAN-SPAM mechanism. Refuse it.
    if not str(msg.unsubscribe_url or "").startswith(settings.outreach_unsubscribe_base_url):
        raise ActionError(
            f"send_outreach_email blocked: unsubscribe_url must be on {settings.outreach_unsubscribe_base_url}"
        )

    email_normalized = to_email.lower()
    subdomain = settings.outreach_from_email.split("@", 1)[-1].lower()
    async with tenant_session(_uuid.UUID(str(tenant_raw))) as session:
        resolved = await outreach_repo.resolve_contact(session, email_normalized=email_normalized)
        suppressed = await outreach_repo.is_suppressed(session, email_normalized=email_normalized)
        sent_today = await outreach_repo.sent_today_count(session, subdomain=subdomain)
        first_send = await outreach_repo.first_send_at(session, subdomain=subdomain)

    decision = authoritative_send_decision(
        resolved,
        contact_id=str(contact_id),
        email=to_email,
        suppressed=suppressed,
        consent_required_countries=settings.outreach_consent_required_country_set,
        blocked_countries=settings.outreach_blocked_country_set,
    )
    if decision.decision != ALLOW:
        raise ActionError(f"send_outreach_email held: {decision.reason}")

    age_days = 0
    if first_send is not None:
        now = _dt.datetime.now(_dt.timezone.utc)
        first = first_send if first_send.tzinfo else first_send.replace(tzinfo=_dt.timezone.utc)
        age_days = max(0, (now - first).days)
    cap = warmup_daily_cap(
        age_days,
        start=settings.outreach_warmup_start,
        growth=settings.outreach_warmup_growth,
        ceiling=settings.outreach_daily_cap,
    )
    if sent_today >= cap:
        raise ActionError(
            f"send_outreach_email held: warm-up daily cap reached ({sent_today}/{cap} on {subdomain})"
        )

    from app.integrations.email_send.client import get_email_send_client

    client = get_email_send_client(settings=settings)
    headers = {
        "List-Unsubscribe": f"<{msg.unsubscribe_url}>",
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
    }
    res = await client.send(
        to=to_email,
        from_email=msg.from_email,
        from_name=msg.from_name,
        reply_to=settings.outreach_reply_to,
        subject=msg.subject,
        html=msg.html,
        text=msg.text,
        headers=headers,
    )
    # Ledger the send (the warm-up meter + audit). Best-effort: a ledger failure must not un-send
    # the email, but it is loud in the result so the operator sees a metering gap.
    ledger = "recorded"
    try:
        async with tenant_session(_uuid.UUID(str(tenant_raw))) as session:
            await outreach_repo.record_send(
                session, email_normalized=email_normalized, subdomain=subdomain,
                action_id=_uuid.UUID(str(params["_action_id"])) if params.get("_action_id") else None,
            )
    except Exception:
        ledger = "ledger_failed"
    return {
        "system": "resend",
        "mode": res.get("mode"),
        "external_ref": res.get("external_ref"),
        "to": to_email,
        "contact_id": str(contact_id),
        "subject": msg.subject,
        "status": res.get("status", "sent"),
        "send_ledger": ledger,
    }


# Imported here (not at top of file) so the agent executor packages can import this module's
# ActionError without a circular import at load time.
from app.agents.ads import executors as _ads_executors  # noqa: E402
from app.agents.collections import executors as _collections_executors  # noqa: E402
from app.agents.pricebook import executors as _pricebook_executors  # noqa: E402

EXECUTORS: dict[str, Executor] = {
    "book_appointment": _book_appointment,
    "file_document": _file_document,
    "request_signature": _request_signature,
    "create_estimate": _create_estimate,
    "send_email_reply": _send_email_reply,
    "delete_emails": _delete_emails,
    "rewrite_workflow": _rewrite_workflow,
    "publish_blog_post": _publish_blog_post,
    "post_comment": _post_comment,
    "payroll_adjustment": _payroll_adjustment,
    "create_ap_draft": _create_ap_draft,
    "register_warranty": _register_warranty,
    "send_dunning_email": _collections_executors.send_dunning_email,
    "send_dunning_sms": _collections_executors.send_dunning_sms,
    "place_dunning_call": _collections_executors.place_dunning_call,
    "update_pricebook_item": _pricebook_executors.update_pricebook_item,
    "send_outreach_email": _send_outreach_email,
    # Ads-CRM (ADR 0009) — operator-only ad-platform writes (Meta / Google).
    "ads.create_campaign": _ads_executors.create_campaign,
    "ads.update_budget": _ads_executors.update_budget,
    "ads.activate_campaign": _ads_executors.activate_campaign,
    "ads.pause_campaign": _ads_executors.pause_campaign,
    "ads.sync_conversion": _ads_executors.sync_conversion,
}


# --------------------------------------------------------------------------------------------
# Undo / compensation (for autonomous-with-undo, ADR 0007)
# --------------------------------------------------------------------------------------------
async def _undo_book_appointment(params: dict, result: dict, settings: Settings) -> dict:
    return {
        "system": "servicetitan",
        "external_ref": result.get("external_ref"),
        "status": "canceled",
    }


async def _undo_file_document(params: dict, result: dict, settings: Settings) -> dict:
    return {"system": "servicetitan", "external_ref": result.get("external_ref"), "status": "unfiled"}


async def _undo_request_signature(params: dict, result: dict, settings: Settings) -> dict:
    return {"system": "esign", "external_ref": result.get("external_ref"), "status": "voided"}


async def _undo_create_estimate(params: dict, result: dict, settings: Settings) -> dict:
    return {"system": "servicetitan", "external_ref": result.get("external_ref"), "status": "estimate_voided"}


async def _undo_send_email_reply(params: dict, result: dict, settings: Settings) -> dict:
    # A sent email cannot be unsent; compensation = a follow-up retraction draft flagged for the owner.
    return {"system": "email", "external_ref": result.get("external_ref"), "status": "retraction_drafted"}


async def _undo_delete_emails(params: dict, result: dict, settings: Settings) -> dict:
    return {
        "system": "email", "external_ref": result.get("external_ref"),
        "restored_count": result.get("deleted_count", 0), "status": "restored_from_trash",
    }


async def _undo_rewrite_workflow(params: dict, result: dict, settings: Settings) -> dict:
    return {"system": "email", "external_ref": result.get("external_ref"), "status": "previous_copy_restored"}


async def _undo_publish_blog_post(params: dict, result: dict, settings: Settings) -> dict:
    return {"system": "cms", "external_ref": result.get("external_ref"), "status": "unpublished"}


async def _undo_post_comment(params: dict, result: dict, settings: Settings) -> dict:
    return {"system": result.get("system", "community"), "external_ref": result.get("external_ref"), "status": "comment_deleted"}


async def _undo_create_ap_draft(params: dict, result: dict, settings: Settings) -> dict:
    # Void the drafted A/P entry (a draft can be deleted/voided before it posts).
    return {"system": "servicetitan", "external_ref": result.get("external_ref"), "status": "ap_voided"}


async def _undo_register_warranty(params: dict, result: dict, settings: Settings) -> dict:
    # Compensation = flag the vendor registration for cancellation (some portals can't auto-cancel).
    return {
        "system": "vendor_portal", "external_ref": result.get("external_ref"),
        "equipment_id": result.get("equipment_id") or params.get("equipment_id"),
        "status": "registration_cancellation_requested",
    }


async def _undo_send_outreach_email(params: dict, result: dict, settings: Settings) -> dict:
    # A sent email cannot be unsent; compensation = ACTUALLY suppress the recipient (durably, so the
    # authority store's is_suppressed() blocks every future send) and flag a retraction for the owner.
    import uuid as _uuid

    from app.db import tenant_session
    from app.repositories import outreach as outreach_repo

    to_email = result.get("to") or params.get("to_email")
    tenant_raw = params.get("_tenant_id")
    suppressed = False
    if to_email and tenant_raw:
        try:
            async with tenant_session(_uuid.UUID(str(tenant_raw))) as session:
                await outreach_repo.add_suppression(
                    session, email_normalized=str(to_email).strip().lower(), reason="undo_retraction",
                )
            suppressed = True
        except Exception:
            suppressed = False  # loud in the payload, but never fail the undo
    return {
        "system": "resend",
        "external_ref": result.get("external_ref"),
        "to": to_email,
        "status": "recipient_suppressed_retraction_flagged" if suppressed else "retraction_flagged_suppression_failed",
    }


async def _undo_payroll_adjustment(params: dict, result: dict, settings: Settings) -> dict:
    # Reverse the posted adjustment (the payroll system supports voiding/reversing an adjustment).
    return {
        "system": "servicetitan",
        "external_ref": result.get("external_ref"),
        "worker_id": result.get("worker_id") or params.get("worker_id"),
        "status": "adjustment_reversed",
    }


UNDO_EXECUTORS: dict[str, "UndoExecutor"] = {
    "book_appointment": _undo_book_appointment,
    "file_document": _undo_file_document,
    "request_signature": _undo_request_signature,
    "create_estimate": _undo_create_estimate,
    "send_email_reply": _undo_send_email_reply,
    "delete_emails": _undo_delete_emails,
    "rewrite_workflow": _undo_rewrite_workflow,
    "publish_blog_post": _undo_publish_blog_post,
    "post_comment": _undo_post_comment,
    "payroll_adjustment": _undo_payroll_adjustment,
    "create_ap_draft": _undo_create_ap_draft,
    "register_warranty": _undo_register_warranty,
    "send_dunning_email": _collections_executors.undo_send_dunning_email,
    "send_dunning_sms": _collections_executors.undo_send_dunning_sms,
    "place_dunning_call": _collections_executors.undo_place_dunning_call,
    "update_pricebook_item": _pricebook_executors.undo_update_pricebook_item,
    "send_outreach_email": _undo_send_outreach_email,
    # Ads-CRM (ADR 0009) — compensations for the ad-platform writes.
    "ads.create_campaign": _ads_executors.undo_create_campaign,
    "ads.update_budget": _ads_executors.undo_update_budget,
    "ads.activate_campaign": _ads_executors.undo_activate_campaign,
    "ads.pause_campaign": _ads_executors.undo_pause_campaign,
    "ads.sync_conversion": _ads_executors.undo_sync_conversion,
}


def is_undoable(kind: str) -> bool:
    return kind in UNDO_EXECUTORS


async def undo(kind: str, params: dict, result: dict, settings: Settings) -> dict:
    fn = UNDO_EXECUTORS.get(kind)
    if fn is None:
        raise ActionError(f"no undo executor registered for kind '{kind}'")
    return await fn(params, result, settings)


def is_executable_kind(kind: str, settings: Settings) -> bool:
    """A kind can execute only if it has an executor AND is on the tenant's allowlist."""
    return kind in EXECUTORS and kind in settings.actions_allowed_kind_set


async def execute(kind: str, params: dict, settings: Settings) -> dict:
    executor = EXECUTORS.get(kind)
    if executor is None:
        raise ActionError(f"no executor registered for kind '{kind}'")
    return await executor(params, settings)
