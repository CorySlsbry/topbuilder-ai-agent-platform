"""Pure tests for the QuickBooks Online (Intuit) Authorization-Code OAuth onboarding.

Mirrors test_google_oauth.py / test_procore_oauth.py. Three surfaces, all infra-free (the DB write is
monkeypatched, httpx is stubbed):
  1. oauth_state — the SHARED tenant-bound HMAC state (re-used, not duplicated): a generate→validate
     round-trip that proves the QBO connect URL binds to the caller's tenant.
  2. qbo_oauth — the authorize-URL builder (scope + Intuit params) + the code→tokens exchange (httpx
     mocked, asserts HTTP Basic auth + the Intuit token URL + grant_type) + missing-creds guards.
  3. routes_qbo_oauth — the connect URL is admin-gated + tenant-bound, and the callback validates
     state, exchanges the code, ENCRYPTS+stores the refresh token + realm_id (realm_id also in
     metadata, audited), fails closed on a bad/forged state / a token-exchange error / a missing
     refresh token / a missing realmId, and friendly-redirects on a declined (?error=) consent.

CRITICAL QBO difference vs Procore/Google: the callback also carries `realmId` (the company id).
"""
from __future__ import annotations

import base64
import uuid

import pytest
from fastapi import HTTPException

from app.config import Settings
from app.integrations.construction import oauth_state
from app.integrations.quickbooks import qbo_oauth

TENANT_A = uuid.UUID("11111111-1111-1111-1111-111111111111")
TENANT_B = uuid.UUID("22222222-2222-2222-2222-222222222222")
SECRET = "a-32-byte-min-signing-secret-for-tests-only-0123456789"
NOW = 1_700_000_000  # a fixed epoch so expiry math is deterministic
REALM = "9341452148273465"  # a representative QBO realmId (company id)


# --- oauth_state binding (the shared module has full coverage in test_procore_oauth.py; here we only
#     re-assert the round-trip that the QBO connect URL relies on) -----------------------------------
class TestSharedStateBinding:
    def test_generate_then_validate_recovers_the_bound_tenant(self) -> None:
        state = oauth_state.generate_state(TENANT_A, SECRET, now=NOW)
        assert oauth_state.validate_state(state, SECRET, now=NOW) == str(TENANT_A)

    def test_state_minted_for_one_tenant_cannot_be_reused_for_another(self) -> None:
        # A state minted for tenant A validates back ONLY to tenant A — never B (no cross-tenant link).
        state = oauth_state.generate_state(TENANT_A, SECRET, now=NOW)
        assert oauth_state.validate_state(state, SECRET, now=NOW) != str(TENANT_B)


# --- qbo_oauth: authorize URL + token exchange ----------------------------------------------------
def _settings(**over) -> Settings:
    base = dict(
        quickbooks_client_id="qbo-cid-123",
        quickbooks_client_secret="qbo-secret-456",
        quickbooks_redirect_uri="https://api.example.com/v1/integrations/quickbooks/callback",
        quickbooks_scopes="com.intuit.quickbooks.accounting",
        quickbooks_authorize_url="https://appcenter.intuit.com/connect/oauth2",
        quickbooks_token_url="https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer",
        credential_encryption_key=None,
    )
    base.update(over)
    return Settings(**base)


