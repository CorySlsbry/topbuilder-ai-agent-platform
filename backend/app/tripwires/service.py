"""Tripwire order-capture service — the checkout.session.completed handler.

Pipeline (after the route has verified the Stripe signature):
    extract -> validate product_key -> record (idempotent) -> Slack alert -> CRM sync.

Contract (load-bearing): NOTHING in `handle_checkout_completed` raises to the caller. Every side
effect (Slack, CRM sync, crm_synced_at stamp) is best-effort try/except-logged — a Slack outage or
a CRM schema surprise can NEVER lose the order, and a persist failure resolves to a status dict the
route acks with a 200 (Stripe must not retry a poison event forever).

Idempotency: the repo's INSERT .. ON CONFLICT (stripe_session_id) DO NOTHING returns None for a
duplicate delivery, and ALL side effects are skipped (no double Slack ping, no double CRM touch).
"""
from __future__ import annotations

import logging
import uuid

from app.config import Settings
from app.tripwires import crm_sync

log = logging.getLogger("app.tripwires")

# The closed product catalog — mirrors the migration 0029 CHECK and the Stripe Payment Link
# metadata (product_key). Amounts are the expected charge; the recorded amount comes from Stripe.
PRODUCTS: dict[str, dict] = {
    "xray": {"label": "Margin Leakage X-Ray", "amount_cents": 9700},
    "collections_sprint": {"label": "Collections Sprint", "amount_cents": 9700},
    "scorecard_trial": {"label": "Scorecard Trial", "amount_cents": 2700},
}
ALLOWED_PRODUCT_KEYS: frozenset[str] = frozenset(PRODUCTS)

# Reuse the notifier's Slack transport (same httpx pattern, tiny + monkeypatchable). Fall back to
# a local mirror only if the notify module ever becomes unimportable.
try:
    from app.notify.notifier import _post_slack
except Exception:  # pragma: no cover — notifier is a first-party module; mirror just in case

    async def _post_slack(url: str, payload: dict) -> bool:
        import httpx

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
        return 200 <= resp.status_code < 300


# ── pure formatting ───────────────────────────────────────────────────────────────────────────────
def product_label(product_key: str) -> str:
    entry = PRODUCTS.get(product_key)
    return entry["label"] if entry else product_key


def _dollars(amount_cents: int | None) -> str:
    if amount_cents is None:
        return "$?"
    if amount_cents % 100 == 0:
        return f"${amount_cents // 100}"
    return f"${amount_cents / 100:.2f}"


def format_tripwire_slack(
    product_key: str, email: str | None, name: str | None, amount_cents: int | None
) -> dict:
    """Render the sale alert as a Slack webhook payload (top-level `text` fallback + rich blocks).
    Pure and total — never raises, even on an unexpected key (the handler validates upstream)."""
    label = product_label(product_key)
    amount = _dollars(amount_cents)
    if name and email:
        buyer = f"{name} <{email}>"
    else:
        buyer = email or name or "unknown buyer"
    headline = f":moneybag: Tripwire sale — {label}"
    line = f"{amount} from {buyer} — next: watch for their data handoff booking"
    return {
        "text": f"{headline}\n{line}",
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text", "text": f"💰 Tripwire sale — {label}", "emoji": True
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Amount:*\n{amount}"},
                    {"type": "mrkdwn", "text": f"*Buyer:*\n{buyer}"},
                ],
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "Next: watch for their data handoff booking."},
            },
        ],
    }


def _extract_session(event: dict) -> dict:
    """The checkout session object out of a Stripe event envelope. Total: always a dict."""
    obj = (event.get("data") or {}).get("object") or {}
    return obj if isinstance(obj, dict) else {}


def _extract_product_key(session_obj: dict) -> str | None:
    """metadata.product_key, falling back to the payment link's metadata when the session carries
    none (a Payment Link's metadata lands on the session only when configured; the expanded
    payment_link object is the fallback)."""
    metadata = session_obj.get("metadata") or {}
    key = metadata.get("product_key") if isinstance(metadata, dict) else None
    if key:
        return str(key)
    payment_link = session_obj.get("payment_link")
    if isinstance(payment_link, dict):
        link_meta = payment_link.get("metadata") or {}
        if isinstance(link_meta, dict) and link_meta.get("product_key"):
            return str(link_meta["product_key"])
    return None


