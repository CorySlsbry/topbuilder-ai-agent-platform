"""Idempotency: an identical run (same inputs_hash) returns the SAME run; `force` makes a new one."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.integration


async def _token(client: AsyncClient, slug: str) -> dict[str, str]:
    resp = await client.post("/auth/dev-token", json={"tenant_slug": slug})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def test_runs_dedupe_by_inputs_hash() -> None:
    from app import db
    from app.main import app

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            apex = await _token(client, "apex")

            r1 = await client.post("/v1/agents/inventory/runs", headers=apex)
            r2 = await client.post("/v1/agents/inventory/runs", headers=apex)
            assert r1.status_code == 201 and r2.status_code == 201
            assert r1.json()["run_id"] == r2.json()["run_id"]  # idempotent

            forced = await client.post(
                "/v1/agents/inventory/runs", headers=apex, params={"force": "true"}
            )
            assert forced.status_code == 201
            assert forced.json()["run_id"] != r1.json()["run_id"]  # bypassed
    finally:
        await db.get_engine().dispose()
        db.get_engine.cache_clear()
        db.get_sessionmaker.cache_clear()
