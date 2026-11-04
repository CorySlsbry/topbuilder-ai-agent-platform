"""Phase C/D governance API: golden CRUD, consolidation trigger, drift, params, admin-gating, isolation."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.integration


async def _token(client: AsyncClient, slug: str, role: str = "admin") -> dict[str, str]:
    resp = await client.post("/auth/dev-token", json={"tenant_slug": slug, "role": role})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def test_governance_api_flow_admin_gating_and_isolation() -> None:
    from app import db
    from app.main import app

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            apex = await _token(client, "apex", "admin")
            apex_viewer = await _token(client, "apex", "viewer")
            summit = await _token(client, "summit", "admin")

            # Admin creates a golden case; a viewer may NOT (admin-gated write).
            gc = await client.post("/v1/learning/golden", headers=apex, json={
                "agent": "financial",
                "situation_text": "Cash falls to $42,000 by 90d; 2 jobs erode margin.",
                "must_include": ["$42,000"], "must_avoid": ["rounded"], "note": "regression: keep the figure",
            })
            assert gc.status_code == 201, gc.text
            viewer_attempt = await client.post("/v1/learning/golden", headers=apex_viewer, json={
                "agent": "financial", "situation_text": "x", "must_include": [], "must_avoid": [],
            })
            assert viewer_attempt.status_code == 403

            listed = (await client.get("/v1/learning/golden?agent=financial", headers=apex)).json()
            assert any("$42,000" in g["situation_text"] for g in listed)

            # A tunable knob round-trips.
            assert (await client.put("/v1/learning/params/canary_pct", headers=apex,
                                     json={"value": 20, "agent": "financial"})).status_code == 200
            params = (await client.get("/v1/learning/params", headers=apex)).json()
            assert any(p["name"] == "canary_pct" for p in params)

            # The nightly consolidation runs on-demand and writes a drift snapshot.
            cons = await client.post("/v1/learning/consolidate?agent=financial", headers=apex)
            assert cons.status_code == 200, cons.text
            assert cons.json()["reports"][0]["agent"] == "financial"
            drift = (await client.get("/v1/learning/drift?agent=financial", headers=apex)).json()
            assert len(drift) >= 1 and drift[0]["agent"] == "financial"

            # Approving a non-existent preference 404s (gate is wired).
            missing = await client.post(
                "/v1/learning/preferences/00000000-0000-0000-0000-000000000000/approve",
                headers=apex, json={"rollout_pct": 100},
            )
            assert missing.status_code == 404

            # Tenant isolation: Summit sees none of Apex's tenant-scoped golden cases.
            summit_golden = (await client.get("/v1/learning/golden?agent=financial", headers=summit)).json()
            assert all("$42,000" not in g["situation_text"] for g in summit_golden)
    finally:
        await db.get_engine().dispose()
        db.get_engine.cache_clear()
        db.get_sessionmaker.cache_clear()
