"""Per-customer QuickBooks Online integration OAuth onboarding — Intuit's OWN Authorization-Code flow.

A customer admin starts the connection (GET .../connect → an authorize URL the SPA redirects to),
grants accounting access in Intuit's consent screen, and Intuit redirects back to
.../callback?code=&state=&realmId=. We validate the tenant-bound `state` (CSRF), exchange the code
for tokens server-side, and store the **refresh token + realm id** ENCRYPTED in the same per-tenant
AES-256-GCM credential vault that holds the ServiceTitan/Procore/Google secrets (provider="quickbooks").
The connection then drives the live QuickBooks client (ACCOUNTING_MODE=quickbooks) for the Financial
agent. NO third-party connector / iPaaS is involved — this is a DIRECT Intuit OAuth connection.

This MIRRORS `app/api/routes_integrations.py` (Procore) + `routes_google_oauth.py` exactly — same
security posture, same shared tenant-bound HMAC `state`. The QBO-specific difference is the `realmId`
(the company id) that arrives on the callback: it is NOT a secret on its own (it's needed on every API
call) but we keep it ENCRYPTED with the refresh token AND in non-secret metadata for the connections UI.

Security posture (this is an authz + credential surface):
  - admin-only (require_admin → role==admin AND aal2/2FA), exactly like the credential-vault writes.
  - `state` is an unguessable HMAC bound to the tenant — a callback can't be forged or cross-tenant.
  - secrets come only from settings/Secret Manager; the refresh token is encrypted at rest.
  - fail closed on every error; the code/secret/access/refresh tokens + realmId are NEVER logged/echoed.
  - PRE-PRODUCTION HARDENING (tracked — SHARED with Procore + Google): `state` is tenant-bound but not
    session/PKCE-bound, so an admin could be login-CSRF'd into connecting QBO to their OWN tenant (no
    cross-tenant hijack; gated by admin+aal2). Bind `state` to the initiating browser session (HttpOnly
    cookie) or add PKCE in `oauth_state.py` — fixing it once covers all three providers.
"""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse

from app.api.deps import require_admin
from app.config import get_settings
from app.db import tenant_session
from app.integrations.construction import oauth_state
from app.integrations.quickbooks import qbo_oauth
from app.repositories import credentials, runs
from app.security import Principal

router = APIRouter(prefix="/v1/integrations", tags=["connections"])

_PROVIDER = "quickbooks"


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


@router.get("/quickbooks/connect")
async def quickbooks_connect(principal: Principal = Depends(require_admin)) -> dict:
    """Begin the QuickBooks connection. Returns the authorize URL for the SPA to redirect the admin to."""
    settings = get_settings()
    if not (settings.quickbooks_client_id and settings.quickbooks_redirect_uri):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="QuickBooks integration not configured "
            "(set QUICKBOOKS_CLIENT_ID / QUICKBOOKS_REDIRECT_URI)",
        )
    state = oauth_state.generate_state(
        principal.tenant_id, _state_secret(), now=int(time.time())
    )
    try:
        authorize_url = qbo_oauth.build_authorize_url(settings, state=state)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return {"provider": _PROVIDER, "authorize_url": authorize_url}


@router.get("/quickbooks/callback")
async def quickbooks_callback(
    code: str | None = None,
    state: str | None = None,
    realmId: str | None = None,  # noqa: N803 — Intuit sends the company id as `realmId` verbatim
    error: str | None = None,
) -> RedirectResponse:
    """Intuit redirects here after the customer grants QBO accounting access.

    Receives `code`, `state`, and `realmId` (the QBO company id). Validates `state` (CSRF + tenant
    binding), exchanges the code for tokens, and stores the refresh token + realm id encrypted for the
    bound tenant. No auth dependency is used here (the caller is Intuit's redirect, not a logged-in
    session) — the signed `state` IS the authentication of which tenant this callback belongs to.
    """
    # Declined consent / no code: Intuit sends ?error=access_denied. Friendly redirect, not a raw 422.
    if error or not code:
        return RedirectResponse(
            url="/?connected=quickbooks&status=cancelled", status_code=status.HTTP_302_FOUND
        )
    if not state:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing state")
    if not realmId:
        # The realm id is required to make ANY QBO API call — without it the connection is useless.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing realmId")
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
        tokens = await qbo_oauth.exchange_code(settings, code=code)
    except Exception as exc:  # noqa: BLE001 — httpx error / non-2xx / malformed JSON all fail closed
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="QuickBooks token exchange failed — restart the connection",
        ) from exc

    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        # Fail closed (don't store a half-linked connection that can never refresh).
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="QuickBooks did not return a refresh token — restart the connection",
        )

    # 3) Store the refresh token + realm id ENCRYPTED for the bound tenant, in the per-tenant RLS vault.
    #    realm_id rides in the secret (so the live QuickBooksClient + connection-test read it back the
    #    same way ServiceTitan/Procore secrets are read) AND in non-secret metadata for the UI/audit.
    secret = {"refresh_token": refresh_token, "realm_id": realmId}
    metadata = {"realm_id": realmId}
    async with tenant_session(tenant_id) as session:
        await credentials.store_credential(
            session, provider=_PROVIDER, secret=secret, metadata=metadata
        )
        await runs.insert_audit(
            session,
            actor="oauth:quickbooks",
            action="connection.oauth.quickbooks",
            target=_PROVIDER,
            detail={"provider": _PROVIDER, "realm_id_present": bool(realmId)},
        )

    return RedirectResponse(url="/?connected=quickbooks", status_code=status.HTTP_302_FOUND)
