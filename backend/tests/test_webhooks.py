"""Webhook signature verification (unit) + receiver enqueue/isolation (integration)."""
from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient

from app.webhooks import (
    compute_signature,
    verify_signature,
    verify_webhook,
    webhook_signature,
)

SECRET = "test-webhook-secret"  # must match WEBHOOK_SIGNING_SECRET in the test env
TENANT_A = "11111111-1111-1111-1111-111111111111"
TENANT_B = "22222222-2222-2222-2222-222222222222"
NOW = 1_800_000_000.0


class TestSignature:
    def test_legacy_roundtrip(self) -> None:
        body = b'{"event":"x"}'
        assert verify_signature(body, compute_signature(body, SECRET), SECRET)

    def test_legacy_rejects_tampered_or_missing(self) -> None:
        assert not verify_signature(b'{"a":1}', "deadbeef", SECRET)
        assert not verify_signature(b"{}", "", SECRET)
        assert not verify_signature(b"{}", "anything", "")


class TestTenantBoundWebhook:
    """SEC-4: the MAC binds tenant_id + timestamp -> no cross-tenant replay, no stale replay."""

    def _signed(self, tenant: str, ts: str, body: bytes) -> str:
        return webhook_signature(tenant, ts, body, SECRET)

    def test_valid_within_window(self) -> None:
        body = b'{"eventType":"job.completed","id":"evt-1"}'
        sig = self._signed(TENANT_A, str(int(NOW)), body)
        ok, _ = verify_webhook(tenant_id=TENANT_A, timestamp=str(int(NOW)), body=body,
                               signature=sig, secret=SECRET, now=NOW)
        assert ok

    def test_signature_for_tenant_a_rejected_at_tenant_b(self) -> None:
        body = b'{"id":"evt-1"}'
        sig = self._signed(TENANT_A, str(int(NOW)), body)  # signed FOR tenant A
        ok, reason = verify_webhook(tenant_id=TENANT_B, timestamp=str(int(NOW)), body=body,
                                    signature=sig, secret=SECRET, now=NOW)
        assert not ok and "invalid signature" in reason

    def test_stale_timestamp_rejected(self) -> None:
        body = b'{"id":"evt-1"}'
        old = str(int(NOW - 10_000))
        sig = self._signed(TENANT_A, old, body)  # correctly signed but too old
        ok, reason = verify_webhook(tenant_id=TENANT_A, timestamp=old, body=body,
                                    signature=sig, secret=SECRET, now=NOW)
        assert not ok and "window" in reason

    def test_missing_inputs_fail_closed(self) -> None:
        body = b"{}"
        assert not verify_webhook(tenant_id=TENANT_A, timestamp=None, body=body,
                                  signature="x", secret=SECRET, now=NOW)[0]
        assert not verify_webhook(tenant_id=TENANT_A, timestamp=str(int(NOW)), body=body,
                                  signature=None, secret=SECRET, now=NOW)[0]
        assert not verify_webhook(tenant_id=TENANT_A, timestamp=str(int(NOW)), body=body,
                                  signature="x", secret="", now=NOW)[0]


async def _token(client: AsyncClient, slug: str) -> dict[str, str]:
    resp = await client.post("/auth/dev-token", json={"tenant_slug": slug})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.mark.integration
async def test_webhook_enqueue_signature_and_isolation() -> None:
    from app import db
    from app.demo import DEMO_TENANTS
    from app.main import app

    import time

    apex_id = DEMO_TENANTS["apex"].tenant_id
    body = json.dumps({"eventType": "job.completed", "id": "evt-1"}).encode()
    ts = str(int(time.time()))
    sig = webhook_signature(str(apex_id), ts, body, SECRET)
    sig_headers = {"X-Signature": sig, "X-Timestamp": ts, "Content-Type": "application/json"}
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            ok = await client.post(
                f"/v1/webhooks/servicetitan/{apex_id}", content=body, headers=sig_headers,
            )
            assert ok.status_code == 202, ok.text
            assert ok.json()["status"] == "queued"

            # replay of the SAME signed event is idempotent (deduped), not a second row
            dup = await client.post(
                f"/v1/webhooks/servicetitan/{apex_id}", content=body, headers=sig_headers,
            )
            assert dup.status_code == 202 and dup.json()["status"] == "duplicate_ignored"

            bad = await client.post(
                f"/v1/webhooks/servicetitan/{apex_id}", content=body,
                headers={"X-Signature": "bad", "X-Timestamp": ts},
            )
            assert bad.status_code == 401

            # the apex-signed event must NOT validate against summit's path (cross-tenant replay)
            summit_id = DEMO_TENANTS["summit"].tenant_id
            cross = await client.post(
                f"/v1/webhooks/servicetitan/{summit_id}", content=body, headers=sig_headers,
            )
            assert cross.status_code == 401

            apex = await _token(client, "apex")
            events = (await client.get("/v1/webhooks/events", headers=apex)).json()
            assert sum(1 for e in events if e["external_id"] == "evt-1") == 1  # exactly one, not two

            summit = await _token(client, "summit")
            assert (await client.get("/v1/webhooks/events", headers=summit)).json() == []
    finally:
        await db.get_engine().dispose()
        db.get_engine.cache_clear()
        db.get_sessionmaker.cache_clear()
