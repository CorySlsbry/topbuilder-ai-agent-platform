"""End-to-end API test for the Email agent: run, read back, proposed actions, tenant isolation."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.integration


async def _token(client: AsyncClient, slug: str) -> dict[str, str]:
    resp = await client.post("/auth/dev-token", json={"tenant_slug": slug})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def test_email_run_actions_and_isolation() -> None:
    from app import db
    from app.main import app

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            apex = await _token(client, "apex")
            summit = await _token(client, "summit")

            run = await client.post("/v1/agents/email/runs", headers=apex)
            assert run.status_code == 201, run.text
            body = run.json()
            assert body["agent"] == "email"
            b = body["briefing"]
            assert b["unread_total"] == 26
            assert (b["needs_reply"], b["fyi"], b["trash_candidates"], b["workflow_reports"]) == (7, 6, 9, 4)
            assert b["needs_reply"] + b["fyi"] + b["trash_candidates"] + b["workflow_reports"] == b["unread_total"]
            assert b["top_priorities"][0]["email_id"] == "EM-3001"
            assert b["top_priorities"][0]["value_usd"] == 12400.0
            assert len(body["reply_drafts"]) == 7
            assert sum(1 for d in body["reply_drafts"] if d["requires_human"]) == 2
            assert len(body["trash_queue"]) == 9
            assert all(t["confidence"] >= 0.85 for t in body["trash_queue"])
            under = [w for w in body["workflows"] if w["status"] == "underperforming"]
            assert len(under) == 1 and under[0]["name"] == "Estimate follow-up"
            assert under[0]["proposed_rewrite"] is not None
            assert body["narration"] and body["inputs_hash"]
            run_id = body["run_id"]

            latest = await client.get("/v1/agents/email/runs/latest", headers=apex)
            assert latest.status_code == 200
            assert latest.json()["run_id"] == run_id

            # The run best-effort-proposed its writes through the action gate (ADR 0007):
            # 1 delete_emails + 5 send_email_reply (the non-held drafts) + 1 rewrite_workflow.
            actions = await client.get("/v1/actions", params={"agent": "email"}, headers=apex)
            assert actions.status_code == 200
            kinds = [a["kind"] for a in actions.json()]
            assert kinds.count("delete_emails") == 1
            assert kinds.count("send_email_reply") == 5
            assert kinds.count("rewrite_workflow") == 1
            by_kind = {a["kind"]: a for a in actions.json()}
            assert len(by_kind["delete_emails"]["params"]["email_ids"]) == 9
            assert len(by_kind["delete_emails"]["params"]["subjects"]) == 9
            assert all(a["status"] == "proposed" for a in actions.json())

            # Tenant isolation: summit sees neither the run nor the actions.
            assert (await client.get(f"/v1/agents/email/runs/{run_id}", headers=summit)).status_code == 404
            assert (await client.get("/v1/agents/email/runs/latest", headers=summit)).status_code == 404
            summit_actions = await client.get("/v1/actions", params={"agent": "email"}, headers=summit)
            assert summit_actions.status_code == 200 and summit_actions.json() == []

            # Cron endpoint: 404 when CRON_SECRET is not configured (the documented test env).
            assert (await client.post("/v1/agents/email/cron/daily")).status_code == 404
    finally:
        await db.get_engine().dispose()
        db.get_engine.cache_clear()
        db.get_sessionmaker.cache_clear()
