"""Google Ads Authorization-Code token exchange WITH PKCE (operator-scoped ad-platform OAuth).

A platform operator connects the Google Ads account in Google's consent screen; Google redirects back
to our ``/v1/integrations/google_ads/callback`` with a one-time ``code``. This module exchanges that
code at the token endpoint (``https://oauth2.googleapis.com/token``, ``grant_type=authorization_code``)
for an ``access_token`` + (with ``access_type=offline``) a long-lived ``refresh_token``.

It mirrors :mod:`app.integrations.google.google_oauth` exactly — same endpoints shape, same
``access_type=offline`` + ``prompt=consent`` (Google omits the refresh_token on silent re-consent
otherwise) — and ADDS PKCE (RFC 7636): the authorize URL carries a ``code_challenge`` (S256) and the
token exchange sends the matching ``code_verifier``. Per the Ads-CRM spec (ADR 0009 §3) this closes the
open-state gap the older providers defer; the caller binds ``state`` + the verifier to a server session.

Fail-closed: a non-2xx response raises (``raise_for_status``). Secrets (client_id/secret/code/verifier/
tokens) flow only through the request body and the returned dict — this module never logs them.
"""
from __future__ import annotations

import base64
import hashlib
import secrets
from typing import Any

import httpx

from app.config import Settings


def _scope_list(settings: Settings) -> list[str]:
    """The space-delimited GOOGLE_ADS_SCOPES config, split into a clean list (empty entries dropped).

    Google Ads scopes are space-delimited like Google Workspace (the default is the single
    ``https://www.googleapis.com/auth/adwords`` scope).
    """
    return [s.strip() for s in (settings.google_ads_scopes or "").split() if s.strip()]


def generate_pkce_pair() -> tuple[str, str]:
    """Mint a fresh PKCE (verifier, challenge) pair (RFC 7636, S256).

    The ``code_verifier`` is a high-entropy URL-safe token; the ``code_challenge`` is the
    base64url(no-pad) of its SHA-256. The verifier is kept server-side (bound to the session) and the
    challenge goes on the authorize URL. Returned as ``(verifier, challenge)`` so the caller stores the
    verifier and passes the challenge to :func:`build_authorize_url`.
    """
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def build_authorize_url(
    settings: Settings,
    *,
    state: str,
    code_challenge: str,
    scopes: list[str] | None = None,
) -> str:
    """Build the Google Ads authorize URL the SPA redirects the platform operator to.

    ``access_type=offline`` + ``prompt=consent`` are required for Google to return a refresh token on
    the FIRST and on RE-consent. ``code_challenge`` (+ ``code_challenge_method=S256``) is the PKCE
    binding — the matching verifier must be supplied to :func:`exchange_code`.
    """
    if not settings.google_ads_client_id:
        raise RuntimeError("GOOGLE_ADS_CLIENT_ID is not configured")
    if not settings.google_ads_redirect_uri:
        raise RuntimeError("GOOGLE_ADS_REDIRECT_URI is not configured")
    scope = " ".join(scopes if scopes is not None else _scope_list(settings))
    return httpx.URL(
        settings.google_ads_authorize_url,
        params={
            "response_type": "code",
            "client_id": settings.google_ads_client_id,
            "redirect_uri": settings.google_ads_redirect_uri,
            "scope": scope,
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        },
    ).__str__()


async def exchange_code(settings: Settings, *, code: str, code_verifier: str) -> dict[str, Any]:
    """Exchange an authorization code (+ PKCE verifier) for tokens. Raises on non-success (fail closed).

    Returns Google's token JSON: ``access_token``, ``refresh_token``, ``expires_in``, ``scope``, etc.
    The ``code_verifier`` proves possession of the matching ``code_challenge`` from the authorize step.
    """
    if not (settings.google_ads_client_id and settings.google_ads_client_secret):
        raise RuntimeError(
            "Google Ads OAuth requires GOOGLE_ADS_CLIENT_ID and GOOGLE_ADS_CLIENT_SECRET"
        )
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            settings.google_ads_token_url,
            data={
                "grant_type": "authorization_code",
                "client_id": settings.google_ads_client_id,
                "client_secret": settings.google_ads_client_secret,
                "code": code,
                "redirect_uri": settings.google_ads_redirect_uri,
                "code_verifier": code_verifier,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    resp.raise_for_status()
    return resp.json()


async def refresh_access_token(settings: Settings, *, refresh_token: str) -> dict[str, Any]:
    """Exchange a stored refresh token for a fresh access token (the live data path). Fail-closed.

    Google rotates refresh tokens infrequently; if the response carries a new ``refresh_token`` the
    caller MUST persist it. Returns Google's token JSON (``access_token``, ``expires_in``, ...).
    """
    if not (settings.google_ads_client_id and settings.google_ads_client_secret):
        raise RuntimeError(
            "Google Ads OAuth requires GOOGLE_ADS_CLIENT_ID and GOOGLE_ADS_CLIENT_SECRET"
        )
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            settings.google_ads_token_url,
            data={
                "grant_type": "refresh_token",
                "client_id": settings.google_ads_client_id,
                "client_secret": settings.google_ads_client_secret,
                "refresh_token": refresh_token,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    resp.raise_for_status()
    return resp.json()
