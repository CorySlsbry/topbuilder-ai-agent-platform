"""The load-bearing security test: Postgres RLS blocks cross-tenant reads and fails closed.

Talks to Postgres directly as the runtime role (`app_user`) — independent of the application — so it
proves the *database* enforces isolation, not the app. See ADR 0002.
"""
from __future__ import annotations

import os
import uuid

import asyncpg
import pytest

pytestmark = pytest.mark.integration

APEX = uuid.UUID("11111111-1111-1111-1111-111111111111")
SUMMIT = uuid.UUID("22222222-2222-2222-2222-222222222222")
APEX_USER = uuid.UUID("1a000000-0000-0000-0000-000000000001")
SUMMIT_USER = uuid.UUID("2b000000-0000-0000-0000-000000000001")


async def _insert_run(conn: asyncpg.Connection, tenant: uuid.UUID, created_by: uuid.UUID) -> uuid.UUID:
    run_id = uuid.uuid4()
    async with conn.transaction():
        # set_config(..., is_local=true) scopes the tenant to THIS transaction; the column default
        # then stamps tenant_id, and the WITH CHECK policy validates it.
        await conn.execute("SELECT set_config('app.current_tenant', $1, true)", str(tenant))
        await conn.execute(
            "INSERT INTO agent_runs (id, agent, status, horizon_days, created_by, duration_ms) "
            "VALUES ($1, 'workforce', 'succeeded', 21, $2, 1)",
            run_id,
            created_by,
        )
    return run_id


async def test_rls_blocks_cross_tenant_reads_and_fails_closed() -> None:
    dsn = os.environ["APP_PG_DSN"]  # connects as app_user (non-superuser, no BYPASSRLS)
    conn = await asyncpg.connect(dsn)
    try:
        run_apex = await _insert_run(conn, APEX, APEX_USER)
        run_summit = await _insert_run(conn, SUMMIT, SUMMIT_USER)

        # Reading as Apex: Apex's row is visible, Summit's is not.
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.current_tenant', $1, true)", str(APEX))
            visible = await conn.fetch(
                "SELECT id FROM agent_runs WHERE id = ANY($1::uuid[])",
                [run_apex, run_summit],
            )
        visible_ids = {row["id"] for row in visible}
        assert run_apex in visible_ids
        assert run_summit not in visible_ids

        # Fail-closed: with no tenant set, the policy matches nothing.
        unscoped_count = await conn.fetchval("SELECT count(*) FROM agent_runs")
        assert unscoped_count == 0
    finally:
        await conn.close()


async def test_app_user_cannot_bypass_rls() -> None:
    """Guard against a misconfigured runtime role (the one way RLS silently breaks)."""
    dsn = os.environ["APP_PG_DSN"]
    conn = await asyncpg.connect(dsn)
    try:
        row = await conn.fetchrow(
            "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
        )
        assert row["rolsuper"] is False
        assert row["rolbypassrls"] is False
    finally:
        await conn.close()
