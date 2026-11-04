"""Tests for the production hardening layer: rate limiter, error envelope, headers, OIDC mapping."""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.ratelimit import RateLimiter
from app.security import (
    AuthError,
    oidc_aal_from_claims,
    oidc_identity_from_claims,
)


class TestRateLimiter:
    async def test_allows_burst_then_denies(self) -> None:
        limiter = RateLimiter(per_minute=60, burst=3)  # capacity 3, refill 1/sec
        results = [(await limiter.allow("k", 0.0))[0] for _ in range(4)]
        assert results == [True, True, True, False]

    async def test_refills_over_time(self) -> None:
        limiter = RateLimiter(per_minute=60, burst=2)
        await limiter.allow("k", 0.0)
        await limiter.allow("k", 0.0)
        denied, retry_after = await limiter.allow("k", 0.0)
        assert denied is False and retry_after > 0
        allowed_again, _ = await limiter.allow("k", 5.0)
        assert allowed_again is True

    async def test_keys_are_independent(self) -> None:
        limiter = RateLimiter(per_minute=60, burst=1)
        assert (await limiter.allow("a", 0.0))[0] is True
        assert (await limiter.allow("b", 0.0))[0] is True  # different key, own bucket


class TestErrorEnvelopeAndHeaders:
    client = TestClient(__import__("app.main", fromlist=["app"]).app, raise_server_exceptions=False)

    def test_unknown_route_uses_envelope(self) -> None:
        resp = self.client.get("/nope")
        assert resp.status_code == 404
        body = resp.json()
        assert body["error"]["code"] == "http_error"
        assert "request_id" in body["error"]

    def test_security_headers_present(self) -> None:
        resp = self.client.get("/")
        assert resp.headers["X-Content-Type-Options"] == "nosniff"
        assert resp.headers["X-Frame-Options"] == "DENY"
        assert "X-Request-ID" in resp.headers

    def test_protected_route_requires_auth(self) -> None:
        resp = self.client.get("/v1/agents/workforce/runs/latest")
        assert resp.status_code in (401, 403)
        assert resp.json()["error"]["code"] == "http_error"


class TestOidcIdentity:
    """SEC-2: the JWKS path takes IDENTITY (sub/email/aal) from the verified token but NEVER role or
    tenant — those resolve from the directory. SEC-1: aal is mapped from real MFA evidence only."""

    @staticmethod
    def _settings() -> Settings:
        return Settings(oidc_issuer="https://idp.example")

    def test_identity_extracted_but_no_role_or_tenant(self) -> None:
        # A token that self-asserts role=admin + a tenant must yield NEITHER — only identity.
        user_id, email, aal = oidc_identity_from_claims(
            {"sub": "auth0|abc", "email": "person1@example.com", "role": "admin", "tenant_id": str(uuid.uuid4())},
            self._settings(),
        )
        assert email == "person1@example.com"
        assert aal == "aal1"  # no MFA evidence -> weakest, NOT a free aal2
        assert isinstance(user_id, uuid.UUID)

    def test_derived_user_id_is_stable(self) -> None:
        claims = {"sub": "auth0|abc"}
        a, _, _ = oidc_identity_from_claims(claims, self._settings())
        b, _, _ = oidc_identity_from_claims(claims, self._settings())
        assert a == b

    def test_missing_sub_raises(self) -> None:
        with pytest.raises(AuthError):
            oidc_identity_from_claims({"email": "person1@example.com"}, self._settings())

    def test_aal_mapping_requires_real_mfa_evidence(self) -> None:
        assert oidc_aal_from_claims({}) == "aal1"
        assert oidc_aal_from_claims({"role": "admin"}) == "aal1"  # role is not MFA
        assert oidc_aal_from_claims({"aal": "aal2"}) == "aal2"
        assert oidc_aal_from_claims({"acr": "urn:mace:incommon:iap:silver-mfa"}) == "aal2"
        assert oidc_aal_from_claims({"amr": ["pwd", "otp"]}) == "aal2"
        assert oidc_aal_from_claims({"amr": ["pwd"]}) == "aal1"
