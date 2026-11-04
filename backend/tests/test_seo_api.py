"""End-to-end API test for the SEO/GEO agent: run, read back, proposed actions, tenant isolation."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.integration

TOP_KEYWORD = "after hours answering service for hvac cost"


async def _token(client: AsyncClient, slug: str) -> dict[str, str]:
    resp = await client.post("/auth/dev-token", json={"tenant_slug": slug})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def test_seo_run_actions_and_isolation() -> None:
    from app import db
    from app.main import app

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            apex = await _token(client, "apex")
            summit = await _token(client, "summit")

            run = await client.post("/v1/agents/seo/runs", headers=apex)
            assert run.status_code == 201, run.text
            body = run.json()
            assert body["agent"] == "seo"
            assert body["weekly_summary"] == {
                "gaps_found": 23,
                "pages_below_benchmark": 3,
                "posts_planned": 2,
                "comments_drafted": 3,
            }
            assert sum(g["keywords_we_miss"] for g in body["competitor_gaps"]) == 23
            assert len(body["geo_audit"]) == 5
            assert sum(1 for p in body["geo_audit"] if p["status"] == "below_benchmark") == 3
            assert len(body["blog_opportunities"]) == 8
            top = body["blog_opportunities"][0]
            assert top["keyword"] == TOP_KEYWORD
            assert top["opportunity_score"] == 92.2
            assert len(body["comment_opportunities"]) == 3
            assert body["narration"] and body["inputs_hash"]
            run_id = body["run_id"]

            latest = await client.get("/v1/agents/seo/runs/latest", headers=apex)
            assert latest.status_code == 200
            assert latest.json()["run_id"] == run_id

            # The run best-effort-proposed its drafts through the action gate (ADR 0007):
            # publish_blog_post for the top 2 opportunities + post_comment for all 3 drafts.
            actions = await client.get("/v1/actions", params={"agent": "seo"}, headers=apex)
            assert actions.status_code == 200
            kinds = [a["kind"] for a in actions.json()]
            assert kinds.count("publish_blog_post") == 2
            assert kinds.count("post_comment") == 3
            assert all(a["status"] == "proposed" for a in actions.json())
            posts = [a for a in actions.json() if a["kind"] == "publish_blog_post"]
            assert {p["params"]["keyword"] for p in posts} == {
                TOP_KEYWORD, "why is my ac blowing warm air at night",
            }
            assert all(
                set(p["params"]) == {"keyword", "title", "outline", "draft_intro"} for p in posts
            )
            comments = [a for a in actions.json() if a["kind"] == "post_comment"]
            assert all(
                set(c["params"]) == {"platform", "url", "thread_title", "draft_comment"}
                for c in comments
            )
            assert all(a["run_id"] == run_id for a in actions.json())

            # Tenant isolation: summit sees neither the run nor the actions.
            by_id = await client.get(f"/v1/agents/seo/runs/{run_id}", headers=summit)
            assert by_id.status_code == 404
            assert (
                await client.get("/v1/agents/seo/runs/latest", headers=summit)
            ).status_code == 404
            summit_actions = await client.get(
                "/v1/actions", params={"agent": "seo"}, headers=summit
            )
            assert summit_actions.status_code == 200 and summit_actions.json() == []

            # Cron endpoint: 404 when CRON_SECRET is not configured (the documented test env).
            assert (await client.post("/v1/agents/seo/cron/weekly")).status_code == 404
    finally:
        await db.get_engine().dispose()
        db.get_engine.cache_clear()
        db.get_sessionmaker.cache_clear()