def _as_id(value) -> str | None:
    """Stripe fields may arrive as a bare id or an expanded object — normalize to the id string."""
    if isinstance(value, dict):
        value = value.get("id")
    return str(value) if value else None


# ── impure seams (monkeypatchable in tests) ───────────────────────────────────────────────────────
async def _record_order(**kwargs) -> dict | None:
    """Insert the order under an operator session. None = duplicate stripe_session_id."""
    from app.db import operator_session
    from app.repositories import tripwires as tripwires_repo

    async with operator_session() as session:
        return await tripwires_repo.insert_order(session, **kwargs)


async def _mark_crm_synced(order_id: uuid.UUID) -> None:
    from app.db import operator_session
    from app.repositories import tripwires as tripwires_repo

    async with operator_session() as session:
        await tripwires_repo.mark_crm_synced(session, order_id)


# ── the handler ───────────────────────────────────────────────────────────────────────────────────
async def handle_checkout_completed(event: dict, settings: Settings) -> dict:
    """Process one checkout.session.completed event. NEVER raises (post-signature contract).

    Returns {status: 'recorded'|'duplicate'|'rejected'|'error', ...} with per-side-effect statuses
    ('sent'/'skipped'/'failed') so the webhook response is auditable in Stripe's delivery log.
    """
    obj = _extract_session(event)
    session_id = _as_id(obj.get("id"))
    if not session_id:
        log.warning("tripwire: event %s has no checkout session id — rejected", event.get("id"))
        return {"status": "rejected", "reason": "missing session id"}

    product_key = _extract_product_key(obj)
    if product_key not in ALLOWED_PRODUCT_KEYS:
        # Unknown/missing product_key: reject-log. We do NOT record arbitrary keys — the DB CHECK
        # mirrors ALLOWED_PRODUCT_KEYS, and a payment we can't attribute needs a human look anyway.
        log.warning(
            "tripwire: session %s carries unknown product_key %r — rejected (event %s)",
            session_id, product_key, event.get("id"),
        )
        return {"status": "rejected", "reason": f"unknown product_key {product_key!r}"}

    details = obj.get("customer_details") or {}
    email = details.get("email") if isinstance(details, dict) else None
    name = details.get("name") if isinstance(details, dict) else None
    amount_cents = obj.get("amount_total")
    amount_cents = int(amount_cents) if isinstance(amount_cents, (int, float)) else None

    try:
        row = await _record_order(
            product_key=product_key,
            stripe_session_id=session_id,
            stripe_payment_intent=_as_id(obj.get("payment_intent")),
            stripe_event_id=_as_id(event.get("id")),
            email=email,
            name=name,
            amount_cents=amount_cents,
            currency=str(obj.get("currency") or "usd"),
        )
    except Exception:
        log.exception("tripwire: persist failed for session %s", session_id)
        return {"status": "error", "reason": "persist failed (logged)"}

    if row is None:  # duplicate delivery — already recorded; skip ALL side effects
        log.info("tripwire: duplicate delivery for session %s — side effects skipped", session_id)
        return {"status": "duplicate", "product_key": product_key}

    # Slack alert — best-effort.
    slack_status = "skipped"
    webhook = getattr(settings, "slack_webhook_url", None)
    if webhook and getattr(settings, "tripwire_slack_enabled", True):
        try:
            ok = await _post_slack(
                webhook, format_tripwire_slack(product_key, email, name, amount_cents)
            )
            slack_status = "sent" if ok else "failed"
        except Exception:
            log.exception("tripwire: slack alert failed (order %s is safe)", row["id"])
            slack_status = "failed"

    # CRM sync — best-effort; stamp crm_synced_at only on success.
    crm_status = "skipped"
    try:
        synced = await crm_sync.sync_buyer(
            settings, email=email, name=name, product_key=product_key, amount_cents=amount_cents
        )
        if synced:
            crm_status = "synced"
            try:
                await _mark_crm_synced(row["id"])
            except Exception:
                log.exception("tripwire: mark_crm_synced failed for order %s", row["id"])
        elif getattr(settings, "crm_sync_db_url", None):
            crm_status = "failed"
    except Exception:
        log.exception("tripwire: crm sync failed (order %s is safe)", row["id"])
        crm_status = "failed"

    return {
        "status": "recorded",
        "order_id": str(row["id"]),
        "product_key": product_key,
        "slack": slack_status,
        "crm": crm_status,
    }
