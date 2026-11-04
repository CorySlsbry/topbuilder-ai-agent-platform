"""Ad-platform OAuth onboarding WITH PKCE + a state->server-session binding (operator-scoped, ADR 0009).

Meta and Google Ads connect flows for the PLATFORM OPERATOR (Cory's GTM ad accounts), NOT a customer
tenant. This deliberately CLOSES the open-state gap the older providers (Procore/Google/QBO) defer:

  * PKCE (RFC 7636, S256) — the ``code_challenge`` rides the authorize URL; the matching ``code_verifier``
    NEVER leaves our server, so an intercepted ``code`` alone is useless.
  * state -> server session — the ``state`` nonce + the ``code_verifier`` are signed (HMAC-SHA256 over the
    app secret) into a short-lived, HttpOnly, SameSite=Lax cookie. The callback re-derives them from the
    cookie and refuses unless the cookie's ``state`` matches the query ``state`` — binding the round-trip
    to the initiating browser (defeats login-CSRF).

Auth: ``/connect`` is operator-only (``require_admin`` + the platform-operator allowlist). ``/callback``
has NO auth dependency (the caller is the provider redirect) — the signed cookie + state ARE the proof of
which flow this callback belongs to. Tokens are stored encrypted in the OPERATOR vault
(``operator_credentials``, AES-256-GCM) and bound to ``ad_accounts.vault_credential_id``; secrets/codes
are NEVER logged or echoed (provider exchange errors map to a generic 502).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse

from app.api.deps import require_admin
from app.config import get_settings
from app.db import operator_session
from app.integrations.ads_google import google_ads_oauth
from app.integrations.ads_meta import meta_oauth
from app.repositories import ads as ads_repo
from app.repositories import operator_credentials
from app.security import Principal

router = APIRouter(prefix="/v1/integrations", tags=["connections"])

_SESSION_TTL = 600  # seconds the connect->callback round-trip is valid
_PROVIDERS = {"meta": "meta", "google_ads": "google_ads"}
# the ad_accounts.platform value each OAuth provider connects ('meta' ad account / 'google' ad account).
_AD_PLATFORM = {"meta": "meta", "google_ads": "google"}


def _is_platform_operator(principal: Principal) -> bool:
    allow = get_settings().platform_operator_email_set
    return bool(principal.email) and principal.email.strip().lower() in allow


def _require_platform_operator(principal: Principal) -> None:
    if not _is_platform_operator(principal):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "connecting an ad platform is a platform-operator action — your account is not an operator",
        )


def _state_secret() -> str:
    """The signing key for the OAuth session cookie — the app's JWT secret. Refuses the placeholder."""
    secret = get_settings().jwt_secret
    if not secret or secret == "change-me":
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "OAuth not configured (JWT_SECRET unset)"
        )
    return secret


def _cookie_name(provider: str) -> str:
    return f"tba_ads_oauth_{provider}"


def _sign_session(provider: str, *, state: str, code_verifier: str, now: int) -> str:
    """Sign ``{provider,state,code_verifier,iat}`` into a compact ``payload.mac`` cookie value.

    The MAC binds the provider + state + verifier + issue time; tampering or reuse across providers/
    flows fails the constant-time compare in :func:`_open_session`.
    """
    body = {"p": provider, "s": state, "v": code_verifier, "iat": now}
    raw = base64.urlsafe_b64encode(json.dumps(body, separators=(",", ":")).encode()).decode()
    mac = hmac.new(_state_secret().encode(), raw.encode(), hashlib.sha256).hexdigest()
    return f"{raw}.{mac}"


def _open_session(provider: str, cookie_value: str | None, *, now: int) -> dict:
    """Verify + decode a session cookie; raise 400 on any tamper / expiry / provider mismatch."""
    if not cookie_value or "." not in cookie_value:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "missing or malformed OAuth session")
    raw, _, mac = cookie_value.partition(".")
    expected = hmac.new(_state_secret().encode(), raw.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, mac):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "OAuth session signature invalid")
    try:
        body = json.loads(base64.urlsafe_b64decode(raw.encode()).decode())
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "OAuth session corrupt") from exc
    if body.get("p") != provider:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "OAuth session provider mismatch")
    if now - int(body.get("iat", 0)) > _SESSION_TTL:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "OAuth session expired — restart the connection")
    return body


def _build_authorize(provider: str, settings, *, state: str, code_challenge: str) -> str:
    if provider == "meta":
        return meta_oauth.build_authorize_url(settings, state=state, code_challenge=code_challenge)
    return google_ads_oauth.build_authorize_url(settings, state=state, code_challenge=code_challenge)


