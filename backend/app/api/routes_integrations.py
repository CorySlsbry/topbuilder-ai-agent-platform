"""Per-customer integration OAuth onboarding — Procore Authorization-Code flow.

A customer admin starts the connection (GET .../connect → an authorize URL the SPA redirects to),
grants access in Procore, and Procore redirects back to .../callback?code=&state=. We validate the
tenant-bound `state` (CSRF), exchange the code for tokens, and store the **refresh token** ENCRYPTED
in the same per-tenant AES-256-GCM credential vault that holds the ServiceTitan/QuickBooks secrets
(provider="procore"). The connection then drives the live Procore client (PROCORE_MODE=live).

Security posture (this is an authz surface):
  - admin-only (require_admin → role==admin AND aal2/2FA), exactly like the credential-vault writes.
  - `state` is an unguessable HMAC bound to the tenant — a callback can't be forged or cross-tenant.
  - secrets come only from settings/Secret Manager; the refresh token is encrypted at rest.
  - fail closed on every error; the code/secret/access/refresh tokens are NEVER logged or echoed.
  - PRE-PRODUCTION HARDENING (tracked): `state` is tenant-bound but not session/PKCE-bound, so an admin
    could be login-CSRF'd into connecting a Procore company to their OWN tenant (no cross-tenant hijack;
    gated by admin+aal2). Bind `state` to the initiating browser session (HttpOnly cookie) or add PKCE
    before treating stored Procore refresh tokens as fully-trusted production credentials.
"""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse

from app.api.deps import require_admin
from app.config import get_settings
from app.db import tenant_session
from app.integrations.construction import oauth_state, procore_oauth
from app.repositories import credentials, runs
from app.security import Principal

router = APIRouter(prefix="/v1/integrations", tags=["connections"])

_PROVIDER = "procore"


def _state_secret() -> str:
    """The signing key for OAuth state — the app's existing JWT secret (already a managed secret).

    Refused if it's the insecure placeholder, so a misconfigured deploy can't mint forgeable state.
    """
    secret = get_settings().jwt_secret
    if not secret or secret == "change-me":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OAuth not configured (JWT_SECRET unset)",
        )
    return secret


@router.get("/procore/connect")
async def procore_connect(principal: Principal = Depends(require_admin)) -> dict:
    """Begin the Procore connection. Returns the authorize URL for the SPA to redirect the admin to."""
    settings = get_settings()
    if not (settings.procore_client_id and settings.procore_redirect_uri):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Procore integration not configured (set PROCORE_CLIENT_ID / PROCORE_REDIRECT_URI)",
        )
    state = oauth_state.generate_state(
        principal.tenant_id, _state_secret(), now=int(time.time())
    )
    try:
        authorize_url = procore_oauth.build_authorize_url(settings, state=state)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return {"provider": _PROVIDER, "authorize_url": authorize_url}


@router.get("/procore/callback")
async def procore_callback(code: str, state: str) -> RedirectResponse:
    """Procore redirects here after the customer grants access.

    Validates `state` (CSRF + tenant binding), exchanges the code for tokens, and stores the refresh
    token encrypted for the bound tenant. Returns a redirect back into the app. No auth dependency is
    used here (the caller is Procore's redirect, not a logged-in session) — the signed `state` IS the
    authentication of which tenant this callback belongs to.
    """
    settings = get_settings()
    if not settings.credential_encryption_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="credential vault not configured (set CREDENTIAL_ENCRYPTION_KEY)",
        )
    # 1) Validate state → the tenant that started this flow. Any failure is a 400 (never trust input).
    try:
        tenant_id = oauth_state.validate_state(state, _state_secret(), now=int(time.time()))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    # 2) Exchange the code for tokens. Fail closed; never surface the provider's raw error body
    # (it can echo the submitted code), so map any exchange failure to a generic 502.
    try:
        tokens = await procore_oauth.exchange_code(settings, code=code)
    except Exception as exc:  # noqa: BLE001 — httpx error / non-2xx / malformed JSON all fail closed
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Procore token exchange failed — restart the connection",
        ) from exc

    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Procore did not return a refresh token",
        )

    # 3) Best-effort company id (the live client scopes calls with Procore-Company-Id).
    company_id = await procore_oauth.resolve_company_id(
        settings, access_token=tokens.get("access_token", "")
    )

    # 4) Store the refresh token ENCRYPTED for the bound tenant, in the per-tenant RLS vault.
    secret = {"refresh_token": refresh_token}
    if company_id:
        secret["company_id"] = company_id
    metadata = {"company_id": company_id} if company_id else {}
    async with tenant_session(tenant_id) as session:
        await credentials.store_credential(
            session, provider=_PROVIDER, secret=secret, metadata=metadata
        )
        await runs.insert_audit(
            session,
            actor="oauth:procore",
            action="connection.oauth.procore",
            target=_PROVIDER,
            detail={"provider": _PROVIDER, "company_id_present": bool(company_id)},
        )

    return RedirectResponse(url="/?connected=procore", status_code=status.HTTP_302_FOUND)
