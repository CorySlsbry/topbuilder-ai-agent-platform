"""End-to-end API test for the Inventory agent: run, read back, confirm tenant isolation."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.integration


async def _token(client: AsyncClient, slug: str) -> dict[str, str]:
    resp = await client.post("/auth/dev-token", json={"tenant_slug": slug})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def test_inventory_run_and_isolation() -> None:
    from app import db
    from app.main import app

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            apex = await _token(client, "apex")
            summit = await _token(client, "summit")

            run = await client.post("/v1/agents/inventory/runs", headers=apex)
            assert run.status_code == 201, run.text
            body = run.json()
            assert body["agent"] == "inventory"
            assert body["totals"]["reorders_count"] >= 1
            assert len(body["vendor_arbitrage"]) >= 1
            assert body["inputs_hash"]
            run_id = body["run_id"]

            latest = await client.get("/v1/agents/inventory/runs/latest", headers=apex)
            assert latest.status_code == 200
            assert latest.json()["run_id"] == run_id

            assert (
                await client.get(f"/v1/agents/inventory/runs/{run_id}", headers=summit)
            ).status_code == 404
            assert (
                await client.get("/v1/agents/inventory/runs/latest", headers=summit)
            ).status_code == 404
    finally:
        await db.get_engine().dispose()
        db.get_engine.cache_clear()
        db.get_sessionmaker.cache_clear()
