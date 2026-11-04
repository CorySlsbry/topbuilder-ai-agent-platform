"""Inbound webhook signature verification (HMAC-SHA256, constant-time).

The signed material BINDS the tenant_id and a timestamp into the MAC (not just the body), so a
validly-signed event captured for tenant A cannot be replayed against tenant B's path, and a stale
capture is rejected outside a small skew window. The secret is resolved per-tenant at the call site.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac

MAX_SKEW_SECONDS = 300  # reject signed timestamps older/newer than this (replay window)


def verify_qbo_signature(body: bytes, signature: str | None, verifier_token: str) -> bool:
    """QuickBooks Online webhook verification: the `intuit-signature` header is the base64 of
    HMAC-SHA256(raw_body, verifier_token). Fails closed on any missing input or a bad MAC (ADR 0010).
    QBO binds no tenant/timestamp into the MAC, so the receiver resolves the tenant from the verified
    payload's `realmId` (never a session) and relies on the event_queue dedupe for replays."""
    if not verifier_token or not signature:
        return False
    expected = base64.b64encode(
        hmac.new(verifier_token.encode(), body, hashlib.sha256).digest()
    ).decode()
    try:
        return hmac.compare_digest(expected, signature)
    except (TypeError, binascii.Error):
        return False


def compute_signature(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def verify_signature(body: bytes, signature: str, secret: str) -> bool:
    """Legacy body-only verification (kept for back-compat; prefer verify_webhook)."""
    if not secret or not signature:
        return False
    return hmac.compare_digest(compute_signature(body, secret), signature)


def _signed_material(tenant_id: str, timestamp: str, body: bytes) -> bytes:
    return f"{tenant_id}.{timestamp}.".encode() + body


def webhook_signature(tenant_id: str, timestamp: str, body: bytes, secret: str) -> str:
    """The signature a sender must produce: HMAC over tenant_id.timestamp.body."""
    return compute_signature(_signed_material(tenant_id, timestamp, body), secret)


def verify_webhook(
    *, tenant_id: str, timestamp: str | None, body: bytes, signature: str | None, secret: str,
    now: float, max_skew: int = MAX_SKEW_SECONDS,
) -> tuple[bool, str]:
    """-> (ok, reason). Fails closed on any missing input, a stale/forged timestamp, or a bad MAC."""
    if not secret:
        return False, "webhook secret not configured"
    if not signature:
        return False, "missing signature"
    if not timestamp:
        return False, "missing timestamp"
    try:
        ts = float(timestamp)
    except (TypeError, ValueError):
        return False, "malformed timestamp"
    if abs(now - ts) > max_skew:
        return False, "timestamp outside the allowed window (replay?)"
    expected = webhook_signature(tenant_id, timestamp, body, secret)
    if not hmac.compare_digest(expected, signature):
        return False, "invalid signature"
    return True, ""
