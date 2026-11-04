"""End-to-end test for the feedback / training loop: capture, training signal, tenant isolation."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.integration


async def _token(client: AsyncClient, slug: str) -> dict[str, str]:
    resp = await client.post("/auth/dev-token", json={"tenant_slug": slug})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def test_feedback_capture_training_signal_and_isolation() -> None:
    from app import db
    from app.main import app

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            apex = await _token(client, "apex")
            summit = await _token(client, "summit")

            # A human corrects the agent (the training signal).
            edit = await client.post("/v1/feedback", headers=apex, json={
                "agent": "booking", "target_kind": "recommendation", "target_ref": "rec-1",
                "rating": "edit", "correction": "Prefer morning slots for elderly customers.",
                "note": "learned on the Jane W. call",
            })
            assert edit.status_code == 201, edit.text
            fid = edit.json()["id"]
            assert edit.json()["rating"] == "edit"
            assert edit.json()["created_by"]

            # A plain up-vote (no correction) — counts as feedback but not training signal.
            up = await client.post("/v1/feedback", headers=apex, json={"agent": "booking", "rating": "up"})
            assert up.status_code == 201

            allfb = await client.get("/v1/feedback?agent=booking", headers=apex)
            assert allfb.status_code == 200
            assert len(allfb.json()) >= 2

            # Training signal = corrections only.
            ts = await client.get("/v1/feedback/training-signal?agent=booking", headers=apex)
            assert ts.status_code == 200
            assert all(f["correction"] for f in ts.json())
            assert any(f["id"] == fid and "morning" in (f["correction"] or "").lower() for f in ts.json())

            # Tenant isolation: Summit sees none of Apex's feedback.
            summit_fb = await client.get("/v1/feedback?agent=booking", headers=summit)
            assert summit_fb.status_code == 200
            assert all(f["id"] != fid for f in summit_fb.json())
    finally:
        await db.get_engine().dispose()
        db.get_engine.cache_clear()
        db.get_sessionmaker.cache_clear()
