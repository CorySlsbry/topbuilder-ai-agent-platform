"""Supabase auth path + 2FA (aal2) enforcement — pure tests, no network/DB.

The membership DB resolution is integration-tested; here we prove the security-critical pure
logic: claims -> identity mapping, ES256 verification against a known key, the Principal aal
default, and require_admin's two distinct 403s (role vs missing 2FA).
"""
from __future__ import annotations

import time
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ec import SECP256R1, generate_private_key
from fastapi import HTTPException

from app.api.deps import require_admin, require_lead_or_admin
from app.config import Settings
from app.security import (
    AuthError,
    Principal,
    decode_supabase_claims,
    supabase_identity_from_claims,
)


def _principal(role: str, aal: str = "aal2") -> Principal:
    return Principal(
        tenant_id=uuid.uuid4(), user_id=uuid.uuid4(), email="t@example.com", role=role, aal=aal
    )


def test_principal_aal_defaults_to_aal1_fail_closed():
    # SEC-1: aal2 is granted only by positive MFA evidence; the default is the WEAKEST level so an
    # auth path that forgets to set it can't accidentally pass require_admin's 2FA gate.
    p = Principal(tenant_id=uuid.uuid4(), user_id=uuid.uuid4(), email="x@y.z", role="admin")
    assert p.aal == "aal1"


def test_supabase_identity_from_claims_happy_path():
    uid = uuid.uuid4()
    auth_user_id, email, aal = supabase_identity_from_claims(
        {"sub": str(uid), "email": "person1@example.com", "aal": "aal2"}
    )
    assert (auth_user_id, email, aal) == (uid, "person1@example.com", "aal2")


def test_supabase_identity_defaults_to_aal1_when_claim_missing():
    _, _, aal = supabase_identity_from_claims({"sub": str(uuid.uuid4()), "email": "a@b.c"})
    assert aal == "aal1"


@pytest.mark.parametrize("claims", [{}, {"sub": ""}, {"sub": "not-a-uuid"}])
def test_supabase_identity_rejects_bad_sub(claims):
    with pytest.raises(AuthError):
        supabase_identity_from_claims(claims)


def test_decode_supabase_claims_requires_configuration():
    settings = Settings(supabase_url=None)
    with pytest.raises(AuthError, match="not configured"):
        decode_supabase_claims("any.token.here", settings)


def test_decode_supabase_claims_verifies_es256(monkeypatch):
    """Round-trip an ES256 token through the verifier with a stubbed JWKS client."""
    private_key = generate_private_key(SECP256R1())
    settings = Settings(supabase_url="https://proj.supabase.co")
    now = int(time.time())
    token = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "email": "person1@example.com",
            "aal": "aal2",
            "aud": settings.supabase_audience,
            "iss": settings.supabase_issuer,
            "iat": now,
            "exp": now + 300,
        },
        private_key,
        algorithm="ES256",
    )

    class _StubKey:
        key = private_key.public_key()

    class _StubJwks:
        def get_signing_key_from_jwt(self, _tok):
            return _StubKey()

    monkeypatch.setattr("app.security._get_supabase_jwks_client", lambda url: _StubJwks())
    claims = decode_supabase_claims(token, settings)
    assert claims["email"] == "person1@example.com" and claims["aal"] == "aal2"

    # Tampered/foreign-key tokens must fail closed.
    other = generate_private_key(SECP256R1())
    forged = jwt.encode({"sub": "x", "aud": settings.supabase_audience, "iss": settings.supabase_issuer,
                         "iat": now, "exp": now + 300}, other, algorithm="ES256")
    with pytest.raises(AuthError):
        decode_supabase_claims(forged, settings)


async def test_require_admin_allows_admin_with_aal2():
    p = _principal("admin", aal="aal2")
    assert await require_admin(p) is p


async def test_require_admin_rejects_non_admin_role():
    with pytest.raises(HTTPException) as exc:
        await require_admin(_principal("analyst"))
    assert exc.value.status_code == 403 and "may not perform this operation" in exc.value.detail


async def test_require_admin_rejects_admin_without_2fa():
    with pytest.raises(HTTPException) as exc:
        await require_admin(_principal("admin", aal="aal1"))
    assert exc.value.status_code == 403 and "2FA" in exc.value.detail


async def test_require_lead_or_admin_allows_lead_and_admin_with_2fa():
    assert await require_lead_or_admin(_principal("lead", aal="aal2")) is not None
    assert await require_lead_or_admin(_principal("admin", aal="aal2")) is not None


async def test_require_lead_or_admin_rejects_analyst_and_viewer():
    for role in ("analyst", "viewer"):
        with pytest.raises(HTTPException) as exc:
            await require_lead_or_admin(_principal(role))
        assert exc.value.status_code == 403 and "may not approve" in exc.value.detail


async def test_require_lead_or_admin_keeps_the_2fa_gate_for_a_lead():
    # A money/legal approval must stay 2FA-gated for a lead exactly as it was for an admin.
    with pytest.raises(HTTPException) as exc:
        await require_lead_or_admin(_principal("lead", aal="aal1"))
    assert exc.value.status_code == 403 and "2FA" in exc.value.detail
