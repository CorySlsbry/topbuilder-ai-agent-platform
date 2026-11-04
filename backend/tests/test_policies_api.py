"""End-to-end test for the per-agent autonomy switch (off | hitl | auto) + undo.

Proves the dial: off refuses execution, auto approves+executes a proposal autonomously, undo reverses
it — admin-gated, and tenant-isolated (a tenant never sees another's policy).
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings

pytestmark = pytest.mark.integration


def _enabled() -> Settings:
    return Settings(actions_enabled=True, servicetitan_mode="fixture", actions_allowed_kinds="book_appointment")


async def _token(client: AsyncClient, slug: str, role: str = "admin") -> dict[str, str]:
    resp = await client.post("/auth/dev-token", json={"tenant_slug": slug, "role": role})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _payload(intake_id: str) -> dict:
    return {
        "agent": "booking",
        "kind": "book_appointment",
        "params": {"intake_id": intake_id, "trade": "hvac", "proposed_date": "2026-06-09", "caller_name": "Jane"},
    }


async def test_per_agent_autonomy_off_auto_and_undo(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import db
    from app.main import app

    monkeypatch.setattr("app.actions.service.get_settings", _enabled)
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            admin = await _token(client, "apex", "admin")
            analyst = await _token(client, "apex", "analyst")
            summit = await _token(client, "summit", "admin")

            # Default policy is the safe 'hitl'.
            pol = await client.get("/v1/agents/policies/booking", headers=admin)
            assert pol.status_code == 200 and pol.json()["mode"] == "hitl"

            # Setting a policy is admin-only; invalid modes are rejected.
            assert (await client.put("/v1/agents/policies/booking", headers=analyst, json={"mode": "auto"})).status_code == 403
            assert (await client.put("/v1/agents/policies/booking", headers=admin, json={"mode": "nope"})).status_code == 400

            # --- OFF: advisory only; execution refused even after a human approves.
            assert (await client.put("/v1/agents/policies/booking", headers=admin, json={"mode": "off"})).status_code == 200
            a = (await client.post("/v1/actions", headers=analyst, json=_payload("OFF1"))).json()
            assert a["status"] == "proposed"
            await client.post(f"/v1/actions/{a['id']}/approve", headers=admin)
            assert (await client.post(f"/v1/actions/{a['id']}/execute", headers=admin)).status_code == 403

            # --- AUTO: proposing auto-approves + executes immediately (autonomous-with-undo).
            await client.put("/v1/agents/policies/booking", headers=admin, json={"mode": "auto"})
            auto = await client.post("/v1/actions", headers=analyst, json=_payload("AUTO1"))
            assert auto.status_code == 201, auto.text
            body = auto.json()
            assert body["status"] == "executed"          # no human approval step needed
            assert body["result"]["external_ref"] == "st-appt-AUTO1"
            assert body["approved_by"]                   # the system recorded an approver

            # Undo reverses the executed action.
            undone = await client.post(f"/v1/actions/{body['id']}/undo", headers=admin)
            assert undone.status_code == 200, undone.text
            assert undone.json()["status"] == "undone"
            assert undone.json()["result"]["undo"]["status"] == "canceled"
            # Idempotent undo.
            assert (await client.post(f"/v1/actions/{body['id']}/undo", headers=admin)).json()["status"] == "undone"

            # Tenant isolation: Summit sees its own default, never Apex's 'auto', and none of Apex's rows.
            assert (await client.get("/v1/agents/policies/booking", headers=summit)).json()["mode"] == "hitl"
            assert (await client.get("/v1/agents/policies", headers=summit)).json() == []
    finally:
        await db.get_engine().dispose()
        db.get_engine.cache_clear()
        db.get_sessionmaker.cache_clear()
