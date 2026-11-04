"""QuickBooks Online Authorization-Code token exchange — Intuit's OWN OAuth 2.0 (no Zapier/iPaaS).

The customer admin grants access in Intuit's consent screen; Intuit redirects back to our
``/v1/integrations/quickbooks/callback`` with a one-time ``code``, the ``state`` we minted, AND a
``realmId`` (the QBO company id). This module builds the authorize URL and exchanges that code at
Intuit's token endpoint (``https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer``) for an
``access_token`` + ``refresh_token``.

Differences from the Procore/Google flows (the rest is identical):
  - the token exchange authenticates with **HTTP Basic** (``client_id:client_secret``), not a body
    ``client_secret`` — Intuit requires Basic auth on the bearer endpoint;
  - the authorize URL carries the QBO ``scope`` (``com.intuit.quickbooks.accounting`` by default);
  - ``realmId`` arrives on the callback (handled by the route, not here) and is the company id needed
    on every subsequent API call.

A ``refresh_access_token`` helper (``grant_type=refresh_token``) is provided for the live data path;
it matches the existing ``QuickBooksClient`` refresh exactly so the two never drift.

Fail-closed: a non-2xx response raises. Secrets (client_id/secret/code/tokens/realmId) flow only
through the request body/headers and the returned dict — this module never logs them.
"""
from __future__ import annotations

import base64
from typing import Any

import httpx

from app.config import Settings


def _scope_list(settings: Settings) -> list[str]:
    """The space-delimited QUICKBOOKS_SCOPES config, split into a clean list (empty entries dropped)."""
    return [s.strip() for s in (settings.quickbooks_scopes or "").split() if s.strip()]


def _basic_auth_header(settings: Settings) -> str:
    """``Basic base64(client_id:client_secret)`` — Intuit requires HTTP Basic on the token endpoint."""
    raw = f"{settings.quickbooks_client_id}:{settings.quickbooks_client_secret}".encode()
    return "Basic " + base64.b64encode(raw).decode()


def build_authorize_url(settings: Settings, *, state: str, scopes: list[str] | None = None) -> str:
    """Build the Intuit authorize URL the SPA redirects the customer admin to.

    Intuit redirects back with ``code``, ``state``, and ``realmId`` once the admin grants access.
    """
    if not settings.quickbooks_client_id:
        raise RuntimeError("QUICKBOOKS_CLIENT_ID is not configured")
    if not settings.quickbooks_redirect_uri:
        raise RuntimeError("QUICKBOOKS_REDIRECT_URI is not configured")
    scope = " ".join(scopes if scopes is not None else _scope_list(settings))
    return httpx.URL(
        settings.quickbooks_authorize_url,
        params={
            "client_id": settings.quickbooks_client_id,
            "response_type": "code",
            "scope": scope,
            "redirect_uri": settings.quickbooks_redirect_uri,
            "state": state,
        },
    ).__str__()


async def exchange_code(settings: Settings, *, code: str) -> dict[str, Any]:
    """Exchange an authorization code for tokens. Raises on any non-success (fail closed).

    Returns Intuit's token JSON: ``access_token``, ``refresh_token``, ``expires_in``,
    ``x_refresh_token_expires_in``, ``token_type``, etc.
    """
    if not (settings.quickbooks_client_id and settings.quickbooks_client_secret):
        raise RuntimeError("QuickBooks OAuth requires QUICKBOOKS_CLIENT_ID and QUICKBOOKS_CLIENT_SECRET")
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            settings.quickbooks_token_url,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.quickbooks_redirect_uri,
            },
            headers={
                "Authorization": _basic_auth_header(settings),
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
    resp.raise_for_status()
    return resp.json()


async def refresh_access_token(settings: Settings, *, refresh_token: str) -> dict[str, Any]:
    """Refresh an access token (``grant_type=refresh_token``) for the live data path. Fail closed.

    Returns Intuit's token JSON. Note: Intuit may ROTATE the refresh token on use — the caller should
    persist the returned ``refresh_token`` if it differs from the one sent.
    """
    if not (settings.quickbooks_client_id and settings.quickbooks_client_secret):
        raise RuntimeError("QuickBooks OAuth requires QUICKBOOKS_CLIENT_ID and QUICKBOOKS_CLIENT_SECRET")
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            settings.quickbooks_token_url,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            headers={
                "Authorization": _basic_auth_header(settings),
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
    resp.raise_for_status()
    return resp.json()