class TestAuthorizeUrl:
    def test_builds_the_authorize_url_with_all_required_params(self) -> None:
        url = qbo_oauth.build_authorize_url(_settings(), state="STATE123")
        assert url.startswith("https://appcenter.intuit.com/connect/oauth2?")
        for fragment in (
            "client_id=qbo-cid-123",
            "response_type=code",
            "state=STATE123",
            # the accounting scope (the dots survive the query string verbatim)
            "scope=com.intuit.quickbooks.accounting",
            # redirect_uri is URL-encoded in the query string
            "redirect_uri=https%3A%2F%2Fapi.example.com%2Fv1%2Fintegrations%2Fquickbooks%2Fcallback",
        ):
            assert fragment in url

    def test_authorize_url_honors_an_explicit_scope_override(self) -> None:
        url = qbo_oauth.build_authorize_url(
            _settings(), state="s", scopes=["com.intuit.quickbooks.payment"]
        )
        assert "com.intuit.quickbooks.payment" in url
        assert "accounting" not in url

    def test_authorize_url_requires_a_client_id(self) -> None:
        with pytest.raises(RuntimeError, match="QUICKBOOKS_CLIENT_ID"):
            qbo_oauth.build_authorize_url(_settings(quickbooks_client_id=None), state="s")

    def test_authorize_url_requires_a_redirect_uri(self) -> None:
        with pytest.raises(RuntimeError, match="QUICKBOOKS_REDIRECT_URI"):
            qbo_oauth.build_authorize_url(_settings(quickbooks_redirect_uri=None), state="s")


class _FakeResponse:
    def __init__(self, json_body: dict) -> None:
        self._json = json_body

    def raise_for_status(self) -> None:  # 2xx
        return None

    def json(self) -> dict:
        return self._json


class _FakeAsyncClient:
    """Records the single POST (url + body + headers) and returns a canned token response."""

    posted: dict | None = None

    def __init__(self, *_, **__) -> None:
        pass

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    async def post(self, url, data=None, headers=None):  # noqa: ANN001
        type(self).posted = {"url": url, "data": data, "headers": headers}
        return _FakeResponse({
            "access_token": "ACCESS_TOKEN",
            "refresh_token": "REFRESH_TOKEN",
            "expires_in": 3600,
            "x_refresh_token_expires_in": 8_726_400,
            "token_type": "bearer",
        })


# The exact HTTP Basic header Intuit requires: base64(client_id:client_secret).
_EXPECTED_BASIC = "Basic " + base64.b64encode(b"qbo-cid-123:qbo-secret-456").decode()


class TestExchangeCode:
    async def test_exchange_posts_authorization_code_grant_with_basic_auth(self, monkeypatch) -> None:
        _FakeAsyncClient.posted = None
        monkeypatch.setattr(qbo_oauth.httpx, "AsyncClient", _FakeAsyncClient)
        tokens = await qbo_oauth.exchange_code(_settings(), code="ABC-CODE")
        assert tokens["refresh_token"] == "REFRESH_TOKEN"
        sent = _FakeAsyncClient.posted
        # Intuit's token endpoint, the authorization_code grant, and the redirect_uri round-trip.
        assert sent["url"] == "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
        assert sent["data"] == {
            "grant_type": "authorization_code",
            "code": "ABC-CODE",
            "redirect_uri": "https://api.example.com/v1/integrations/quickbooks/callback",
        }
        # QBO authenticates the client via HTTP Basic, NOT a body client_secret.
        assert sent["headers"]["Authorization"] == _EXPECTED_BASIC
        assert "client_secret" not in sent["data"]

    async def test_refresh_posts_refresh_token_grant_with_basic_auth(self, monkeypatch) -> None:
        _FakeAsyncClient.posted = None
        monkeypatch.setattr(qbo_oauth.httpx, "AsyncClient", _FakeAsyncClient)
        tokens = await qbo_oauth.refresh_access_token(_settings(), refresh_token="OLD-RT")
        assert tokens["access_token"] == "ACCESS_TOKEN"
        sent = _FakeAsyncClient.posted
        assert sent["url"] == "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
        assert sent["data"] == {"grant_type": "refresh_token", "refresh_token": "OLD-RT"}
        assert sent["headers"]["Authorization"] == _EXPECTED_BASIC

    async def test_exchange_requires_client_credentials(self) -> None:
        with pytest.raises(RuntimeError, match="QUICKBOOKS_CLIENT_ID and QUICKBOOKS_CLIENT_SECRET"):
            await qbo_oauth.exchange_code(_settings(quickbooks_client_id=None), code="c")


