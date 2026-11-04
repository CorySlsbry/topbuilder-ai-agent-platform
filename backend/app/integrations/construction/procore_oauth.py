"""Procore Authorization-Code token exchange (per-customer production OAuth).

The customer installs the marketplace app and grants access; Procore redirects back to our
``/v1/integrations/procore/callback`` with a one-time ``code``. This module exchanges that code at
the token endpoint for an ``access_token`` + ``refresh_token`` (``grant_type=authorization_code``),
mirroring the refresh-token exchange already in ``procore_client.LiveProcoreClient`` and the dev
bootstrap script — the difference is only the grant type + the ``redirect_uri`` round-trip.

Fail-closed: a non-2xx response raises. Secrets (client_id/secret/code/tokens) flow only through the
request body and the returned dict — this module never logs them.
"""
from __future__ import annotations

from typing import Any

import httpx

from app.config import Settings


def build_authorize_url(settings: Settings, *, state: str) -> str:
    """Build the Procore authorize URL the SPA redirects the customer to."""
    if not settings.procore_client_id:
        raise RuntimeError("PROCORE_CLIENT_ID is not configured")
    if not settings.procore_redirect_uri:
        raise RuntimeError("PROCORE_REDIRECT_URI is not configured")
    return httpx.URL(
        settings.procore_authorize_url,
        params={
            "response_type": "code",
            "client_id": settings.procore_client_id,
            "redirect_uri": settings.procore_redirect_uri,
            "state": state,
        },
    ).__str__()


async def exchange_code(settings: Settings, *, code: str) -> dict[str, Any]:
    """Exchange an authorization code for tokens. Raises on any non-success (fail closed).

    Returns Procore's token JSON: ``access_token``, ``refresh_token``, ``expires_in``, etc.
    """
    if not (settings.procore_client_id and settings.procore_client_secret):
        raise RuntimeError("Procore OAuth requires PROCORE_CLIENT_ID and PROCORE_CLIENT_SECRET")
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            settings.procore_auth_url,
            data={
                "grant_type": "authorization_code",
                "client_id": settings.procore_client_id,
                "client_secret": settings.procore_client_secret,
                "code": code,
                "redirect_uri": settings.procore_redirect_uri,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    resp.raise_for_status()
    return resp.json()


async def resolve_company_id(settings: Settings, *, access_token: str) -> str | None:
    """Best-effort: read the customer's company id with the fresh access token.

    Returns the first company's id as a string, or ``None`` if the call fails or returns nothing —
    storing the connection must not hinge on this convenience read (the connect flow stays robust).
    """
    try:
        async with httpx.AsyncClient(base_url=settings.procore_base_url, timeout=30) as client:
            resp = await client.get(
                "/rest/v1.0/companies",
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            )
            resp.raise_for_status()
            body = resp.json()
    except Exception:  # noqa: BLE001 — a convenience read; never break the connect flow on it
        return None
    rows = body.get("data") if isinstance(body, dict) else body
    if isinstance(rows, list) and rows and isinstance(rows[0], dict) and rows[0].get("id") is not None:
        return str(rows[0]["id"])
    return None
