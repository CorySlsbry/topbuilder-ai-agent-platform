"""End-to-end test for the payroll agent path (advisory run + the gated payroll adjustment).

Proves: a payroll run persists (admin), the worker pays + flagged review queue come back; proposing a
``payroll_adjustment`` for a FLAGGED worker is admin/analyst-gated (viewer 403), assembled server-side
(a clean worker is refused 400, never reaching the gate); then propose -> approve (admin) -> execute
(only when ACTIONS_ENABLED + allowlisted) -> undo, idempotent; and tenant isolation across Apex/Summit.

Mirrors tests/test_actions_api.py. Requires a real Postgres (RUN_DB_TESTS=1); marked integration.
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings

pytestmark = pytest.mark.integration


async def _token(client: AsyncClient, slug: str, role: str = "admin") -> dict[str, str]:
    resp = await client.post("/auth/dev-token", json={"tenant_slug": slug, "role": role})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def test_payroll_run_and_gated_adjustment(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import db
    from app.main import app

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            admin = await _token(client, "apex", "admin")
            analyst = await _token(client, "apex", "analyst")
            viewer = await _token(client, "apex", "viewer")
            summit = await _token(client, "summit", "admin")

            # Advisory payroll run -> persisted; the flagged review queue is populated.
            run = await client.post("/v1/agents/workforce/payroll?force=true", headers=admin)
            assert run.status_code == 201, run.text
            body = run.json()
            run_id = body["run_id"]
            assert body["totals"]["total_gross_usd"] == pytest.approx(5920.0)
            assert body["totals"]["flagged_count"] == 2
            flagged = [wp for wp in body["worker_pays"] if wp["needs_review"]]
            assert {wp["worker_id"] for wp in flagged} == {"tech-002", "tech-101"}
            clean = next(wp for wp in body["worker_pays"] if not wp["needs_review"])

            adj = {"run_id": run_id, "worker_id": "tech-002"}

            # Viewer cannot propose (needs admin/analyst).
            assert (
                await client.post("/v1/agents/workforce/payroll/adjustments", headers=viewer, json=adj)
            ).status_code == 403

            # A clean worker has no discrepancy -> refused server-side (400), never reaches the gate.
            bad = await client.post(
                "/v1/agents/workforce/payroll/adjustments",
                headers=analyst,
                json={"run_id": run_id, "worker_id": clean["worker_id"]},
            )
            assert bad.status_code == 400, bad.text

            # Analyst proposes the adjustment for a flagged worker -> 'proposed' (nothing external).
            r = await client.post(
                "/v1/agents/workforce/payroll/adjustments", headers=analyst, json=adj
            )
            assert r.status_code == 201, r.text
            action = r.json()
            assert action["status"] == "proposed"
            assert action["kind"] == "payroll_adjustment"
            assert action["agent"] == "workforce"
            assert action["params"]["worker_id"] == "tech-002"
            # params assembled server-side from the persisted run (clock vs claimed).
            assert action["params"]["computed_hours"] == pytest.approx(48.0)
            assert action["params"]["claimed_hours"] == pytest.approx(52.0)
            action_id = action["id"]

            # Idempotent propose -> same action id.
            r2 = await client.post(
                "/v1/agents/workforce/payroll/adjustments", headers=analyst, json=adj
            )
            assert r2.status_code == 201
            assert r2.json()["id"] == action_id

            # Approval is admin-only — the maker (analyst) cannot approve.
            assert (
                await client.post(f"/v1/actions/{action_id}/approve", headers=analyst)
            ).status_code == 403

            # Admin approves -> 'approved'.
            r = await client.post(f"/v1/actions/{action_id}/approve", headers=admin)
            assert r.status_code == 200, r.text
            assert r.json()["status"] == "approved"

            # Execute is blocked while actions are disabled (the default) -> 403; stays 'approved'.
            blocked = await client.post(f"/v1/actions/{action_id}/execute", headers=admin)
            assert blocked.status_code == 403
            assert (
                await client.get(f"/v1/actions/{action_id}", headers=admin)
            ).json()["status"] == "approved"

            # Opt in (master switch) + allowlist payroll_adjustment, then execute (fixture write).
            monkeypatch.setattr(
                "app.actions.service.get_settings",
                lambda: Settings(
                    actions_enabled=True,
                    servicetitan_mode="fixture",
                    actions_allowed_kinds="payroll_adjustment",
                ),
            )
            r = await client.post(f"/v1/actions/{action_id}/execute", headers=admin)
            assert r.status_code == 200, r.text
            done = r.json()
            assert done["status"] == "executed"
            assert done["result"]["status"] == "adjustment_posted"
            assert done["result"]["worker_id"] == "tech-002"
            assert done["executed_at"]

            # Idempotent execute.
            again = await client.post(f"/v1/actions/{action_id}/execute", headers=admin)
            assert again.status_code == 200
            assert again.json()["result"]["external_ref"] == done["result"]["external_ref"]

            # Undo (reversible) -> 'undone', idempotent.
            u = await client.post(f"/v1/actions/{action_id}/undo", headers=admin)
            assert u.status_code == 200, u.text
            assert u.json()["status"] == "undone"
            assert (
                await client.post(f"/v1/actions/{action_id}/undo", headers=admin)
            ).json()["status"] == "undone"

            # Tenant isolation: Summit can neither see the run nor act on Apex's action.
            assert (
                await client.get(f"/v1/agents/workforce/payroll/runs/{run_id}", headers=summit)
            ).status_code == 404
            assert (
                await client.get(f"/v1/actions/{action_id}", headers=summit)
            ).status_code == 404
            assert (
                await client.post(f"/v1/actions/{action_id}/approve", headers=summit)
            ).status_code == 404
    finally:
        await db.get_engine().dispose()
        db.get_engine.cache_clear()
        db.get_sessionmaker.cache_clear()
