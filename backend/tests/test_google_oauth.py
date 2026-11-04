"""Pure tests for the Google (Drive / Sheets) Authorization-Code OAuth onboarding.

Mirrors test_procore_oauth.py. Three surfaces, all infra-free (the DB write is monkeypatched, httpx
is stubbed):
  1. oauth_state — the SHARED tenant-bound HMAC state (re-used, not duplicated): a generate→validate
     round-trip that proves the Google connect URL binds to the caller's tenant.
  2. google_oauth — the authorize-URL builder (offline + consent + scopes) + the code→tokens exchange
     (httpx mocked) + best-effort resolve_user_email.
  3. routes_google_oauth — the connect URL is admin-gated + tenant-bound, and the callback validates
     state, exchanges the code, ENCRYPTS+stores the refresh token (with email + granted scopes as
     metadata), and fails closed on a bad state / a token-exchange error / a missing refresh token.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from app.config import Settings
from app.integrations.construction import oauth_state
from app.integrations.google import google_oauth

TENANT_A = uuid.UUID("11111111-1111-1111-1111-111111111111")
TENANT_B = uuid.UUID("22222222-2222-2222-2222-222222222222")
SECRET = "a-32-byte-min-signing-secret-for-tests-only-0123456789"
NOW = 1_700_000_000  # a fixed epoch so expiry math is deterministic


# --- oauth_state binding (the shared module already has full coverage in test_procore_oauth.py; here
#     we only re-assert the round-trip that the Google connect URL relies on) -----------------------
class TestSharedStateBinding:
    def test_generate_then_validate_recovers_the_bound_tenant(self) -> None:
        state = oauth_state.generate_state(TENANT_A, SECRET, now=NOW)
        assert oauth_state.validate_state(state, SECRET, now=NOW) == str(TENANT_A)

    def test_state_minted_for_one_tenant_cannot_be_reused_for_another(self) -> None:
        # A state minted for tenant A validates back ONLY to tenant A — never B (no cross-tenant link).
        state = oauth_state.generate_state(TENANT_A, SECRET, now=NOW)
        assert oauth_state.validate_state(state, SECRET, now=NOW) != str(TENANT_B)


# --- google_oauth: authorize URL + token exchange ------------------------------------------------
def _settings(**over) -> Settings:
    base = dict(
        google_client_id="gcid-123",
        google_client_secret="gsecret-456",
        google_redirect_uri="https://api.example.com/v1/integrations/google/callback",
        google_scopes=(
            "https://www.googleapis.com/auth/drive.readonly "
            "https://www.googleapis.com/auth/spreadsheets.readonly"
        ),
        google_authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        google_token_url="https://oauth2.googleapis.com/token",
        google_userinfo_url="https://www.googleapis.com/oauth2/v3/userinfo",
        credential_encryption_key=None,
    )
    base.update(over)
    return Settings(**base)


class TestAuthorizeUrl:
    def test_builds_the_authorize_url_with_all_required_params(self) -> None:
        url = google_oauth.build_authorize_url(_settings(), state="STATE123")
        assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
        for fragment in (
            "response_type=code",
            "client_id=gcid-123",
            "state=STATE123",
            # Google requires offline + consent to return a refresh token.
            "access_type=offline",
            "prompt=consent",
            # redirect_uri is URL-encoded in the query string.
            "redirect_uri=https%3A%2F%2Fapi.example.com%2Fv1%2Fintegrations%2Fgoogle%2Fcallback",
        ):
            assert fragment in url

    def test_authorize_url_encodes_the_configured_scopes(self) -> None:
        url = google_oauth.build_authorize_url(_settings(), state="s")
        # Space-delimited scopes are URL-encoded (space -> %20 or +) and both scopes are present.
        assert "drive.readonly" in url
        assert "spreadsheets.readonly" in url

    def test_authorize_url_honors_an_explicit_scope_override(self) -> None:
        url = google_oauth.build_authorize_url(
            _settings(), state="s", scopes=["https://www.googleapis.com/auth/drive.readonly"]
        )
        assert "drive.readonly" in url
        assert "spreadsheets.readonly" not in url

    def test_authorize_url_requires_a_client_id(self) -> None:
        with pytest.raises(RuntimeError, match="GOOGLE_CLIENT_ID"):
            google_oauth.build_authorize_url(_settings(google_client_id=None), state="s")

    def test_authorize_url_requires_a_redirect_uri(self) -> None:
        with pytest.raises(RuntimeError, match="GOOGLE_REDIRECT_URI"):
            google_oauth.build_authorize_url(_settings(google_redirect_uri=None), state="s")


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
            "expires_in": 3599,
            "scope": "https://www.googleapis.com/auth/drive.readonly",
        })


class TestExchangeCode:
    async def test_exchange_posts_authorization_code_grant_and_returns_tokens(self, monkeypatch) -> None:
        _FakeAsyncClient.posted = None
        monkeypatch.setattr(google_oauth.httpx, "AsyncClient", _FakeAsyncClient)
        tokens = await google_oauth.exchange_code(_settings(), code="ABC-CODE")
        assert tokens["refresh_token"] == "REFRESH_TOKEN"
        sent = _FakeAsyncClient.posted
        assert sent["url"] == "https://oauth2.googleapis.com/token"
        assert sent["data"] == {
            "grant_type": "authorization_code",
            "client_id": "gcid-123",
            "client_secret": "gsecret-456",
            "code": "ABC-CODE",
            "redirect_uri": "https://api.example.com/v1/integrations/google/callback",
        }

    async def test_exchange_requires_client_credentials(self) -> None:
        with pytest.raises(RuntimeError, match="GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET"):
            await google_oauth.exchange_code(_settings(google_client_id=None), code="c")


class _FakeUserinfoClient:
    """Returns a canned userinfo response for resolve_user_email."""

    def __init__(self, *_, **__) -> None:
        pass

    async def __aenter__(self) -> "_FakeUserinfoClient":
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    async def get(self, url, headers=None):  # noqa: ANN001
        return _FakeResponse({"email": "person1@example.com", "email_verified": True})


class _BoomUserinfoClient(_FakeUserinfoClient):
    async def get(self, url, headers=None):  # noqa: ANN001
        raise RuntimeError("userinfo scope not granted")


class TestResolveUserEmail:
    async def test_returns_the_email_on_success(self, monkeypatch) -> None:
        monkeypatch.setattr(google_oauth.httpx, "AsyncClient", _FakeUserinfoClient)
        email = await google_oauth.resolve_user_email(_settings(), access_token="AT")
        assert email == "person1@example.com"

    async def test_returns_none_when_the_userinfo_read_fails(self, monkeypatch) -> None:
        # A convenience read — a failure must NOT break the connect flow (returns None, not raises).
        monkeypatch.setattr(google_oauth.httpx, "AsyncClient", _BoomUserinfoClient)
        email = await google_oauth.resolve_user_email(_settings(), access_token="AT")
        assert email is None


# --- routes_google_oauth: connect + callback (DB write + httpx both stubbed) ----------------------
import base64  # noqa: E402
import contextlib  # noqa: E402

from app.api import routes_google_oauth  # noqa: E402
from app.security import Principal  # noqa: E402

# A real urlsafe-b64 32-byte AES-256 key so the vault cipher initializes in the callback happy path.
_AES_KEY = base64.urlsafe_b64encode(b"\x11" * 32).decode()


def _route_settings(**over) -> Settings:
    over.setdefault("credential_encryption_key", _AES_KEY)
    return _settings(jwt_secret=SECRET, **over)


def _admin(tenant=TENANT_A) -> Principal:
    return Principal(
        tenant_id=tenant, user_id=uuid.uuid4(), email="person2@example.com", role="admin", aal="aal2"
    )


@pytest.fixture
def _patched_route(monkeypatch):
    """Patch the route's settings + capture what gets written to the vault, with no DB."""
    settings = _route_settings()
    monkeypatch.setattr(routes_google_oauth, "get_settings", lambda: settings)

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

    monkeypatch.setattr(routes_google_oauth, "tenant_session", _fake_session)
    monkeypatch.setattr(routes_google_oauth.credentials, "store_credential", _fake_store)
    monkeypatch.setattr(routes_google_oauth.runs, "insert_audit", _fake_audit)
    return settings, captured


