"""End-to-end API test for the Documents agent: run, read back, confirm tenant isolation."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.integration


async def _token(client: AsyncClient, slug: str) -> dict[str, str]:
    resp = await client.post("/auth/dev-token", json={"tenant_slug": slug})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def test_documents_run_and_isolation() -> None:
    from app import db
    from app.main import app

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            apex = await _token(client, "apex")
            summit = await _token(client, "summit")

            run = await client.post("/v1/agents/documents/runs", headers=apex)
            assert run.status_code == 201, run.text
            body = run.json()
            assert body["agent"] == "documents"
            t = body["totals"]
            assert t["documents_processed"] == 12
            assert t["auto_filed"] + t["needs_signature"] + t["needs_human"] == t["documents_processed"]
            assert t["auto_filed"] >= 8
            assert t["needs_signature"] >= 1
            assert t["needs_human"] >= 2
            assert t["expiring_soon"] >= 1
            assert t["extracted_value_usd"] > 0
            # Every filing routes to a customer + a ServiceTitan folder.
            assert all(f["customer_ref"] and f["st_folder"] for f in body["filings"])
            assert any("customer" in u["reason"].lower() for u in body["needs_human"])
            assert body["inputs_hash"]
            run_id = body["run_id"]

            latest = await client.get("/v1/agents/documents/runs/latest", headers=apex)
            assert latest.status_code == 200
            assert latest.json()["run_id"] == run_id

            assert (await client.get(f"/v1/agents/documents/runs/{run_id}", headers=summit)).status_code == 404
            assert (await client.get("/v1/agents/documents/runs/latest", headers=summit)).status_code == 404
    finally:
        await db.get_engine().dispose()
        db.get_engine.cache_clear()
        db.get_sessionmaker.cache_clear()
