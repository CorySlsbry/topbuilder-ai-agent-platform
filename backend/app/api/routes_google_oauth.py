"""Per-customer Google integration OAuth onboarding — Drive / Sheets Authorization-Code flow.

A customer admin starts the connection (GET .../connect → an authorize URL the SPA redirects to),
grants Drive/Sheets access in Google's consent screen, and Google redirects back to
.../callback?code=&state=. We validate the tenant-bound `state` (CSRF), exchange the code for tokens
server-side, and store the **refresh token** ENCRYPTED in the same per-tenant AES-256-GCM credential
vault that holds the ServiceTitan/QuickBooks/Procore secrets (provider="google"). The connection then
lets the Financial agent read the tenant's Google Sheets (their AR tracker + budget-to-actual doc) and
Drive files directly.

This MIRRORS `app/api/routes_integrations.py` (Procore) exactly — same security posture, same shared
tenant-bound HMAC `state`. See that module's docstring for the full rationale.

Security posture (this is an authz surface):
  - admin-only (require_admin → role==admin AND aal2/2FA), exactly like the credential-vault writes.
  - `state` is an unguessable HMAC bound to the tenant — a callback can't be forged or cross-tenant.
  - secrets come only from settings/Secret Manager; the refresh token is encrypted at rest.
  - fail closed on every error; the code/secret/access/refresh tokens are NEVER logged or echoed.
  - PRE-PRODUCTION HARDENING (tracked — SHARED with Procore): `state` is tenant-bound but not
    session/PKCE-bound, so an admin could be login-CSRF'd into connecting Google to their OWN tenant
    (no cross-tenant hijack; gated by admin+aal2). Bind `state` to the initiating browser session
    (HttpOnly cookie) or add PKCE in `oauth_state.py` — fixing it once covers both providers.
"""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse

from app.api.deps import require_admin
from app.config import get_settings
from app.db import tenant_session
from app.integrations.construction import oauth_state
from app.integrations.google import google_oauth
from app.repositories import credentials, runs
from app.security import Principal

router = APIRouter(prefix="/v1/integrations", tags=["connections"])

_PROVIDER = "google"


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


@router.get("/google/connect")
async def google_connect(principal: Principal = Depends(require_admin)) -> dict:
    """Begin the Google connection. Returns the authorize URL for the SPA to redirect the admin to."""
    settings = get_settings()
    if not (settings.google_client_id and settings.google_redirect_uri):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google integration not configured (set GOOGLE_CLIENT_ID / GOOGLE_REDIRECT_URI)",
        )
    state = oauth_state.generate_state(
        principal.tenant_id, _state_secret(), now=int(time.time())
    )
    try:
        authorize_url = google_oauth.build_authorize_url(settings, state=state)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return {"provider": _PROVIDER, "authorize_url": authorize_url}


@router.get("/google/callback")
async def google_callback(
    code: str | None = None, state: str | None = None, error: str | None = None
) -> RedirectResponse:
    """Google redirects here after the customer grants Drive/Sheets access.

    Validates `state` (CSRF + tenant binding), exchanges the code for tokens, and stores the refresh
    token encrypted for the bound tenant. Returns a redirect back into the app. No auth dependency is
    used here (the caller is Google's redirect, not a logged-in session) — the signed `state` IS the
    authentication of which tenant this callback belongs to.
    """
    # Declined consent / no code: Google sends ?error=access_denied. Friendly redirect, not a raw 422.
    if error or not code:
        return RedirectResponse(
            url="/?connected=google&status=cancelled", status_code=status.HTTP_302_FOUND
        )
    if not state:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing state")
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
        tokens = await google_oauth.exchange_code(settings, code=code)
    except Exception as exc:  # noqa: BLE001 — httpx error / non-2xx / malformed JSON all fail closed
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Google token exchange failed — restart the connection",
        ) from exc

    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        # Google omits the refresh token on silent re-consent; we force prompt=consent on the
        # authorize URL so this only fires on a genuine error. Fail closed (don't store a half-link).
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Google did not return a refresh token — restart the connection",
        )

    # 3) Best-effort connecting-user email (for display in the connections UI / audit context).
    email = await google_oauth.resolve_user_email(
        settings, access_token=tokens.get("access_token", "")
    )
    # The scopes Google actually granted (may be a subset of those requested).
    granted_scopes = tokens.get("scope", "") if isinstance(tokens.get("scope"), str) else ""

    # 4) Store the refresh token ENCRYPTED for the bound tenant, in the per-tenant RLS vault.
    #    Only the refresh_token is a SECRET; email + scopes are non-secret metadata.
    secret = {"refresh_token": refresh_token}
    metadata: dict[str, str] = {}
    if email:
        metadata["email"] = email
    if granted_scopes:
        metadata["scopes"] = granted_scopes
    async with tenant_session(tenant_id) as session:
        await credentials.store_credential(
            session, provider=_PROVIDER, secret=secret, metadata=metadata
        )
        await runs.insert_audit(
            session,
            actor="oauth:google",
            action="connection.oauth.google",
            target=_PROVIDER,
            detail={"provider": _PROVIDER, "email_present": bool(email), "scopes": granted_scopes},
        )

    return RedirectResponse(url="/?connected=google", status_code=status.HTTP_302_FOUND)
