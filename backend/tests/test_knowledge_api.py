"""RAG Learn module end-to-end: ingest -> list -> semantic search, agent + tenant scoped."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.integration

DOC = (
    "Our overtime policy caps technicians at 45 billable hours per week before premium pay applies. "
    "Dispatch should balance HVAC installs across the crew to avoid burnout."
)


async def _token(client: AsyncClient, slug: str) -> dict[str, str]:
    resp = await client.post("/auth/dev-token", json={"tenant_slug": slug})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def test_ingest_search_agent_and_tenant_scoping() -> None:
    from app import db
    from app.main import app

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            apex = await _token(client, "apex")
            summit = await _token(client, "summit")

            ingested = await client.post(
                "/v1/knowledge/workforce/documents",
                headers=apex,
                json={"source_type": "text", "source_ref": "overtime-policy.txt", "content": DOC},
            )
            assert ingested.status_code == 201, ingested.text
            assert ingested.json()["chunks"] >= 1

            docs = (await client.get("/v1/knowledge/workforce/documents", headers=apex)).json()
            assert len(docs) == 1 and docs[0]["agent"] == "workforce"

            hits = (
                await client.post(
                    "/v1/knowledge/workforce/search",
                    headers=apex,
                    json={"query": "overtime policy hours", "k": 3},
                )
            ).json()
            assert len(hits) >= 1
            assert "overtime" in hits[0]["content"].lower()

            # Agent scoping: the financial agent has no knowledge.
            other = await client.post(
                "/v1/knowledge/financial/search", headers=apex, json={"query": "overtime"}
            )
            assert other.json() == []

            # Tenant isolation: Summit sees none of Apex's knowledge.
            assert (await client.get("/v1/knowledge/workforce/documents", headers=summit)).json() == []
            assert (
                await client.post(
                    "/v1/knowledge/workforce/search", headers=summit, json={"query": "overtime"}
                )
            ).json() == []
    finally:
        await db.get_engine().dispose()
        db.get_engine.cache_clear()
        db.get_sessionmaker.cache_clear()
