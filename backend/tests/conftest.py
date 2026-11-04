"""Pytest configuration.

DB-touching tests are marked `integration` and skipped unless RUN_DB_TESTS=1 (so the pure unit +
property suite runs anywhere with zero infrastructure). To run them:

    docker compose up -d db
    # apply migrations against the local db (admin URL), then:
    RUN_DB_TESTS=1 \
      DATABASE_URL=postgresql+asyncpg://app_user:app_pw@localhost:5432/fieldops \
      APP_PG_DSN=postgresql://app_user:app_pw@localhost:5432/fieldops \
      pytest -q
"""
from __future__ import annotations

import os

import pytest


def pytest_collection_modifyitems(config, items):
    if os.environ.get("RUN_DB_TESTS") == "1":
        return
    skip = pytest.mark.skip(reason="set RUN_DB_TESTS=1 with a test Postgres to run DB integration tests")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session", autouse=True)
def _clean_run_tables():
    """Give DB integration tests a clean slate (like a fresh CI database) so run-history and
    idempotency assertions are deterministic. Keeps the seeded tenants/users/connections."""
    if os.environ.get("RUN_DB_TESTS") != "1":
        yield
        return

    import asyncio

    import asyncpg

    # Truncate as the superuser (bypasses RLS). Derive the admin DSN if not given.
    dsn = os.environ.get("ADMIN_PG_DSN") or os.environ.get("APP_PG_DSN", "").replace(
        "app_user:app_pw", "postgres:postgres"
    )

    async def _truncate() -> None:
        conn = await asyncpg.connect(dsn)
        try:
            await conn.execute(
                "TRUNCATE agent_runs, agent_actions, agent_feedback, agent_policies, "
                "agent_recommendations, agent_reasoning_logs, audit_events, tenant_credentials, "
                "event_queue, communications, tasks, knowledge_documents, knowledge_chunks, "
                "agent_cases, agent_preferences, learning_events, golden_cases, eval_runs, "
                "learning_params, drift_snapshots "
                "RESTART IDENTITY CASCADE"
            )
        finally:
            await conn.close()

    asyncio.run(_truncate())
    yield
