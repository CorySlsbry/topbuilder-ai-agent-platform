"""Route-gate tests for the tripwire Stripe webhook + orders list — everything that fires BEFORE
any DB access, so they run in the pure suite (no Postgres).

Covered:
  - POST /v1/tripwires/stripe/webhook is DARK (404) until stripe_webhook_secret is configured;
  - a bad / missing Stripe-Signature is a 400 (Stripe will retry — that's correct for a bad sig);
  - a VALID signature on an unhandled event type returns 200 {'received': true} (ack, no work);
  - a poison event AFTER a valid signature can NEVER 500: catch-all -> 200 'error-logged'
    (a non-2xx would make Stripe retry a permanently-broken event forever);
  - GET /v1/tripwires/orders requires auth (401/403 anonymous).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings

SECRET = "whsec_route_test_secret"


@pytest.fixture()
def client() -> TestClient:
    return TestClient(__import__("app.main", fromlist=["app"]).app, raise_server_exceptions=False)


def _sig_header(body: bytes, secret: str = SECRET, ts: int | None = None) -> str:
    ts = int(time.time()) if ts is None else ts
    mac = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={ts},v1={mac}"


def _arm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configure the webhook secret on the (cached) settings object."""
    monkeypatch.setattr(get_settings(), "stripe_webhook_secret", SECRET, raising=False)


class TestWebhookGates:
    def test_404_when_secret_unset(self, client: TestClient) -> None:
        # Default dev settings carry no stripe_webhook_secret -> the endpoint hides itself,
        # mirroring the cron-gate style.
        resp = client.post("/v1/tripwires/stripe/webhook", content=b"{}")
        assert resp.status_code == 404

    def test_400_on_missing_signature(self, client: TestClient, monkeypatch) -> None:
        _arm(monkeypatch)
        resp = client.post("/v1/tripwires/stripe/webhook", content=b"{}")
        assert resp.status_code == 400

    def test_400_on_bad_signature(self, client: TestClient, monkeypatch) -> None:
        _arm(monkeypatch)
        body = b'{"type":"checkout.session.completed"}'
        resp = client.post(
            "/v1/tripwires/stripe/webhook",
            content=body,
            headers={"Stripe-Signature": _sig_header(body, secret="whsec_wrong")},
        )
        assert resp.status_code == 400

    def test_400_on_stale_signature(self, client: TestClient, monkeypatch) -> None:
        _arm(monkeypatch)
        body = b'{"type":"ping"}'
        stale = int(time.time()) - 3600
        resp = client.post(
            "/v1/tripwires/stripe/webhook",
            content=body,
            headers={"Stripe-Signature": _sig_header(body, ts=stale)},
        )
        assert resp.status_code == 400

    def test_200_valid_sig_unhandled_event_type(self, client: TestClient, monkeypatch) -> None:
        _arm(monkeypatch)
        body = json.dumps({"id": "evt_x", "type": "invoice.paid", "data": {"object": {}}}).encode()
        resp = client.post(
            "/v1/tripwires/stripe/webhook",
            content=body,
            headers={"Stripe-Signature": _sig_header(body)},
        )
        assert resp.status_code == 200
        assert resp.json()["received"] is True

    def test_poison_body_after_valid_sig_is_200_error_logged(
        self, client: TestClient, monkeypatch
    ) -> None:
        # Signature verification is forced True; the body is not even JSON. Stripe retries on any
        # non-2xx, so a poison event must resolve to 200 with the error logged — never a 500 loop.
        _arm(monkeypatch)
        from app.api import routes_tripwires

        monkeypatch.setattr(routes_tripwires.stripe_sig, "verify", lambda *a, **k: True)
        resp = client.post(
            "/v1/tripwires/stripe/webhook",
            content=b"\xff\xfenot json at all",
            headers={"Stripe-Signature": "t=1,v1=forced"},
        )
        assert resp.status_code == 200
        assert resp.json().get("status") == "error-logged"

    def test_handler_explosion_after_valid_sig_is_200_error_logged(
        self, client: TestClient, monkeypatch
    ) -> None:
        _arm(monkeypatch)
        from app.api import routes_tripwires

        async def boom(event, settings):
            raise RuntimeError("poison event")

        monkeypatch.setattr(routes_tripwires.service, "handle_checkout_completed", boom)
        body = json.dumps(
            {
                "id": "evt_x",
                "type": "checkout.session.completed",
                "data": {"object": {"id": "cs_1"}},
            }
        ).encode()
        resp = client.post(
            "/v1/tripwires/stripe/webhook",
            content=body,
            headers={"Stripe-Signature": _sig_header(body)},
        )
        assert resp.status_code == 200
        assert resp.json().get("status") == "error-logged"


class TestOrdersGate:
    def test_orders_rejects_unauthenticated(self, client: TestClient) -> None:
        # HTTPBearer(auto_error=True): 403 on a missing credential, 401 on an invalid one.
        assert client.get("/v1/tripwires/orders").status_code in (401, 403)
