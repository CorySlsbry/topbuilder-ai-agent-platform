"""End-to-end API test for the field-ops surface: pricebook, jobs, and the custom-quote builder."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.integration


async def _token(client: AsyncClient, slug: str, role: str = "admin") -> dict[str, str]:
    resp = await client.post("/auth/dev-token", json={"tenant_slug": slug, "role": role})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def test_fieldops_pricebook_jobs_and_quote() -> None:
    from app import db
    from app.main import app

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            tech = await _token(client, "apex", "admin")

            # Auth is required.
            assert (await client.get("/v1/field/pricebook")).status_code in (401, 403)

            pb = await client.get("/v1/field/pricebook", headers=tech)
            assert pb.status_code == 200
            assert len(pb.json()) == 12
            assert all(s["unit_price_usd"] > 0 for s in pb.json())

            jobs = await client.get("/v1/field/jobs", headers=tech)
            assert jobs.status_code == 200
            assert len(jobs.json()) >= 1
            assert "-" in jobs.json()[0]["window"]  # HH:MM-HH:MM

            # The custom-quote builder (the oracle): $441.00 + $31.48 tax = $472.48.
            body = {
                "tax_rate": 0.086,
                "line_items": [
                    {"service_code": "SVC-AC-TUNE"}, {"service_code": "SVC-CAP"},
                    {"service_code": "SVC-FILTER", "qty": 2}, {"service_code": "SVC-PERMIT"},
                ],
            }
            q = await client.post("/v1/field/quote", headers=tech, json=body)
            assert q.status_code == 200, q.text
            assert q.json()["subtotal_usd"] == 441.0
            assert q.json()["tax_usd"] == 31.48
            assert q.json()["total_usd"] == 472.48

            # An unknown service is a clean 400, not a 500.
            bad = await client.post("/v1/field/quote", headers=tech, json={"line_items": [{"service_code": "SVC-NOPE"}]})
            assert bad.status_code == 400

            # Submitting the quote proposes a ServiceTitan estimate through the action gate.
            sub = await client.post("/v1/field/quote/submit", headers=tech, json={**body, "job_ref": "JOB-9001"})
            assert sub.status_code == 201, sub.text
            assert sub.json()["kind"] == "create_estimate"
            assert sub.json()["status"] in ("proposed", "executed")
    finally:
        await db.get_engine().dispose()
        db.get_engine.cache_clear()
        db.get_sessionmaker.cache_clear()
