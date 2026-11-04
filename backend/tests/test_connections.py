"""Credential vault: store (encrypted) -> list (no secret) -> decrypt roundtrip -> tenant isolation."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.integration


async def _token(client: AsyncClient, slug: str) -> dict[str, str]:
    resp = await client.post("/auth/dev-token", json={"tenant_slug": slug})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def test_credential_vault_store_list_isolation_roundtrip() -> None:
    from app import db
    from app.db import tenant_session
    from app.demo import DEMO_TENANTS
    from app.main import app
    from app.repositories import credentials

    secret = {"client_id": "ci", "client_secret": "cs", "app_key": "ak", "tenant_id": "ti"}
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            apex = await _token(client, "apex")
            summit = await _token(client, "summit")

            stored = await client.put(
                "/v1/connections",
                headers=apex,
                json={"provider": "servicetitan", "secret": secret, "metadata": {"env": "sandbox"}},
            )
            assert stored.status_code == 200, stored.text

            listed = (await client.get("/v1/connections", headers=apex)).json()
            assert [c["provider"] for c in listed] == ["servicetitan"]
            assert all("secret" not in c and "secret_ciphertext" not in c for c in listed)

            # Summit cannot see Apex's connection.
            assert (await client.get("/v1/connections", headers=summit)).json() == []

            # Encryption roundtrip through the DB recovers the exact secret.
            async with tenant_session(DEMO_TENANTS["apex"].tenant_id) as session:
                recovered = await credentials.get_credential(session, provider="servicetitan")
            assert recovered == secret
    finally:
        await db.get_engine().dispose()
        db.get_engine.cache_clear()
        db.get_sessionmaker.cache_clear()