# --- routes_qbo_oauth: connect + callback (DB write + httpx both stubbed) --------------------------
import contextlib  # noqa: E402

from app.api import routes_qbo_oauth  # noqa: E402
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
    monkeypatch.setattr(routes_qbo_oauth, "get_settings", lambda: settings)

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

    monkeypatch.setattr(routes_qbo_oauth, "tenant_session", _fake_session)
    monkeypatch.setattr(routes_qbo_oauth.credentials, "store_credential", _fake_store)
    monkeypatch.setattr(routes_qbo_oauth.runs, "insert_audit", _fake_audit)
    return settings, captured


class TestConnectEndpoint:
    async def test_connect_returns_a_tenant_bound_authorize_url(self, _patched_route) -> None:
        settings, _ = _patched_route
        result = await routes_qbo_oauth.quickbooks_connect(principal=_admin())
        assert result["provider"] == "quickbooks"
        url = result["authorize_url"]
        assert url.startswith(settings.quickbooks_authorize_url + "?")
        # The state in the URL must validate back to the caller's tenant.
        state = url.split("state=", 1)[1].split("&", 1)[0]
        import urllib.parse

        decoded_state = urllib.parse.unquote(state)
        assert (
            oauth_state.validate_state(decoded_state, SECRET, now=int(__import__("time").time()))
            == str(TENANT_A)
        )

    async def test_connect_503_when_quickbooks_not_configured(self, monkeypatch) -> None:
        settings = _route_settings(quickbooks_client_id=None)
        monkeypatch.setattr(routes_qbo_oauth, "get_settings", lambda: settings)
        with pytest.raises(HTTPException) as exc:
            await routes_qbo_oauth.quickbooks_connect(principal=_admin())
        assert exc.value.status_code == 503