class TestConnectEndpoint:
    async def test_connect_returns_a_tenant_bound_authorize_url(self, _patched_route) -> None:
        settings, _ = _patched_route
        result = await routes_google_oauth.google_connect(principal=_admin())
        assert result["provider"] == "google"
        url = result["authorize_url"]
        assert url.startswith(settings.google_authorize_url + "?")
        # The state in the URL must validate back to the caller's tenant.
        state = url.split("state=", 1)[1].split("&", 1)[0]
        import urllib.parse

        decoded_state = urllib.parse.unquote(state)
        assert (
            oauth_state.validate_state(decoded_state, SECRET, now=int(__import__("time").time()))
            == str(TENANT_A)
        )

    async def test_connect_503_when_google_not_configured(self, monkeypatch) -> None:
        settings = _route_settings(google_client_id=None)
        monkeypatch.setattr(routes_google_oauth, "get_settings", lambda: settings)
        with pytest.raises(HTTPException) as exc:
            await routes_google_oauth.google_connect(principal=_admin())
        assert exc.value.status_code == 503


class TestCallbackEndpoint:
    async def test_callback_happy_path_encrypts_and_stores_the_refresh_token(
        self, monkeypatch, _patched_route
    ) -> None:
        _settings_obj, captured = _patched_route
        # A valid state for tenant A + a stubbed exchange returning a refresh token.
        state = oauth_state.generate_state(TENANT_A, SECRET, now=int(__import__("time").time()))

        async def _fake_exchange(_settings, *, code):
            assert code == "THE-CODE"
            return {
                "access_token": "AT",
                "refresh_token": "RT-xyz",
                "expires_in": 3599,
                "scope": "https://www.googleapis.com/auth/spreadsheets.readonly",
            }

        async def _fake_email(_settings, *, access_token):
            return "person1@example.com"

        monkeypatch.setattr(routes_google_oauth.google_oauth, "exchange_code", _fake_exchange)
        monkeypatch.setattr(routes_google_oauth.google_oauth, "resolve_user_email", _fake_email)

        resp = await routes_google_oauth.google_callback(code="THE-CODE", state=state)
        assert resp.status_code == 302
        # The refresh token landed in the vault for the BOUND tenant (A); the SECRET holds ONLY the
        # refresh token, while email + granted scopes are non-secret metadata.
        assert captured["tenant_id"] == str(TENANT_A)
        assert captured["provider"] == "google"
        assert captured["secret"] == {"refresh_token": "RT-xyz"}
        assert captured["metadata"] == {
            "email": "person1@example.com",
            "scopes": "https://www.googleapis.com/auth/spreadsheets.readonly",
        }
        assert captured["audit"]["action"] == "connection.oauth.google"

    async def test_callback_rejects_an_invalid_state_before_any_exchange(
        self, monkeypatch, _patched_route
    ) -> None:
        _settings_obj, captured = _patched_route
        called = {"exchange": False}

        async def _boom(*_, **__):  # the exchange must never run on a bad state
            called["exchange"] = True
            return {}

        monkeypatch.setattr(routes_google_oauth.google_oauth, "exchange_code", _boom)
        with pytest.raises(HTTPException) as exc:
            await routes_google_oauth.google_callback(code="c", state="forged-state")
        assert exc.value.status_code == 400
        assert called["exchange"] is False
        assert "secret" not in captured  # nothing was stored

    async def test_callback_rejects_a_state_bound_to_a_different_secret(
        self, monkeypatch, _patched_route
    ) -> None:
        # A state forged with an attacker secret must not validate -> 400, no exchange, no store.
        _settings_obj, captured = _patched_route
        forged = oauth_state.generate_state(TENANT_A, "attacker-secret", now=int(__import__("time").time()))

        async def _boom(*_, **__):
            raise AssertionError("exchange must not run on a forged state")

        monkeypatch.setattr(routes_google_oauth.google_oauth, "exchange_code", _boom)
        with pytest.raises(HTTPException) as exc:
            await routes_google_oauth.google_callback(code="c", state=forged)
        assert exc.value.status_code == 400
        assert "secret" not in captured

    async def test_callback_fails_closed_when_token_exchange_errors(
        self, monkeypatch, _patched_route
    ) -> None:
        _settings_obj, captured = _patched_route
        state = oauth_state.generate_state(TENANT_A, SECRET, now=int(__import__("time").time()))

        async def _raise(*_, **__):
            raise RuntimeError("google 400 invalid_grant code already redeemed")  # must NOT leak

        monkeypatch.setattr(routes_google_oauth.google_oauth, "exchange_code", _raise)
        with pytest.raises(HTTPException) as exc:
            await routes_google_oauth.google_callback(code="c", state=state)
        assert exc.value.status_code == 502
        assert "invalid_grant" not in exc.value.detail  # provider error body never echoed
        assert "secret" not in captured

    async def test_callback_fails_closed_when_no_refresh_token_returned(
        self, monkeypatch, _patched_route
    ) -> None:
        _settings_obj, captured = _patched_route
        state = oauth_state.generate_state(TENANT_A, SECRET, now=int(__import__("time").time()))

        async def _no_refresh(*_, **__):
            return {"access_token": "AT", "expires_in": 3599}  # refresh_token missing

        monkeypatch.setattr(routes_google_oauth.google_oauth, "exchange_code", _no_refresh)
        with pytest.raises(HTTPException) as exc:
            await routes_google_oauth.google_callback(code="c", state=state)
        assert exc.value.status_code == 502
        assert "secret" not in captured

    async def test_callback_503_when_vault_not_configured(self, monkeypatch) -> None:
        settings = _route_settings(credential_encryption_key=None)
        monkeypatch.setattr(routes_google_oauth, "get_settings", lambda: settings)
        with pytest.raises(HTTPException) as exc:
            await routes_google_oauth.google_callback(code="c", state="x")
        assert exc.value.status_code == 503
