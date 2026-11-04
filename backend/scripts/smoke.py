"""End-to-end smoke test against a running API (default http://localhost:8088).

Exercises every router: auth, all three agents, knowledge (RAG), connections (vault), webhooks.
Usage:  python scripts/smoke.py
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os

import httpx

BASE = os.environ.get("SMOKE_BASE_URL", "http://localhost:8088")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SIGNING_SECRET", "dev-webhook-secret")
APEX_TENANT = "11111111-1111-1111-1111-111111111111"


async def main() -> None:
    async with httpx.AsyncClient(base_url=BASE, timeout=60) as c:
        print("health     ", (await c.get("/health")).json())
        token = (await c.post("/auth/dev-token", json={"tenant_slug": "apex"})).json()["access_token"]
        h = {"Authorization": f"Bearer {token}"}

        for agent, query in [("workforce", "?horizon_days=21"), ("financial", ""), ("inventory", ""), ("booking", "")]:
            r = await c.post(f"/v1/agents/{agent}/runs{query}", headers=h)
            print(f"{agent:11}", r.status_code, "totals=", r.json().get("totals"))

        r = await c.post(
            "/v1/knowledge/workforce/documents",
            headers=h,
            json={"source_type": "text", "source_ref": "policy.txt",
                  "content": "Overtime is capped at 45 hours per week for HVAC technicians."},
        )
        print("kb ingest  ", r.status_code, r.json())
        r = await c.post("/v1/knowledge/workforce/search", headers=h, json={"query": "overtime hours", "k": 2})
        print("kb search  ", r.status_code, "hits=", len(r.json()))

        r = await c.put("/v1/connections", headers=h,
                        json={"provider": "servicetitan", "secret": {"client_id": "x"}, "metadata": {"env": "sandbox"}})
        print("vault put  ", r.status_code, r.json())
        r = await c.get("/v1/connections", headers=h)
        print("vault list ", r.status_code, [x["provider"] for x in r.json()])

        body = json.dumps({"eventType": "job.completed", "id": "evt-1"}).encode()
        sig = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
        r = await c.post(f"/v1/webhooks/servicetitan/{APEX_TENANT}", content=body,
                         headers={"X-Signature": sig, "Content-Type": "application/json"})
        print("webhook    ", r.status_code, r.json())
        r = await c.get("/v1/webhooks/events", headers=h)
        print("wh events  ", r.status_code, "count=", len(r.json()))


if __name__ == "__main__":
    asyncio.run(main())
