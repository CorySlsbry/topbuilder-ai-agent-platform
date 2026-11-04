"""Google Authorization-Code token exchange (per-customer Drive / Sheets OAuth).

The customer admin grants access in Google's consent screen; Google redirects back to our
``/v1/integrations/google/callback`` with a one-time ``code``. This module exchanges that code at the
token endpoint (``https://oauth2.googleapis.com/token``, ``grant_type=authorization_code``) for an
``access_token`` + (with ``access_type=offline``) a long-lived ``refresh_token`` — mirroring the
Procore flow exactly; the differences are only the endpoints, the scopes, and the extra
``access_type=offline`` + ``prompt=consent`` params Google needs to return a refresh token.

Fail-closed: a non-2xx response raises. Secrets (client_id/secret/code/tokens) flow only through the
request body and the returned dict — this module never logs them.
"""
from __future__ import annotations

from typing import Any

import httpx

from app.config import Settings


def _scope_list(settings: Settings) -> list[str]:
    """The space-delimited GOOGLE_SCOPES config, split into a clean list (empty entries dropped)."""
    return [s.strip() for s in (settings.google_scopes or "").split() if s.strip()]


def build_authorize_url(settings: Settings, *, state: str, scopes: list[str] | None = None) -> str:
    """Build the Google authorize URL the SPA redirects the customer admin to.

    ``access_type=offline`` + ``prompt=consent`` are required for Google to return a refresh token on
    the FIRST and on RE-consent (Google omits the refresh_token on silent re-auth otherwise).
    """
    if not settings.google_client_id:
        raise RuntimeError("GOOGLE_CLIENT_ID is not configured")
    if not settings.google_redirect_uri:
        raise RuntimeError("GOOGLE_REDIRECT_URI is not configured")
    scope = " ".join(scopes if scopes is not None else _scope_list(settings))
    return httpx.URL(
        settings.google_authorize_url,
        params={
            "response_type": "code",
            "client_id": settings.google_client_id,
            "redirect_uri": settings.google_redirect_uri,
            "scope": scope,
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
        },
    ).__str__()


async def exchange_code(settings: Settings, *, code: str) -> dict[str, Any]:
    """Exchange an authorization code for tokens. Raises on any non-success (fail closed).

    Returns Google's token JSON: ``access_token``, ``refresh_token``, ``expires_in``, ``scope``, etc.
    """
    if not (settings.google_client_id and settings.google_client_secret):
        raise RuntimeError("Google OAuth requires GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET")
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            settings.google_token_url,
            data={
                "grant_type": "authorization_code",
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "code": code,
                "redirect_uri": settings.google_redirect_uri,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    resp.raise_for_status()
    return resp.json()


async def resolve_user_email(settings: Settings, *, access_token: str) -> str | None:
    """Best-effort: read the connecting user's email with the fresh access token.

    Returns the email string, or ``None`` if the call fails or returns nothing — storing the
    connection must not hinge on this convenience read (the connect flow stays robust even if the
    granted scopes don't include userinfo).
    """
    try:
        async with httpx.AsyncClient(base_url=settings.google_userinfo_url, timeout=30) as client:
            resp = await client.get(
                "",
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            )
            resp.raise_for_status()
            body = resp.json()
    except Exception:  # noqa: BLE001 — a convenience read; never break the connect flow on it
        return None
    if isinstance(body, dict):
        email = body.get("email")
        if isinstance(email, str) and email:
            return email
    return None
