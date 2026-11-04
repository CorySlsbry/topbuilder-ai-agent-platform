"""End-to-end test for the human-approved action path (ADR 0007).

Proves: propose (maker) -> approve (admin checker) -> execute (admin), with the role gate, the
master-switch gate (off by default), idempotent propose + execute, and tenant isolation.
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings

pytestmark = pytest.mark.integration


async def _token(client: AsyncClient, slug: str, role: str = "admin") -> dict[str, str]:
    resp = await client.post("/auth/dev-token", json={"tenant_slug": slug, "role": role})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def test_action_propose_approve_execute(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import db
    from app.main import app

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            admin = await _token(client, "apex", "admin")
            analyst = await _token(client, "apex", "analyst")
            viewer = await _token(client, "apex", "viewer")
            summit = await _token(client, "summit", "admin")

            # A real booking run -> a proposed booking to act on.
            run = await client.post("/v1/agents/booking/runs?force=true", headers=admin)
            assert run.status_code == 201, run.text
            body = run.json()
            booking = body["proposed_bookings"][0]
            payload = {
                "agent": "booking",
                "kind": "book_appointment",
                "run_id": body["run_id"],
                "params": {
                    "intake_id": booking["intake_id"],
                    "trade": booking["trade"],
                    "proposed_date": booking["proposed_date"],
                    "caller_name": booking["caller_name"],
                },
            }

            # Viewer cannot propose (needs admin/analyst).
            assert (await client.post("/v1/actions", headers=viewer, json=payload)).status_code == 403

            # Analyst proposes -> 'proposed'. Proposing touches nothing external.
            r = await client.post("/v1/actions", headers=analyst, json=payload)
            assert r.status_code == 201, r.text
            action = r.json()
            assert action["status"] == "proposed"
            action_id = action["id"]

            # Idempotent propose -> same action id (nothing duplicated).
            r2 = await client.post("/v1/actions", headers=analyst, json=payload)
            assert r2.status_code == 201
            assert r2.json()["id"] == action_id

            # Approval is admin-only — the maker (analyst) cannot approve their own action.
            assert (await client.post(f"/v1/actions/{action_id}/approve", headers=analyst)).status_code == 403

            # Admin approves -> 'approved'; re-approve is idempotent.
            r = await client.post(f"/v1/actions/{action_id}/approve", headers=admin)
            assert r.status_code == 200, r.text
            assert r.json()["status"] == "approved"
            assert r.json()["approved_by"]
            assert (await client.post(f"/v1/actions/{action_id}/approve", headers=admin)).json()["status"] == "approved"

            # Execute is blocked while actions are disabled (the default) -> 403; action stays 'approved'.
            blocked = await client.post(f"/v1/actions/{action_id}/execute", headers=admin)
            assert blocked.status_code == 403
            assert (await client.get(f"/v1/actions/{action_id}", headers=admin)).json()["status"] == "approved"

            # Opt in (master switch) and execute -> the (fixture) write happens, idempotently.
            monkeypatch.setattr(
                "app.actions.service.get_settings",
                lambda: Settings(actions_enabled=True, servicetitan_mode="fixture", actions_allowed_kinds="book_appointment"),
            )
            r = await client.post(f"/v1/actions/{action_id}/execute", headers=admin)
            assert r.status_code == 200, r.text
            done = r.json()
            assert done["status"] == "executed"
            assert done["result"]["external_ref"] == f"st-appt-{booking['intake_id']}"
            assert done["executed_at"]

            again = await client.post(f"/v1/actions/{action_id}/execute", headers=admin)
            assert again.status_code == 200
            assert again.json()["result"]["external_ref"] == done["result"]["external_ref"]

            # Tenant isolation: Summit can neither see nor act on Apex's action.
            assert (await client.get(f"/v1/actions/{action_id}", headers=summit)).status_code == 404
            assert (await client.post(f"/v1/actions/{action_id}/approve", headers=summit)).status_code == 404
            assert (await client.post(f"/v1/actions/{action_id}/execute", headers=summit)).status_code == 404
    finally:
        await db.get_engine().dispose()
        db.get_engine.cache_clear()
        db.get_sessionmaker.cache_clear()