# ── connect ─────────────────────────────────────────────────────────────────────────────────────────
@router.get("/{provider}/connect")
async def ads_connect(
    provider: str, principal: Principal = Depends(require_admin)
) -> JSONResponse:
    """Begin an ad-platform OAuth connection (operator-only). Returns the authorize URL + sets the session cookie.

    The SPA reads ``{provider, authorize_url}`` and redirects the browser; the HttpOnly session cookie
    (set on this same response) carries the state->verifier binding the callback re-checks.
    """
    if provider not in _PROVIDERS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown ad-platform provider")
    _require_platform_operator(principal)
    settings = get_settings()
    now = int(time.time())
    state = secrets.token_urlsafe(24)
    if provider == "meta":
        code_verifier = meta_oauth.generate_code_verifier()
        code_challenge = meta_oauth.code_challenge_from_verifier(code_verifier)
    else:
        code_verifier, code_challenge = google_ads_oauth.generate_pkce_pair()
    try:
        authorize_url = _build_authorize(provider, settings, state=state, code_challenge=code_challenge)
    except RuntimeError as exc:  # client id / redirect uri unset
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc

    session_value = _sign_session(provider, state=state, code_verifier=code_verifier, now=now)
    response = JSONResponse({"provider": provider, "authorize_url": authorize_url})
    # HttpOnly so JS can't read the verifier; Lax so the cookie survives the provider redirect back.
    response.set_cookie(
        key=_cookie_name(provider), value=session_value, max_age=_SESSION_TTL,
        httponly=True, samesite="lax", secure=not settings.is_dev, path="/v1/integrations",
    )
    return response


# ── callback (NO auth dep — the signed cookie + state is the proof) ─────────────────────────────────
@router.get("/{provider}/callback")
async def ads_callback(
    provider: str,
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Provider redirect target. Verifies the session cookie + state, exchanges the code (with the PKCE
    verifier), stores the token in the operator vault, and binds it to the ad account. Fail-closed."""
    if provider not in _PROVIDERS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown ad-platform provider")
    if error:  # the operator cancelled the consent dialog
        return RedirectResponse(url=f"/?connect_error={provider}", status_code=status.HTTP_302_FOUND)
    if not code or not state:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "missing code or state")

    settings = get_settings()
    if not settings.credential_encryption_key:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "credential vault not configured (set CREDENTIAL_ENCRYPTION_KEY)",
        )

    now = int(time.time())
    session = _open_session(provider, request.cookies.get(_cookie_name(provider)), now=now)
    if not hmac.compare_digest(str(session.get("s", "")), state):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "state does not match the session (CSRF)")
    code_verifier = str(session.get("v", ""))

    # Exchange the code (+ PKCE verifier). Never surface the provider's raw error body (it can echo the
    # code) — map any failure to a generic 502.
    try:
        if provider == "meta":
            tokens = await meta_oauth.exchange_code(settings, code=code, code_verifier=code_verifier)
            short = tokens.get("access_token")
            if short:
                tokens = await meta_oauth.exchange_long_lived_token(settings, short_lived_token=short)
        else:
            tokens = await google_ads_oauth.exchange_code(
                settings, code=code, code_verifier=code_verifier
            )
    except Exception as exc:  # noqa: BLE001 — httpx / non-2xx / malformed JSON all fail closed
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"{provider} token exchange failed — restart the connection"
        ) from exc

    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")
    if not access_token and not refresh_token:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"{provider} did not return a usable token")
    # Google omits the refresh_token on silent re-consent; we force prompt=consent, so a missing one
    # means a half-linked connection — fail closed rather than store an un-refreshable Google credential.
    if provider == "google_ads" and not refresh_token:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Google did not return a refresh token — revoke the app's access and reconnect",
        )

    secret = {k: v for k, v in tokens.items() if v is not None}
    metadata = {
        "connected_at": now,
        "scope": tokens.get("scope"),
        "expires_in": tokens.get("expires_in"),
    }
    # The connected ad-account id isn't in the token response for either platform (it's a follow-up API
    # call at go-live); store under a stable per-provider external_ref so the vault row is idempotent.
    external_ref = f"{provider}-operator"
    ad_platform = _AD_PLATFORM[provider]
    async with operator_session() as session_db:
        credential_id = await operator_credentials.store_credential(
            session_db, provider=provider, secret=secret, metadata=metadata, external_ref=external_ref,
        )
        await ads_repo.upsert_ad_account(
            session_db, platform=ad_platform, external_account_id=external_ref,
            display_name=f"{ad_platform.title()} Ads (operator)",
            vault_credential_id=credential_id, status="connected",
            metadata={"provider": provider},
        )

    response = RedirectResponse(url=f"/?connected={provider}", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(_cookie_name(provider), path="/v1/integrations")
    return response
