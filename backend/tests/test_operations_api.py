"""End-to-end test for the front-desk layer: communications + tasks (seed-on-read, 2-way send, RLS)."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.integration


async def _token(client: AsyncClient, slug: str) -> dict[str, str]:
    resp = await client.post("/auth/dev-token", json={"tenant_slug": slug})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def test_communications_and_tasks() -> None:
    from app import db
    from app.main import app

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            apex = await _token(client, "apex")
            summit = await _token(client, "summit")

            # Inbox seeds on first read, across all channels.
            comms = (await client.get("/v1/communications", headers=apex)).json()
            assert len(comms) >= 9
            assert {c["channel"] for c in comms} >= {"call", "sms", "email", "voicemail", "web"}

            calls = (await client.get("/v1/communications?channel=call", headers=apex)).json()
            assert calls and all(c["channel"] == "call" for c in calls)

            # 2-way send (outbound).
            sent = await client.post(
                "/v1/communications", headers=apex,
                json={"channel": "sms", "contact_name": "Test", "contact_phone": "+10000000000",
                      "subject": "APEX-PING", "body": "On our way."},
            )
            assert sent.status_code == 201, sent.text
            assert sent.json()["direction"] == "outbound" and sent.json()["status"] == "sent"

            # Worklist seeds; highest priority first; ties agents together.
            tasks = (await client.get("/v1/tasks", headers=apex)).json()
            assert len(tasks) >= 7
            assert tasks[0]["priority"] == 9
            assert {t["source_agent"] for t in tasks} >= {"booking", "routing"}

            # Create + complete a task.
            t = (await client.post("/v1/tasks", headers=apex,
                                   json={"title": "APEX-TASK", "department": "front_desk", "priority": 7})).json()
            done = await client.patch(f"/v1/tasks/{t['id']}", headers=apex, json={"status": "done"})
            assert done.status_code == 200 and done.json()["status"] == "done"

            # Tenant isolation: Summit seeds its OWN inbox/worklist, never Apex's ping or task.
            scomms = (await client.get("/v1/communications", headers=summit)).json()
            assert all(c["subject"] != "APEX-PING" for c in scomms)
            stasks = (await client.get("/v1/tasks", headers=summit)).json()
            assert all(t["title"] != "APEX-TASK" for t in stasks)
    finally:
        await db.get_engine().dispose()
        db.get_engine.cache_clear()
        db.get_sessionmaker.cache_clear()
