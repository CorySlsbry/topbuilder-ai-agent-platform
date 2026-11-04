"""Tripwire order-capture surface (Stripe Payment Links).

  * POST /v1/tripwires/stripe/webhook — Stripe posts checkout.session.completed here. DARK (404)
    until `stripe_webhook_secret` is configured (mirrors the cron-gate style). The RAW body is read
    BEFORE any parsing (the signature covers the exact bytes); a bad signature is a 400. AFTER a
    valid signature the endpoint must NEVER 500 — Stripe retries any non-2xx, so a poison event
    resolves to 200 {'status': 'error-logged'} instead of a retry loop.
  * GET /v1/tripwires/orders — operator-only list: require_admin (admin + aal2/2FA) PLUS the
    PLATFORM_OPERATOR_EMAILS allowlist (the routes_crm two-line pattern), read via operator_session.
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status

from app.api.deps import require_admin
from app.config import get_settings
from app.db import operator_session
from app.repositories import tripwires as tripwires_repo
from app.security import Principal
from app.tripwires import service, stripe_sig

log = logging.getLogger("app.tripwires")

router = APIRouter(prefix="/v1/tripwires", tags=["tripwires"])


def _require_platform_operator(principal: Principal) -> None:
    """The caller's verified email must be on the platform-operator allowlist (fail-closed)."""
    allow = get_settings().platform_operator_email_set
    if not (principal.email and principal.email.strip().lower() in allow):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "tripwire orders are a platform-operator surface — your account is not an operator",
        )


@router.post("/stripe/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
) -> dict:
    settings = get_settings()
    if not settings.stripe_webhook_secret:
        # Endpoint dark until configured — an unsigned deployment must not accept anything.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "stripe webhook not configured")

    body = await request.body()  # RAW bytes FIRST — the signature covers exactly these
    if not stripe_sig.verify(body, stripe_signature or "", settings.stripe_webhook_secret):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid stripe signature")

    # Post-signature: NEVER 500. Stripe retries non-2xx deliveries, so a poison event must land as
    # a logged 200, not an infinite retry loop.
    try:
        event = json.loads(body or b"{}")
        if not isinstance(event, dict):
            event = {}
        if event.get("type") != "checkout.session.completed":
            return {"received": True}  # acknowledged, intentionally unhandled
        result = await service.handle_checkout_completed(event, settings)
        return {"received": True, **result}
    except Exception:
        log.exception("tripwire webhook: unhandled failure after a valid signature")
        return {"received": True, "status": "error-logged"}


@router.get("/orders")
async def list_orders(
    product_key: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    principal: Principal = Depends(require_admin),
) -> dict:
    """Operator-only: list tripwire orders, newest first, optionally filtered by product."""
    _require_platform_operator(principal)
    if product_key is not None and product_key not in service.ALLOWED_PRODUCT_KEYS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"product_key must be one of {sorted(service.ALLOWED_PRODUCT_KEYS)}",
        )
    async with operator_session() as session:
        rows = await tripwires_repo.list_orders(session, product_key=product_key, limit=limit)
    return {"orders": rows, "count": len(rows)}
