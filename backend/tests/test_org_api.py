"""End-to-end API tests for the Organization Brain: seed-on-read, tenant isolation (RLS), and the
department permission gate (a dispatch login literally cannot reach the Financial agent — 403).

Requires migration 0015 applied (org tables + the canyonridge tenant + membership columns).
"""
from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.integration

CANYONRIDGE = uuid.UUID("33333333-3333-3333-3333-333333333333")


async def _token(client: AsyncClient, slug: str, role: str = "admin") -> dict[str, str]:
    resp = await client.post("/auth/dev-token", json={"tenant_slug": slug, "role": role})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _department_token(department: str, role: str = "analyst") -> dict[str, str]:
    """Mint a department-scoped token directly (the dev-token endpoint carries no department)."""
    from app.security import create_token

    token = create_token(
        tenant_id=CANYONRIDGE,
        user_id=uuid.uuid4(),
        email=f"{department}.person1@example.com",
        role=role,
        department=department,
    )
    return {"Authorization": f"Bearer {token}"}


async def test_org_overview_seeds_on_read_and_isolates_tenants() -> None:
    from app import db
    from app.main import app

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            canyon = await _token(client, "canyonridge")
            apex = await _token(client, "apex")

            # First read seeds the 38-person roster (idempotent on every read after).
            resp = await client.get("/v1/org/overview", headers=canyon)
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["company"]["name"] == "Canyon Ridge Mechanical"
            assert body["company"]["employee_count"] == 38
            assert body["company"]["provider"] == "servicetitan"
            assert len(body["people"]) == 38
            assert [d["key"] for d in body["departments"]] == [
                "leadership", "front_office", "dispatch", "field", "sales", "finance", "warehouse",
            ]
            assert {d["key"]: d["head_count"] for d in body["departments"]}["field"] == 18
            assert len(body["agents"]) == 8
            # Admin dev token = unrestricted caller access.
            assert body["caller_access"] == {"department": None, "allowed_agents": None}

            # Re-read does not duplicate (ON CONFLICT DO NOTHING + count guard).
            again = await client.get("/v1/org/overview", headers=canyon)
            assert again.json()["company"]["employee_count"] == 38

            # Person profile: Alex is the owner with no manager and the GM as a direct report.
            alex_id = next(p["id"] for p in body["people"] if p["full_name"] == "Alex")
            person = (await client.get(f"/v1/org/people/{alex_id}", headers=canyon)).json()
            assert person["person"]["role_tier"] == "owner"
            assert person["manager"] is None
            assert {r["full_name"] for r in person["direct_reports"]} == {"Marcus Reed", "Elena Vasquez"}
            assert person["ai_access"]["not_accessible"] == []

            # RLS isolation: Apex sees its own (empty) org, never Canyon Ridge's people.
            apex_view = (await client.get("/v1/org/overview", headers=apex)).json()
            assert apex_view["people"] == []
            assert apex_view["departments"] == []
            assert (await client.get(f"/v1/org/people/{alex_id}", headers=apex)).status_code == 404
    finally:
        await db.get_engine().dispose()
        db.get_engine.cache_clear()
        db.get_sessionmaker.cache_clear()


async def test_department_gate_blocks_out_of_scope_agents() -> None:
    from app import db
    from app.main import app

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            dispatch = _department_token("dispatch")

            # The money shot: a dispatch login cannot reach the Financial agent.
            blocked = await client.get("/v1/agents/financial/runs/latest", headers=dispatch)
            assert blocked.status_code == 403, blocked.text
            assert "does not include the financial agent" in blocked.json()["error"]["message"]
            assert (
                await client.post("/v1/agents/financial/runs", headers=dispatch)
            ).status_code == 403

            # Its own agent stays reachable (404 just means no runs yet — not forbidden).
            allowed = await client.get("/v1/agents/routing/runs/latest", headers=dispatch)
            assert allowed.status_code in (200, 404)

            # The runner-role gate still composes: a dispatch viewer may read but not run.
            viewer = _department_token("dispatch", role="viewer")
            assert (
                await client.post("/v1/agents/routing/runs", headers=viewer)
            ).status_code == 403

            # /auth/me reports the scope the frontend filters by.
            me = (await client.get("/auth/me", headers=dispatch)).json()
            assert me["department"] == "dispatch"
            assert me["allowed_agents"] == ["routing"]
            assert me["allowed_sections"] == ["dispatch", "dispatchboard", "organization"]
            assert me["person"] is None
    finally:
        await db.get_engine().dispose()
        db.get_engine.cache_clear()
        db.get_sessionmaker.cache_clear()
