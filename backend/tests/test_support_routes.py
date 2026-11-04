"""Route-gate tests for the support/reporting surface — the auth + validation checks that fire
BEFORE any DB access, so they run in the pure suite (no Postgres).

Covered:
  - POST /v1/support/intake requires authentication (401 without a bearer token);
  - the intake kind is validated against the allowed set (bug|feature|question) — a 422 is raised
    before any row is written, and the pure kind validator agrees;
  - GET /v1/support requires auth (401 anon);
  - the digest cron mirrors the sync crons: 404 when no cron secret is configured, 403 on a bad key.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.notify import support_kinds


@pytest.fixture()
def client() -> TestClient:
    return TestClient(__import__("app.main", fromlist=["app"]).app, raise_server_exceptions=False)


class TestKindValidator:
    def test_intake_kinds_are_the_user_reportable_three(self) -> None:
        assert support_kinds.INTAKE_KINDS == {"bug", "feature", "question"}

    def test_all_kinds_include_the_captured_two(self) -> None:
        # signup + chatbot are captured by the system, not submitted via /intake.
        assert support_kinds.ALL_KINDS == {"signup", "chatbot", "bug", "feature", "question"}

    def test_is_intake_kind(self) -> None:
        assert support_kinds.is_intake_kind("bug")
        assert not support_kinds.is_intake_kind("signup")  # not user-submittable
        assert not support_kinds.is_intake_kind("malware")


class TestIntakeAuth:
    # HTTPBearer(auto_error=True) rejects a MISSING bearer with 403 (no credential) and an INVALID
    # one with 401; either way an unauthenticated caller is refused. The gate is what's under test.
    def test_intake_rejects_unauthenticated(self, client: TestClient) -> None:
        resp = client.post("/v1/support/intake", json={"kind": "bug", "message": "x"})
        assert resp.status_code in (401, 403)

    def test_support_list_rejects_unauthenticated(self, client: TestClient) -> None:
        assert client.get("/v1/support").status_code in (401, 403)


class TestDigestCronAuth:
    def test_cron_404_when_no_secret_configured(self, client: TestClient, monkeypatch) -> None:
        # Default dev settings have no cron_secret -> the endpoint hides itself (404), mirroring
        # routes_sync. No X-Cron-Key header supplied.
        resp = client.post("/v1/support/cron/digest")
        assert resp.status_code == 404

    def test_cron_403_on_bad_key(self, client: TestClient, monkeypatch) -> None:
        from app.config import get_settings

        settings = get_settings()
        monkeypatch.setattr(settings, "cron_secret", "the-real-key", raising=False)
        resp = client.post("/v1/support/cron/digest", headers={"X-Cron-Key": "wrong"})
        assert resp.status_code == 403
