"""DB-integration tests for operator reporting (support_requests, migration 0028).

Proves the load-bearing guarantees against a real Postgres + RLS:
  * repository round-trip under operator_session (create -> list -> mark_notified);
  * RLS 2-context — a row seeded under operator_session() is INVISIBLE to a tenant_session
    (app.operator unset -> the operator-only policy fails closed);
  * counts_since aggregates recent rows by kind for the digest;
  * the operator authz gate on GET /v1/support — a non-operator admin gets 403, an operator 200;
  * POST /v1/support/intake persists a user-submitted bug and returns 202 (notify is best-effort:
    with no Slack/email configured it silently skips, and the row still lands).
"""
from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.db import operator_session, tenant_session
from app.demo import DEMO_TENANTS
from app.repositories import support as support_repo

pytestmark = pytest.mark.integration

_APEX = DEMO_TENANTS["apex"]
_OPERATOR_EMAIL = _APEX.admin_email
_OPERATOR_SETTINGS = Settings(platform_operator_emails=_OPERATOR_EMAIL)
_NON_OPERATOR_SETTINGS = Settings(platform_operator_emails="")


async def _admin_token(client: AsyncClient, slug: str = "apex") -> dict[str, str]:
    resp = await client.post("/auth/dev-token", json={"tenant_slug": slug, "role": "admin"})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _patch_gates(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> None:
    from app import config
    from app.api import routes_support

    monkeypatch.setattr(config, "get_settings", lambda: settings)
    monkeypatch.setattr(routes_support, "get_settings", lambda: settings)
    # capture.py reads get_settings() from app.config directly (already patched above).


class TestRepositoryRoundTrip:
    async def test_create_list_and_mark_notified(self) -> None:
        async with operator_session() as session:
            row = await support_repo.create_support_request(
                session, kind="bug", name="Sam", email="person1@example.com",
                message="blank dispatch board", source="in_app", meta={"k": "v"},
            )
            assert row["kind"] == "bug"
            assert row["notified_at"] is None
            listed = await support_repo.list_support_requests(session, kind="bug", limit=10)
            assert any(r["id"] == row["id"] for r in listed)
            await support_repo.mark_notified(session, row["id"])
            after = await support_repo.list_support_requests(session, kind="bug", limit=10)
            marked = next(r for r in after if r["id"] == row["id"])
            assert marked["notified_at"] is not None


class TestRlsIsolation:
    async def test_row_is_invisible_to_a_tenant_session(self) -> None:
        async with operator_session() as session:
            row = await support_repo.create_support_request(
                session, kind="feature", message="export 13-week cash flow", source="in_app",
            )
        # A tenant session (app.operator unset) must see ZERO operator rows — fail-closed policy.
        async with tenant_session(_APEX.tenant_id) as tsession:
            from sqlalchemy import text

            seen = (
                await tsession.execute(
                    text("SELECT count(*) FROM support_requests WHERE id = :id"), {"id": row["id"]}
                )
            ).scalar_one()
            assert seen == 0


class TestCountsSince:
    async def test_counts_by_kind_and_total(self) -> None:
        async with operator_session() as session:
            for kind in ("signup", "signup", "question"):
                await support_repo.create_support_request(session, kind=kind, message="x")
            counts, total = await support_repo.counts_since(session, hours=24)
        assert counts.get("signup", 0) >= 2
        assert counts.get("question", 0) >= 1
        assert total == sum(counts.values())


class TestOperatorAuthz:
    async def test_non_operator_admin_gets_403_and_operator_gets_200(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        transport = ASGITransport(app=__import__("app.main", fromlist=["app"]).app)
        async with AsyncClient(transport=transport, base_url="http://t") as client:
            headers = await _admin_token(client)

            _patch_gates(monkeypatch, _NON_OPERATOR_SETTINGS)
            forbidden = await client.get("/v1/support", headers=headers)
            assert forbidden.status_code == 403

            _patch_gates(monkeypatch, _OPERATOR_SETTINGS)
            ok = await client.get("/v1/support", headers=headers)
            assert ok.status_code == 200
            assert "support_requests" in ok.json()


class TestIntakePersists:
    async def test_intake_persists_a_bug_and_returns_202(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # No Slack / no operator emails -> notify silently skips; the row still lands (202).
        _patch_gates(monkeypatch, _NON_OPERATOR_SETTINGS)
        transport = ASGITransport(app=__import__("app.main", fromlist=["app"]).app)
        async with AsyncClient(transport=transport, base_url="http://t") as client:
            headers = await _admin_token(client)
            resp = await client.post(
                "/v1/support/intake",
                json={"kind": "bug", "message": "the estimate total is off by tax"},
                headers=headers,
            )
            assert resp.status_code == 202, resp.text
            new_id = resp.json()["id"]
            assert new_id
        async with operator_session() as session:
            rows = await support_repo.list_support_requests(session, kind="bug", limit=50)
        assert any(r["id"] == uuid.UUID(new_id) for r in rows)

    async def test_intake_rejects_a_non_intake_kind(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_gates(monkeypatch, _NON_OPERATOR_SETTINGS)
        transport = ASGITransport(app=__import__("app.main", fromlist=["app"]).app)
        async with AsyncClient(transport=transport, base_url="http://t") as client:
            headers = await _admin_token(client)
            # 'signup' is captured by the system, not user-submittable via intake.
            resp = await client.post(
                "/v1/support/intake",
                json={"kind": "signup", "message": "x"},
                headers=headers,
            )
            assert resp.status_code == 422
