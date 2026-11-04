"""Pure tests for the Procore Authorization-Code OAuth onboarding.

Three surfaces, all infra-free (the DB write is monkeypatched, httpx is stubbed):
  1. oauth_state — tenant-bound HMAC state: generate→validate round-trips, and every CSRF/expiry/
     tamper path fails closed.
  2. procore_oauth — the authorize-URL builder + the code→tokens exchange (httpx mocked).
  3. routes_integrations — the connect URL is admin-gated + tenant-bound, and the callback validates
     state, exchanges the code, ENCRYPTS+stores the refresh token, and fails closed on a bad state /
     a token-exchange error / a missing refresh token.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from app.config import Settings
from app.integrations.construction import oauth_state, procore_oauth

TENANT_A = uuid.UUID("11111111-1111-1111-1111-111111111111")
TENANT_B = uuid.UUID("22222222-2222-2222-2222-222222222222")
SECRET = "a-32-byte-min-signing-secret-for-tests-only-0123456789"
NOW = 1_700_000_000  # a fixed epoch so expiry math is deterministic


# --- oauth_state: tenant-bound CSRF token ---------------------------------------------------------
class TestOauthState:
    def test_generate_then_validate_recovers_the_bound_tenant(self) -> None:
        state = oauth_state.generate_state(TENANT_A, SECRET, now=NOW)
        assert oauth_state.validate_state(state, SECRET, now=NOW) == str(TENANT_A)

    def test_state_is_opaque_and_unguessable(self) -> None:
        # The raw tenant id must not appear verbatim; two mints differ (fresh random nonce each time).
        state = oauth_state.generate_state(TENANT_A, SECRET, now=NOW)
        assert str(TENANT_A) not in state
        assert oauth_state.generate_state(TENANT_A, SECRET, now=NOW) != state

    def test_validate_rejects_a_state_signed_with_a_different_secret_csrf(self) -> None:
        forged = oauth_state.generate_state(TENANT_A, "attacker-controlled-secret", now=NOW)
        with pytest.raises(ValueError, match="signature mismatch"):
            oauth_state.validate_state(forged, SECRET, now=NOW)

    def test_validate_rejects_a_tampered_tenant_id(self) -> None:
        # Re-pack the token with tenant B but keep tenant A's signature → MAC fails (no cross-tenant).
        import base64

        raw = base64.urlsafe_b64decode(oauth_state.generate_state(TENANT_A, SECRET, now=NOW)).decode()
        _tid, issued, nonce, sig = raw.split(".")
        swapped = base64.urlsafe_b64encode(f"{TENANT_B}.{issued}.{nonce}.{sig}".encode()).decode()
        with pytest.raises(ValueError, match="signature mismatch"):
            oauth_state.validate_state(swapped, SECRET, now=NOW)

    def test_validate_rejects_an_expired_state(self) -> None:
        state = oauth_state.generate_state(TENANT_A, SECRET, now=NOW)
        with pytest.raises(ValueError, match="expired"):
            oauth_state.validate_state(state, SECRET, now=NOW + oauth_state.STATE_TTL_SECONDS + 1)

    def test_validate_rejects_a_future_dated_state(self) -> None:
        state = oauth_state.generate_state(TENANT_A, SECRET, now=NOW)
        with pytest.raises(ValueError, match="expired"):
            oauth_state.validate_state(state, SECRET, now=NOW - 60)

    def test_validate_rejects_garbage(self) -> None:
        with pytest.raises(ValueError, match="malformed"):
            oauth_state.validate_state("not-base64-$$$", SECRET, now=NOW)

    def test_validate_rejects_empty_state(self) -> None:
        with pytest.raises(ValueError, match="missing state"):
            oauth_state.validate_state("", SECRET, now=NOW)

    def test_generate_requires_a_secret(self) -> None:
        with pytest.raises(ValueError, match="signing secret"):
            oauth_state.generate_state(TENANT_A, "", now=NOW)


# --- procore_oauth: authorize URL + token exchange ------------------------------------------------
def _settings(**over) -> Settings:
    base = dict(
        procore_client_id="cid-123",
        procore_client_secret="csecret-456",
        procore_authorize_url="https://login.procore.com/oauth/authorize",
        procore_auth_url="https://login.procore.com/oauth/token",
        procore_redirect_uri="https://api.example.com/v1/integrations/procore/callback",
        procore_base_url="https://api.procore.com",
        credential_encryption_key=None,
    )
    base.update(over)
    return Settings(**base)


class TestAuthorizeUrl:
    def test_builds_the_authorize_url_with_all_required_params(self) -> None:
        url = procore_oauth.build_authorize_url(_settings(), state="STATE123")
        assert url.startswith("https://login.procore.com/oauth/authorize?")
        for fragment in (
            "response_type=code",
            "client_id=cid-123",
            "state=STATE123",
            # redirect_uri is URL-encoded in the query string
            "redirect_uri=https%3A%2F%2Fapi.example.com%2Fv1%2Fintegrations%2Fprocore%2Fcallback",
        ):
            assert fragment in url

    def test_authorize_url_requires_a_client_id(self) -> None:
        with pytest.raises(RuntimeError, match="PROCORE_CLIENT_ID"):
            procore_oauth.build_authorize_url(_settings(procore_client_id=None), state="s")


class _FakeResponse:
    def __init__(self, json_body: dict) -> None:
        self._json = json_body

    def raise_for_status(self) -> None:  # 2xx
        return None

    def json(self) -> dict:
        return self._json


class _FakeAsyncClient:
    """Records the single POST and returns a canned token response."""

    posted: dict | None = None

    def __init__(self, *_, **__) -> None:
        pass

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    async def post(self, url, data=None, headers=None):  # noqa: ANN001
        type(self).posted = {"url": url, "data": data}
        return _FakeResponse({
            "access_token": "ACCESS_TOKEN",
            "refresh_token": "REFRESH_TOKEN",
            "expires_in": 7200,
        })


class TestExchangeCode:
    async def test_exchange_posts_authorization_code_grant_and_returns_tokens(self, monkeypatch) -> None:
        _FakeAsyncClient.posted = None
        monkeypatch.setattr(procore_oauth.httpx, "AsyncClient", _FakeAsyncClient)
        tokens = await procore_oauth.exchange_code(_settings(), code="ABC-CODE")
        assert tokens["refresh_token"] == "REFRESH_TOKEN"
        sent = _FakeAsyncClient.posted
        assert sent["url"] == "https://login.procore.com/oauth/token"
        assert sent["data"] == {
            "grant_type": "authorization_code",
            "client_id": "cid-123",
            "client_secret": "csecret-456",
            "code": "ABC-CODE",
            "redirect_uri": "https://api.example.com/v1/integrations/procore/callback",
        }

    async def test_exchange_requires_client_credentials(self) -> None:
        with pytest.raises(RuntimeError, match="PROCORE_CLIENT_ID"):
            await procore_oauth.exchange_code(_settings(procore_client_id=None), code="c")


# --- routes_integrations: connect + callback (DB write + httpx both stubbed) -----------------------
import base64  # noqa: E402
import contextlib  # noqa: E402

from app.api import routes_integrations  # noqa: E402
from app.security import Principal  # noqa: E402

# A real urlsafe-b64 32-byte AES-256 key so the vault cipher initializes in the callback happy path.
_AES_KEY = base64.urlsafe_b64encode(b"\x11" * 32).decode()


def _route_settings(**over) -> Settings:
    over.setdefault("credential_encryption_key", _AES_KEY)
    return _settings(jwt_secret=SECRET, **over)


def _admin(tenant=TENANT_A) -> Principal:
    return Principal(
        tenant_id=tenant, user_id=uuid.uuid4(), email="person1@example.com", role="admin", aal="aal2"
    )


@pytest.fixture
def _patched_route(monkeypatch):
    """Patch the route's settings + capture what gets written to the vault, with no DB."""
    settings = _route_settings()
    monkeypatch.setattr(routes_integrations, "get_settings", lambda: settings)

    captured: dict = {}

    @contextlib.asynccontextmanager
    async def _fake_session(tenant_id):
        captured["tenant_id"] = tenant_id
        yield object()  # the stubbed repo calls ignore the session

    async def _fake_store(session, *, provider, secret, metadata=None):
        captured["provider"] = provider
        captured["secret"] = secret
        captured["metadata"] = metadata

    async def _fake_audit(session, *, actor, action, target, detail):
        captured["audit"] = {"actor": actor, "action": action, "target": target, "detail": detail}

    monkeypatch.setattr(routes_integrations, "tenant_session", _fake_session)
    monkeypatch.setattr(routes_integrations.credentials, "store_credential", _fake_store)
    monkeypatch.setattr(routes_integrations.runs, "insert_audit", _fake_audit)
    return settings, captured


