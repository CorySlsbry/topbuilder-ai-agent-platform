"""Persistence for the feedback / training loop. Tenant-scoped (RLS auto-filters by tenant)."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _row(mapping: Any) -> dict | None:
    return dict(mapping) if mapping is not None else None


async def insert_feedback(
    session: AsyncSession,
    *,
    feedback_id: uuid.UUID,
    agent: str,
    run_id: uuid.UUID | None,
    target_kind: str,
    target_ref: str | None,
    rating: str,
    correction: str | None,
    note: str | None,
    created_by: uuid.UUID,
) -> dict | None:
    result = await session.execute(
        text(
            """
            INSERT INTO agent_feedback
              (id, agent, run_id, target_kind, target_ref, rating, correction, note, created_by)
            VALUES (:id, :agent, :run_id, :tk, :tr, :rating, :corr, :note, :cb)
            RETURNING *
            """
        ),
        {
            "id": feedback_id, "agent": agent, "run_id": run_id, "tk": target_kind, "tr": target_ref,
            "rating": rating, "corr": correction, "note": note, "cb": created_by,
        },
    )
    return _row(result.mappings().first())


async def list_feedback(session: AsyncSession, *, agent: str | None = None, limit: int = 50) -> list[dict]:
    result = await session.execute(
        text(
            """
            SELECT * FROM agent_feedback
            WHERE (CAST(:agent AS text) IS NULL OR agent = :agent)
            ORDER BY created_at DESC LIMIT :limit
            """
        ),
        {"agent": agent, "limit": limit},
    )
    return [dict(m) for m in result.mappings().all()]


async def recent_corrections(session: AsyncSession, *, agent: str, limit: int = 20) -> list[dict]:
    """The training signal: the human corrections this agent should learn from."""
    result = await session.execute(
        text(
            """
            SELECT * FROM agent_feedback
            WHERE agent = :agent AND correction IS NOT NULL
            ORDER BY created_at DESC LIMIT :limit
            """
        ),
        {"agent": agent, "limit": limit},
    )
    return [dict(m) for m in result.mappings().all()]
