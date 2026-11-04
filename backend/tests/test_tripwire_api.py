"""DB-integration tests for tripwire order capture (tripwire_orders, migration 0029).

Proves the load-bearing guarantees against a real Postgres + RLS (mirrors test_support_api.py):
  * repository round-trip under operator_session (insert -> list -> mark_crm_synced);
  * idempotency — a second insert with the same stripe_session_id returns None (ON CONFLICT DO
    NOTHING) and does not add a row;
  * RLS 2-context — a row written under operator_session() is INVISIBLE to a tenant_session
    (app.operator unset -> the operator-only policy fails closed);
  * the operator authz gate on GET /v1/tripwires/orders — a non-operator admin gets 403, an
    operator 200.
"""
from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.db import operator_session, tenant_session
from app.demo import DEMO_TENANTS
from app.repositories import tripwires as tripwires_repo

pytestmark = pytest.mark.integration

_APEX = DEMO_TENANTS["apex"]
_OPERATOR_SETTINGS = Settings(platform_operator_emails=_APEX.admin_email)
_NON_OPERATOR_SETTINGS = Settings(platform_operator_emails="")


async def _admin_token(client: AsyncClient, slug: str = "apex") -> dict[str, str]:
    resp = await client.post("/auth/dev-token", json={"tenant_slug": slug, "role": "admin"})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _patch_gates(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> None:
    from app import config
    from app.api import routes_tripwires

    monkeypatch.setattr(config, "get_settings", lambda: settings)
    monkeypatch.setattr(routes_tripwires, "get_settings", lambda: settings)


class TestRepositoryRoundTrip:
    async def test_insert_list_and_mark_crm_synced(self) -> None:
        sid = f"cs_it_{uuid.uuid4().hex}"
        async with operator_session() as session:
            row = await tripwires_repo.insert_order(
                session,
                product_key="xray",
                stripe_session_id=sid,
                stripe_payment_intent="pi_it_1",
                stripe_event_id="evt_it_1",
                email="person1@example.com",
                name="Sam Buyer",
                amount_cents=9700,
                currency="usd",
                intake={"utm": "test"},
            )
            assert row is not None
            assert row["product_key"] == "xray"
            assert row["status"] == "paid"
            assert row["crm_synced_at"] is None
            assert row["intake"] == {"utm": "test"}

            listed = await tripwires_repo.list_orders(session, product_key="xray", limit=50)
            assert any(r["id"] == row["id"] for r in listed)

            await tripwires_repo.mark_crm_synced(session, row["id"])
            after = await tripwires_repo.list_orders(session, product_key="xray", limit=50)
            marked = next(r for r in after if r["id"] == row["id"])
            assert marked["crm_synced_at"] is not None

    async def test_duplicate_session_id_returns_none(self) -> None:
        sid = f"cs_dup_{uuid.uuid4().hex}"
        async with operator_session() as session:
            first = await tripwires_repo.insert_order(
                session, product_key="scorecard_trial", stripe_session_id=sid, amount_cents=2700
            )
            assert first is not None
            second = await tripwires_repo.insert_order(
                session, product_key="scorecard_trial", stripe_session_id=sid, amount_cents=2700
            )
            assert second is None  # idempotent: ON CONFLICT DO NOTHING


class TestRlsIsolation:
    async def test_row_is_invisible_to_a_tenant_session(self) -> None:
        sid = f"cs_rls_{uuid.uuid4().hex}"
        async with operator_session() as session:
            row = await tripwires_repo.insert_order(
                session, product_key="collections_sprint", stripe_session_id=sid, amount_cents=9700
            )
            assert row is not None
        async with tenant_session(_APEX.tenant_id) as tsession:
            from sqlalchemy import text

            seen = (
                await tsession.execute(
                    text("SELECT count(*) FROM tripwire_orders WHERE id = :id"), {"id": row["id"]}
                )
            ).scalar_one()
            assert seen == 0


class TestOperatorAuthz:
    async def test_non_operator_admin_gets_403_and_operator_gets_200(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        transport = ASGITransport(app=__import__("app.main", fromlist=["app"]).app)
        async with AsyncClient(transport=transport, base_url="http://t") as client:
            headers = await _admin_token(client)

            _patch_gates(monkeypatch, _NON_OPERATOR_SETTINGS)
            forbidden = await client.get("/v1/tripwires/orders", headers=headers)
            assert forbidden.status_code == 403

            _patch_gates(monkeypatch, _OPERATOR_SETTINGS)
            ok = await client.get("/v1/tripwires/orders", headers=headers)
            assert ok.status_code == 200
            assert "orders" in ok.json()