class TestConnectEndpoint:
    async def test_connect_returns_a_tenant_bound_authorize_url(self, _patched_route) -> None:
        settings, _ = _patched_route
        result = await routes_integrations.procore_connect(principal=_admin())
        assert result["provider"] == "procore"
        url = result["authorize_url"]
        assert url.startswith(settings.procore_authorize_url + "?")
        # The state in the URL must validate back to the caller's tenant.
        state = url.split("state=", 1)[1].split("&", 1)[0]
        import urllib.parse

        decoded_state = urllib.parse.unquote(state)
        assert oauth_state.validate_state(decoded_state, SECRET, now=int(__import__("time").time())) == str(TENANT_A)

    async def test_connect_503_when_procore_not_configured(self, monkeypatch) -> None:
        settings = _route_settings(procore_client_id=None)
        monkeypatch.setattr(routes_integrations, "get_settings", lambda: settings)
        with pytest.raises(HTTPException) as exc:
            await routes_integrations.procore_connect(principal=_admin())
        assert exc.value.status_code == 503


class TestCallbackEndpoint:
    async def test_callback_happy_path_encrypts_and_stores_the_refresh_token(
        self, monkeypatch, _patched_route
    ) -> None:
        settings, captured = _patched_route
        # A valid state for tenant A + a stubbed exchange returning a refresh token (no company read).
        state = oauth_state.generate_state(TENANT_A, SECRET, now=int(__import__("time").time()))

        async def _fake_exchange(_settings, *, code):
            assert code == "THE-CODE"
            return {"access_token": "AT", "refresh_token": "RT-xyz", "expires_in": 7200}

        async def _fake_company(_settings, *, access_token):
            return "company-99"

        monkeypatch.setattr(routes_integrations.procore_oauth, "exchange_code", _fake_exchange)
        monkeypatch.setattr(routes_integrations.procore_oauth, "resolve_company_id", _fake_company)

        resp = await routes_integrations.procore_callback(code="THE-CODE", state=state)
        assert resp.status_code == 302
        # The refresh token landed in the vault for the BOUND tenant (A), with company id alongside.
        # validate_state returns the tenant id as a str; the session/RLS casts it back to uuid.
        assert captured["tenant_id"] == str(TENANT_A)
        assert captured["provider"] == "procore"
        assert captured["secret"] == {"refresh_token": "RT-xyz", "company_id": "company-99"}
        assert captured["audit"]["action"] == "connection.oauth.procore"

    async def test_callback_rejects_an_invalid_state_before_any_exchange(
        self, monkeypatch, _patched_route
    ) -> None:
        _settings_obj, captured = _patched_route
        called = {"exchange": False}

        async def _boom(*_, **__):  # the exchange must never run on a bad state
            called["exchange"] = True
            return {}

        monkeypatch.setattr(routes_integrations.procore_oauth, "exchange_code", _boom)
        with pytest.raises(HTTPException) as exc:
            await routes_integrations.procore_callback(code="c", state="forged-state")
        assert exc.value.status_code == 400
        assert called["exchange"] is False
        assert "secret" not in captured  # nothing was stored

    async def test_callback_fails_closed_when_token_exchange_errors(
        self, monkeypatch, _patched_route
    ) -> None:
        _settings_obj, captured = _patched_route
        state = oauth_state.generate_state(TENANT_A, SECRET, now=int(__import__("time").time()))

        async def _raise(*_, **__):
            raise RuntimeError("procore 401 invalid_grant")  # must NOT leak into the response

        monkeypatch.setattr(routes_integrations.procore_oauth, "exchange_code", _raise)
        with pytest.raises(HTTPException) as exc:
            await routes_integrations.procore_callback(code="c", state=state)
        assert exc.value.status_code == 502
        assert "invalid_grant" not in exc.value.detail  # provider error body never echoed
        assert "secret" not in captured

    async def test_callback_fails_closed_when_no_refresh_token_returned(
        self, monkeypatch, _patched_route
    ) -> None:
        _settings_obj, captured = _patched_route
        state = oauth_state.generate_state(TENANT_A, SECRET, now=int(__import__("time").time()))

        async def _no_refresh(*_, **__):
            return {"access_token": "AT", "expires_in": 7200}  # refresh_token missing

        monkeypatch.setattr(routes_integrations.procore_oauth, "exchange_code", _no_refresh)
        with pytest.raises(HTTPException) as exc:
            await routes_integrations.procore_callback(code="c", state=state)
        assert exc.value.status_code == 502
        assert "secret" not in captured

    async def test_callback_503_when_vault_not_configured(self, monkeypatch) -> None:
        settings = _route_settings(credential_encryption_key=None)
        monkeypatch.setattr(routes_integrations, "get_settings", lambda: settings)
        with pytest.raises(HTTPException) as exc:
            await routes_integrations.procore_callback(code="c", state="x")
        assert exc.value.status_code == 503
