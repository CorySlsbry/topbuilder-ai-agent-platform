"""End-to-end API test: trigger a run, read it back, and confirm tenant isolation at the API layer.

Uses httpx's in-process ASGI transport against the real FastAPI app (real auth, real graph, real DB,
template narrative since no ANTHROPIC_API_KEY is set).
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.integration


async def _token(client: AsyncClient, slug: str) -> dict[str, str]:
    resp = await client.post("/auth/dev-token", json={"tenant_slug": slug})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def test_run_then_isolation_across_tenants() -> None:
    from app import db
    from app.main import app

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            apex = await _token(client, "apex")
            summit = await _token(client, "summit")

            # Trigger an Apex run. force=true makes this deterministic in the full suite:
            # it always creates a fresh (newest) run, so the "latest == this run" assert holds
            # regardless of what other integration tests left in the shared DB.
            run = await client.post(
                "/v1/agents/workforce/runs",
                params={"horizon_days": 21, "force": "true"},
                headers=apex,
            )
            assert run.status_code == 201, run.text
            body = run.json()
            assert body["agent"] == "workforce"
            assert body["inputs_hash"]
            assert body["totals"]["weeks_short"] >= 1
            assert body["totals"]["technicians_in_overtime"] >= 1
            run_id = body["run_id"]

            # Apex can read its own run (latest + by id).
            latest = await client.get("/v1/agents/workforce/runs/latest", headers=apex)
            assert latest.status_code == 200
            assert latest.json()["run_id"] == run_id

            by_id = await client.get(f"/v1/agents/workforce/runs/{run_id}", headers=apex)
            assert by_id.status_code == 200

            # Summit cannot see Apex's run, and has none of its own.
            assert (
                await client.get(f"/v1/agents/workforce/runs/{run_id}", headers=summit)
            ).status_code == 404
            assert (
                await client.get("/v1/agents/workforce/runs/latest", headers=summit)
            ).status_code == 404

            # Unauthenticated is rejected.
            assert (await client.get("/v1/agents/workforce/runs/latest")).status_code in (401, 403)
    finally:
        await db.get_engine().dispose()
        db.get_engine.cache_clear()
        db.get_sessionmaker.cache_clear()
