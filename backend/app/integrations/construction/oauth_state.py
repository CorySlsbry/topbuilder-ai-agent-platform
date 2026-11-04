"""Stateless, tenant-bound OAuth `state` for the Procore Authorization-Code flow (CSRF defense).

The OAuth `state` round-trips through the customer's browser and Procore, so it must be unguessable
AND prove, on return, that the callback belongs to the same tenant that started the flow. We bind the
tenant_id into an HMAC-signed token (the same "MAC binds the tenant" pattern as the inbound-webhook
verifier in app/webhooks.py), so a `state` minted for tenant A cannot be replayed against tenant B,
and a stale `state` is rejected outside a short window. No server-side nonce store is required — the
signature itself is the proof — so it works across scaled-to-zero Cloud Run instances.

Layout (all ASCII, dot-separated, then the whole thing urlsafe-b64 so it survives a query string):
    <tenant_id>.<issued_at_epoch>.<random_nonce>.<hmac_sha256_hex>
where the MAC is computed over ``<tenant_id>.<issued_at>.<nonce>`` keyed by the app's signing secret.

Pure + dependency-free (only stdlib + the secret passed in) so it unit-tests without any infra.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import secrets
import uuid

STATE_TTL_SECONDS = 600  # a started OAuth flow must finish within 10 minutes
_NONCE_BYTES = 16  # 128-bit random nonce → unguessable even with a known tenant_id + timestamp


def _mac(tenant_id: str, issued_at: int, nonce: str, secret: str) -> str:
    material = f"{tenant_id}.{issued_at}.{nonce}".encode()
    return hmac.new(secret.encode(), material, hashlib.sha256).hexdigest()


def generate_state(tenant_id: str | uuid.UUID, secret: str, *, now: int, nonce: str | None = None) -> str:
    """Mint an unguessable, tenant-bound, time-stamped OAuth state token.

    `now` is the issuing epoch seconds (injected so the function stays pure/testable). `nonce` is only
    a test seam — production always uses a fresh CSPRNG value.
    """
    if not secret:
        raise ValueError("a signing secret is required to mint OAuth state")
    tid = str(tenant_id)
    nonce = nonce or secrets.token_urlsafe(_NONCE_BYTES)
    sig = _mac(tid, now, nonce, secret)
    raw = f"{tid}.{now}.{nonce}.{sig}".encode()
    return base64.urlsafe_b64encode(raw).decode()


def validate_state(state: str, secret: str, *, now: int, ttl: int = STATE_TTL_SECONDS) -> str:
    """Validate `state` and return the bound tenant_id (as a string).

    Fails closed (raises ``ValueError``) on a malformed token, a forged/mismatched MAC, or an expired
    token. The MAC is compared in constant time. The caller treats any ValueError as a 400/403.
    """
    if not secret:
        raise ValueError("a signing secret is required to validate OAuth state")
    if not state:
        raise ValueError("missing state")
    try:
        raw = base64.urlsafe_b64decode(state.encode()).decode()
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise ValueError("malformed state") from exc
    parts = raw.split(".")
    if len(parts) != 4:
        raise ValueError("malformed state")
    tid, issued_str, nonce, sig = parts
    try:
        issued_at = int(issued_str)
    except ValueError as exc:
        raise ValueError("malformed state") from exc
    expected = _mac(tid, issued_at, nonce, secret)
    if not hmac.compare_digest(expected, sig):
        raise ValueError("state signature mismatch (possible CSRF)")
    if now - issued_at > ttl or now < issued_at:
        raise ValueError("state expired — restart the connection")
    # Confirm the bound tenant is a well-formed UUID before the caller scopes a DB session to it.
    try:
        uuid.UUID(tid)
    except ValueError as exc:
        raise ValueError("malformed state tenant") from exc
    return tid
