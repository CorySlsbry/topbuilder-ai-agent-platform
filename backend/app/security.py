"""JWT issuance/verification and the request Principal.

Dev uses an HS256 issuer (`/auth/dev-token`). In production, swap `decode_token` to verify against
your IdP's JWKS (Supabase / Auth0 / Entra) — the rest of the app only depends on `Principal`.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import jwt
from pydantic import BaseModel

from app.config import Settings, get_settings

# The role carried by the non-human identity that the event-detection loop (ADR 0010) runs under.
# It may only PROPOSE actions: the action gate hard-refuses approve/execute under this role (a belt on
# top of the per-agent autonomy mode + ALWAYS_HITL_KINDS), so a detected event can never self-approve.
SYSTEM_ROLE = "system"


class Principal(BaseModel):
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    email: str
    role: str  # 'admin' | 'analyst' | 'viewer'
    # Authenticator assurance level. 'aal2' = a second factor (TOTP) was verified this session.
    # Defaults to the WEAKEST value: 'aal2' is granted ONLY by positive evidence of a second factor
    # (the Supabase 'aal' claim, a mapped OIDC amr/acr, or the ENV=dev god-token which explicitly
    # opts in). require_admin demands aal2, so operator access is genuinely 2FA-enforced.
    aal: str = "aal1"
    # Department scope from the membership directory. None = unrestricted (executive/operator);
    # otherwise app/org/permissions.py maps it to the agents/sections this principal may use.
    department: str | None = None
    # Link to the org_people row this login represents (str — set from the membership).
    person_id: str | None = None


class AuthError(Exception):
    """Raised when a token is missing, malformed, expired, or fails verification."""


def create_token(
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    email: str,
    role: str = "admin",
    department: str | None = None,
    expires_minutes: int | None = None,
) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    exp_minutes = expires_minutes if expires_minutes is not None else settings.jwt_expiry_minutes
    payload = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "email": email,
        "role": role,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + timedelta(minutes=exp_minutes),
    }
    if department is not None:
        payload["department"] = department
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


_jwks_client: jwt.PyJWKClient | None = None


def _get_jwks_client(url: str) -> jwt.PyJWKClient:
    global _jwks_client
    if _jwks_client is None or getattr(_jwks_client, "uri", None) != url:
        _jwks_client = jwt.PyJWKClient(url)
    return _jwks_client


def oidc_aal_from_claims(claims: dict) -> str:
    """Map an OIDC token's MFA evidence to our aal level. 'aal2' only when the token PROVES a second
    factor (an explicit aal2/acr, or an 'mfa'/'otp'/'hwk' entry in amr); otherwise 'aal1'."""
    aal = str(claims.get("aal", "")).lower()
    if aal in ("aal2", "aal3"):
        return "aal2"
    acr = str(claims.get("acr", "")).lower()
    if "aal2" in acr or "mfa" in acr or "loa3" in acr or "loa2" in acr:
        return "aal2"
    amr = claims.get("amr") or []
    if isinstance(amr, list) and any(str(m).lower() in {"mfa", "otp", "hwk", "totp", "sms"} for m in amr):
        return "aal2"
    return "aal1"


def oidc_identity_from_claims(claims: dict, settings: Settings) -> tuple[uuid.UUID, str, str]:
    """Pure: verified OIDC claims -> (derived stable user_id, email, aal). Tenant + role are NOT
    taken from the token — they are resolved from the membership directory (see deps), exactly like
    the Supabase path, so a self-asserted role/tenant claim can never grant access."""
    subject = str(claims.get("sub", ""))
    if not subject:
        raise AuthError("token missing 'sub'")
    user_id = uuid.uuid5(uuid.NAMESPACE_URL, f"{settings.oidc_issuer}|{subject}")
    return user_id, str(claims.get("email", "")), oidc_aal_from_claims(claims)


def _decode_dev(token: str) -> Principal:
    settings = get_settings()
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
        )
    except jwt.PyJWTError as exc:  # expired, bad signature, wrong aud/iss, malformed
        raise AuthError(str(exc)) from exc
    try:
        return Principal(
            tenant_id=uuid.UUID(claims["tenant_id"]),
            user_id=uuid.UUID(claims["sub"]),
            email=claims.get("email", ""),
            role=claims.get("role", "viewer"),
            department=claims.get("department"),
            # The dev god-token is ENV=dev-only (unreachable in prod) and is trusted as a fully
            # privileged operator session, so it explicitly opts into aal2.
            aal="aal2",
        )
    except (KeyError, ValueError) as exc:
        raise AuthError(f"token missing required claims: {exc}") from exc


def verify_oidc_claims(token: str, settings: Settings | None = None) -> dict:
    """Verify an external-IdP (JWKS) access token's signature/aud/iss and return its claims.
    Identity only — tenant + role are resolved from the directory by the caller, NOT trusted here."""
    settings = settings or get_settings()
    if not (settings.oidc_jwks_url and settings.oidc_issuer and settings.oidc_audience):
        raise AuthError("jwks auth not configured (set OIDC_JWKS_URL / OIDC_ISSUER / OIDC_AUDIENCE)")
    try:
        signing_key = _get_jwks_client(settings.oidc_jwks_url).get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience=settings.oidc_audience,
            issuer=settings.oidc_issuer,
        )
    except jwt.PyJWTError as exc:
        raise AuthError(str(exc)) from exc


def decode_token(token: str) -> Principal:
    """Verify a DEV (HS256) bearer token into a Principal. The JWKS path is handled in deps
    (it must resolve tenant + role from the directory, which requires DB access)."""
    return _decode_dev(token)


_supabase_jwks_client: jwt.PyJWKClient | None = None


def _get_supabase_jwks_client(url: str) -> jwt.PyJWKClient:
    global _supabase_jwks_client
    if _supabase_jwks_client is None or getattr(_supabase_jwks_client, "uri", None) != url:
        _supabase_jwks_client = jwt.PyJWKClient(url)
    return _supabase_jwks_client


def decode_supabase_claims(token: str, settings: Settings | None = None) -> dict:
    """Verify a Supabase Auth access token (ES256 via the project JWKS) and return its claims.

    Identity only — tenant + role come from the user_memberships directory, NOT the token.
    The 'aal' claim carries the MFA assurance level ('aal2' once a TOTP factor is verified).
    """
    settings = settings or get_settings()
    if not settings.supabase_auth_configured:
        raise AuthError("supabase auth not configured (set SUPABASE_URL)")
    try:
        signing_key = _get_supabase_jwks_client(settings.supabase_jwks_url).get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256"],
            audience=settings.supabase_audience,
            issuer=settings.supabase_issuer,
        )
    except jwt.PyJWTError as exc:
        raise AuthError(str(exc)) from exc


def supabase_identity_from_claims(claims: dict) -> tuple[uuid.UUID, str, str]:
    """Pure claims -> (auth_user_id, email, aal). Unit-testable without a network."""
    sub = str(claims.get("sub", ""))
    if not sub:
        raise AuthError("token missing 'sub'")
    try:
        auth_user_id = uuid.UUID(sub)
    except ValueError as exc:
        raise AuthError("'sub' is not a valid UUID") from exc
    return auth_user_id, str(claims.get("email", "")), str(claims.get("aal", "aal1"))
