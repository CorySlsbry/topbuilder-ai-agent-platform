"""Meta (Facebook) Authorization-Code + PKCE token exchange — OPERATOR ad-platform OAuth (ADR 0009).

The platform OPERATOR (not a customer tenant) connects the agency's Meta ad account: the SPA redirects
to Meta's authorize dialog, Meta redirects back to ``/v1/integrations/meta/callback`` with a one-time
``code``, and we exchange it for an ``access_token``. This mirrors ``construction/procore_oauth.py``
exactly, ADDING **PKCE** (``code_challenge`` S256 on the authorize URL, ``code_verifier`` on the
exchange) — the verifier never leaves our server, so an intercepted ``code`` alone is useless. The
short-lived user token is then upgraded to a ~60-day long-lived token via :func:`exchange_long_lived_token`.

Fail-closed: a non-2xx response raises (``raise_for_status``). Secrets (app secret, ``code``, the
``code_verifier``, and the returned tokens) flow ONLY through the request body and the returned dict —
this module never logs them. The returned token is stored encrypted in the operator credential vault
(``operator_credentials``, migration 0023), never in app config.
"""
from __future__ import annotations

import base64
import hashlib
import secrets
from typing import Any

import httpx

from app.config import Settings


def _scope_str(settings: Settings) -> str:
    """The configured Meta scopes as a single comma-delimited string (Meta uses commas, not spaces)."""
    return ",".join(s.strip() for s in (settings.meta_scopes or "").split(",") if s.strip())


# ── PKCE helpers (RFC 7636) ───────────────────────────────────────────────────────────────────────
def generate_code_verifier(n_bytes: int = 64) -> str:
    """A high-entropy, URL-safe PKCE ``code_verifier`` (RFC 7636 §4.1: 43-128 unreserved chars).

    ``token_urlsafe(64)`` yields ~86 base64url chars (all unreserved), comfortably within the spec.
    Generate this when starting the flow, stash it in the server-side session keyed by ``state``, and
    pass it back into :func:`exchange_code`.
    """
    return secrets.token_urlsafe(n_bytes)


def code_challenge_from_verifier(code_verifier: str) -> str:
    """Derive the S256 ``code_challenge``: base64url(sha256(verifier)) with the ``=`` padding stripped."""
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def build_authorize_url(settings: Settings, *, state: str, code_challenge: str) -> str:
    """Build the Meta authorize URL the SPA redirects the operator to (PKCE S256).

    ``state`` ties the round-trip to a server-side session (CSRF), and ``code_challenge`` is the S256
    hash of the verifier kept server-side — Meta echoes neither secret back in the redirect.
    """
    if not settings.meta_app_id:
        raise RuntimeError("META_APP_ID is not configured")
    if not settings.meta_redirect_uri:
        raise RuntimeError("META_REDIRECT_URI is not configured")
    return httpx.URL(
        settings.meta_authorize_url,
        params={
            "response_type": "code",
            "client_id": settings.meta_app_id,
            "redirect_uri": settings.meta_redirect_uri,
            "scope": _scope_str(settings),
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        },
    ).__str__()


async def exchange_code(settings: Settings, *, code: str, code_verifier: str) -> dict[str, Any]:
    """Exchange an authorization code (+ PKCE verifier) for a short-lived token. Fail-closed.

    Returns Meta's token JSON: ``access_token``, ``token_type``, ``expires_in``, etc. Raises on any
    non-2xx. The ``code`` and ``code_verifier`` are secrets and are NEVER logged.
    """
    if not (settings.meta_app_id and settings.meta_app_secret):
        raise RuntimeError("Meta OAuth requires META_APP_ID and META_APP_SECRET")
    if not settings.meta_redirect_uri:
        raise RuntimeError("META_REDIRECT_URI is not configured")
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            settings.meta_token_url,
            data={
                "grant_type": "authorization_code",
                "client_id": settings.meta_app_id,
                "client_secret": settings.meta_app_secret,
                "redirect_uri": settings.meta_redirect_uri,
                "code": code,
                "code_verifier": code_verifier,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    resp.raise_for_status()
    return resp.json()


async def exchange_long_lived_token(settings: Settings, *, short_lived_token: str) -> dict[str, Any]:
    """Upgrade a short-lived user token to a ~60-day long-lived token. Fail-closed.

    Meta's long-lived exchange is ``grant_type=fb_exchange_token`` on the same token endpoint; the
    returned ``access_token`` (with a longer ``expires_in``) is what we encrypt into the operator
    vault. Raises on any non-2xx; the token is a secret and is NEVER logged.
    """
    if not (settings.meta_app_id and settings.meta_app_secret):
        raise RuntimeError("Meta OAuth requires META_APP_ID and META_APP_SECRET")
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            settings.meta_token_url,
            params={
                "grant_type": "fb_exchange_token",
                "client_id": settings.meta_app_id,
                "client_secret": settings.meta_app_secret,
                "fb_exchange_token": short_lived_token,
            },
        )
    resp.raise_for_status()
    return resp.json()
