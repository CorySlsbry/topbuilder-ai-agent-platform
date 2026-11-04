"""End-to-end API test for the Collections agent: run, read back, propose a dunning step, confirm
tenant isolation (RLS). Requires Postgres (marked integration)."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.integration


async def _token(client: AsyncClient, slug: str) -> dict[str, str]:
    resp = await client.post("/auth/dev-token", json={"tenant_slug": slug})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def test_collections_run_propose_and_isolation() -> None:
    from app import db
    from app.main import app

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            apex = await _token(client, "apex")
            summit = await _token(client, "summit")

            run = await client.post("/v1/agents/collections/runs", headers=apex)
            assert run.status_code == 201, run.text
            body = run.json()
            assert body["agent"] == "collections"
            assert body["totals"]["customers"] >= 1
            # The headline pain: a real overdue A/R portfolio (>$400K) is being worked.
            assert body["totals"]["overdue_balance_usd"] > 400_000
            assert body["totals"]["customers_needing_action"] >= 1
            assert body["inputs_hash"]
            run_id = body["run_id"]

            latest = await client.get("/v1/agents/collections/runs/latest", headers=apex)
            assert latest.status_code == 200
            assert latest.json()["run_id"] == run_id

            # Pick an actionable customer (has a compliant channel) and PROPOSE a dunning step.
            actionable = next(
                c for c in body["worklist"]
                if c["status"] not in ("reconciled", "expecting_money") and c["dunning_channel"] != "none"
            )
            prop = await client.post(
                f"/v1/agents/collections/runs/{run_id}/dunning",
                headers=apex,
                json={"customer_id": actionable["customer_id"]},
            )
            assert prop.status_code == 201, prop.text
            action = prop.json()
            assert action["agent"] == "collections"
            assert action["kind"] in ("send_dunning_email", "send_dunning_sms", "place_dunning_call")
            assert action["status"] == "proposed"

            # A current/reconciled customer is refused (server-side param assembly guards it).
            reconciled = next((c for c in body["worklist"] if c["status"] == "reconciled"), None)
            if reconciled is not None:
                bad = await client.post(
                    f"/v1/agents/collections/runs/{run_id}/dunning",
                    headers=apex,
                    json={"customer_id": reconciled["customer_id"]},
                )
                assert bad.status_code == 400, bad.text

            # Cross-tenant: Summit can see neither Apex's run by id nor a "latest" of its own.
            assert (
                await client.get(f"/v1/agents/collections/runs/{run_id}", headers=summit)
            ).status_code == 404
            assert (
                await client.get("/v1/agents/collections/runs/latest", headers=summit)
            ).status_code == 404
    finally:
        await db.get_engine().dispose()
        db.get_engine.cache_clear()
        db.get_sessionmaker.cache_clear()
