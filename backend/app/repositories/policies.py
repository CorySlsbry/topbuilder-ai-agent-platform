"""Per-agent autonomy policy persistence (off | hitl | auto).

Tenant-scoped session → RLS auto-filters; the `tenant_id` column default stamps the current tenant on
insert. A missing row means the safe default (`hitl`): the agent may propose, a human approves.
"""
from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

VALID_MODES = {"off", "hitl", "auto"}
DEFAULT_MODE = "hitl"


async def get_mode(session: AsyncSession, *, agent: str) -> str:
    row = (
        await session.execute(text("SELECT mode FROM agent_policies WHERE agent = :a"), {"a": agent})
    ).first()
    return row[0] if row else DEFAULT_MODE


async def list_policies(session: AsyncSession) -> list[dict]:
    rows = (
        await session.execute(
            text("SELECT agent, mode, updated_at FROM agent_policies ORDER BY agent")
        )
    ).mappings().all()
    return [dict(m) for m in rows]


async def upsert(session: AsyncSession, *, agent: str, mode: str, updated_by: uuid.UUID) -> dict:
    row = (
        await session.execute(
            text(
                """
                INSERT INTO agent_policies (agent, mode, updated_by, updated_at)
                VALUES (:a, :m, :u, now())
                ON CONFLICT (tenant_id, agent)
                  DO UPDATE SET mode = :m, updated_by = :u, updated_at = now()
                RETURNING agent, mode, updated_at
                """
            ),
            {"a": agent, "m": mode, "u": updated_by},
        )
    ).mappings().first()
    return dict(row)