class TestCallbackEndpoint:
    async def test_callback_happy_path_encrypts_and_stores_refresh_token_and_realm(
        self, monkeypatch, _patched_route
    ) -> None:
        _settings_obj, captured = _patched_route
        state = oauth_state.generate_state(TENANT_A, SECRET, now=int(__import__("time").time()))

        async def _fake_exchange(_settings, *, code):
            assert code == "THE-CODE"
            return {"access_token": "AT", "refresh_token": "RT-xyz", "expires_in": 3600}

        monkeypatch.setattr(routes_qbo_oauth.qbo_oauth, "exchange_code", _fake_exchange)

        resp = await routes_qbo_oauth.quickbooks_callback(
            code="THE-CODE", state=state, realmId=REALM
        )
        assert resp.status_code == 302
        # Refresh token + realm id land in the vault for the BOUND tenant (A); realm id is also exposed
        # as non-secret metadata for the connections UI.
        assert captured["tenant_id"] == str(TENANT_A)
        assert captured["provider"] == "quickbooks"
        assert captured["secret"] == {"refresh_token": "RT-xyz", "realm_id": REALM}
        assert captured["metadata"] == {"realm_id": REALM}
        assert captured["audit"]["action"] == "connection.oauth.quickbooks"

    async def test_callback_friendly_redirect_when_user_declines(self, _patched_route) -> None:
        # Intuit sends ?error=access_denied with no code → a friendly redirect, never a 422.
        _settings_obj, captured = _patched_route
        resp = await routes_qbo_oauth.quickbooks_callback(error="access_denied")
        assert resp.status_code == 302
        assert resp.headers["location"] == "/?connected=quickbooks&status=cancelled"
        assert "secret" not in captured  # nothing stored on a decline

    async def test_callback_rejects_a_missing_realm_id(self, monkeypatch, _patched_route) -> None:
        _settings_obj, captured = _patched_route
        state = oauth_state.generate_state(TENANT_A, SECRET, now=int(__import__("time").time()))

        async def _boom(*_, **__):  # the exchange must never run without a realm id
            raise AssertionError("exchange must not run without realmId")

        monkeypatch.setattr(routes_qbo_oauth.qbo_oauth, "exchange_code", _boom)
        with pytest.raises(HTTPException) as exc:
            await routes_qbo_oauth.quickbooks_callback(code="c", state=state, realmId=None)
        assert exc.value.status_code == 400
        assert "realmId" in exc.value.detail
        assert "secret" not in captured

    async def test_callback_rejects_an_invalid_state_before_any_exchange(
        self, monkeypatch, _patched_route
    ) -> None:
        _settings_obj, captured = _patched_route
        called = {"exchange": False}

        async def _boom(*_, **__):  # the exchange must never run on a bad state
            called["exchange"] = True
            return {}

        monkeypatch.setattr(routes_qbo_oauth.qbo_oauth, "exchange_code", _boom)
        with pytest.raises(HTTPException) as exc:
            await routes_qbo_oauth.quickbooks_callback(
                code="c", state="forged-state", realmId=REALM
            )
        assert exc.value.status_code == 400
        assert called["exchange"] is False
        assert "secret" not in captured  # nothing was stored

    async def test_callback_rejects_a_state_bound_to_a_different_secret(
        self, monkeypatch, _patched_route
    ) -> None:
        # A state forged with an attacker secret must not validate → 400, no exchange, no store.
        _settings_obj, captured = _patched_route
        forged = oauth_state.generate_state(TENANT_A, "attacker-secret", now=int(__import__("time").time()))

        async def _boom(*_, **__):
            raise AssertionError("exchange must not run on a forged state")

        monkeypatch.setattr(routes_qbo_oauth.qbo_oauth, "exchange_code", _boom)
        with pytest.raises(HTTPException) as exc:
            await routes_qbo_oauth.quickbooks_callback(code="c", state=forged, realmId=REALM)
        assert exc.value.status_code == 400
        assert "secret" not in captured

    async def test_callback_fails_closed_when_token_exchange_errors(
        self, monkeypatch, _patched_route
    ) -> None:
        _settings_obj, captured = _patched_route
        state = oauth_state.generate_state(TENANT_A, SECRET, now=int(__import__("time").time()))

        async def _raise(*_, **__):
            raise RuntimeError("intuit 400 invalid_grant code already redeemed")  # must NOT leak

        monkeypatch.setattr(routes_qbo_oauth.qbo_oauth, "exchange_code", _raise)
        with pytest.raises(HTTPException) as exc:
            await routes_qbo_oauth.quickbooks_callback(code="c", state=state, realmId=REALM)
        assert exc.value.status_code == 502
        assert "invalid_grant" not in exc.value.detail  # provider error body never echoed
        assert "secret" not in captured

    async def test_callback_fails_closed_when_no_refresh_token_returned(
        self, monkeypatch, _patched_route
    ) -> None:
        _settings_obj, captured = _patched_route
        state = oauth_state.generate_state(TENANT_A, SECRET, now=int(__import__("time").time()))

        async def _no_refresh(*_, **__):
            return {"access_token": "AT", "expires_in": 3600}  # refresh_token missing

        monkeypatch.setattr(routes_qbo_oauth.qbo_oauth, "exchange_code", _no_refresh)
        with pytest.raises(HTTPException) as exc:
            await routes_qbo_oauth.quickbooks_callback(code="c", state=state, realmId=REALM)
        assert exc.value.status_code == 502
        assert "secret" not in captured

    async def test_callback_503_when_vault_not_configured(self, monkeypatch) -> None:
        settings = _route_settings(credential_encryption_key=None)
        monkeypatch.setattr(routes_qbo_oauth, "get_settings", lambda: settings)
        with pytest.raises(HTTPException) as exc:
            await routes_qbo_oauth.quickbooks_callback(code="c", state="x", realmId=REALM)
        assert exc.value.status_code == 503
