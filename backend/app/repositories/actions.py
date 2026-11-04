"""Persistence for human-approved actions (ADR 0007).

Runs on a tenant-scoped session (RLS auto-filters by tenant; the `tenant_id` column default stamps the
current tenant on insert). Status transitions are guarded with `WHERE status = <expected>` so a
transition can never race or skip a step, and `RETURNING *` reports whether the guard matched.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_JSONB = ("params", "result")


def _row(mapping: Any) -> dict | None:
    if mapping is None:
        return None
    d = dict(mapping)
    for k in _JSONB:
        if isinstance(d.get(k), str):
            d[k] = json.loads(d[k])
    return d


async def insert_action(
    session: AsyncSession,
    *,
    action_id: uuid.UUID,
    run_id: uuid.UUID | None,
    agent: str,
    kind: str,
    params: dict,
    idempotency_key: str,
    requested_by: uuid.UUID,
) -> dict | None:
    """Insert a proposed action. Idempotent: a duplicate (tenant, idempotency_key) inserts nothing
    and returns None (the caller then reads the existing row)."""
    result = await session.execute(
        text(
            """
            INSERT INTO agent_actions
              (id, run_id, agent, kind, status, params, idempotency_key, requested_by)
            VALUES
              (:id, :run_id, :agent, :kind, 'proposed', CAST(:params AS jsonb), :key, :requested_by)
            ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
            RETURNING *
            """
        ),
        {
            "id": action_id,
            "run_id": run_id,
            "agent": agent,
            "kind": kind,
            "params": json.dumps(params, default=str),
            "key": idempotency_key,
            "requested_by": requested_by,
        },
    )
    return _row(result.mappings().first())


async def get_action(session: AsyncSession, *, action_id: uuid.UUID) -> dict | None:
    result = await session.execute(
        text("SELECT * FROM agent_actions WHERE id = :id"), {"id": action_id}
    )
    return _row(result.mappings().first())


async def get_action_by_key(session: AsyncSession, *, idempotency_key: str) -> dict | None:
    result = await session.execute(
        text("SELECT * FROM agent_actions WHERE idempotency_key = :k"), {"k": idempotency_key}
    )
    return _row(result.mappings().first())


async def release_idempotency_key(session: AsyncSession, *, action_id: uuid.UUID, new_key: str) -> None:
    """Tombstone a dead action's idempotency key so the same proposal can be made fresh
    (an 'undone'/'failed' action must not block a redo forever)."""
    await session.execute(
        text("UPDATE agent_actions SET idempotency_key = :k, updated_at = now() WHERE id = :id"),
        {"k": new_key, "id": action_id},
    )


async def list_actions(
    session: AsyncSession,
    *,
    agent: str | None = None,
    agents: list[str] | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """List tenant actions (RLS-scoped). `agents` (None = unrestricted) is a cheap department
    pre-filter on the STORED agent column; the service layer re-filters authoritatively by the
    owning agent. `status` narrows the approvals queue (e.g. 'proposed')."""
    # The agent-set filter is bound as a comma-joined TEXT (split server-side via string_to_array)
    # rather than a list -> text[] cast: asyncpg cannot infer the element type of a cast-bound list
    # (and an empty list errors), whereas a text bind is unambiguous. Agent keys contain no commas.
    # `string_to_array('', ',')` -> {''}, which matches no real agent, so an empty department's queue
    # is correctly empty (fail-closed). This SQL filter only narrows; the service post-filters by owner.
    result = await session.execute(
        text(
            """
            SELECT * FROM agent_actions
            WHERE (CAST(:agent AS text) IS NULL OR agent = :agent)
              AND (CAST(:status AS text) IS NULL OR status = :status)
              AND (:no_agent_filter OR agent = ANY(string_to_array(:agents_csv, ',')))
            ORDER BY created_at DESC
            LIMIT :limit
            """
        ),
        {
            "agent": agent,
            "status": status,
            "no_agent_filter": agents is None,
            "agents_csv": ",".join(agents or []),
            "limit": limit,
        },
    )
    return [_row(m) for m in result.mappings().all()]  # type: ignore[misc]


async def reject(
    session: AsyncSession, *, action_id: uuid.UUID, decided_by: uuid.UUID, reason: str | None = None
) -> dict | None:
    """proposed -> rejected (a human disapproves). Guarded; returns None if not 'proposed'. Records the
    decider in approved_by (the decision actor) and the reason in error."""
    result = await session.execute(
        text(
            """
            UPDATE agent_actions
               SET status = 'rejected', approved_by = :who, approved_at = now(),
                   error = :reason, updated_at = now()
             WHERE id = :id AND status = 'proposed'
            RETURNING *
            """
        ),
        {"id": action_id, "who": decided_by, "reason": reason},
    )
    return _row(result.mappings().first())


async def approve(session: AsyncSession, *, action_id: uuid.UUID, approved_by: uuid.UUID) -> dict | None:
    """proposed -> approved. Returns None if the action wasn't in 'proposed' (guard didn't match)."""
    result = await session.execute(
        text(
            """
            UPDATE agent_actions
               SET status = 'approved', approved_by = :who, approved_at = now(), updated_at = now()
             WHERE id = :id AND status = 'proposed'
            RETURNING *
            """
        ),
        {"id": action_id, "who": approved_by},
    )
    return _row(result.mappings().first())


async def mark_executing(session: AsyncSession, *, action_id: uuid.UUID) -> dict | None:
    """approved -> executing (the claim that lets exactly one executor run)."""
    result = await session.execute(
        text(
            "UPDATE agent_actions SET status = 'executing', updated_at = now() "
            "WHERE id = :id AND status = 'approved' RETURNING *"
        ),
        {"id": action_id},
    )
    return _row(result.mappings().first())


async def mark_executed(session: AsyncSession, *, action_id: uuid.UUID, result_payload: dict) -> dict | None:
    result = await session.execute(
        text(
            """
            UPDATE agent_actions
               SET status = 'executed', result = CAST(:result AS jsonb),
                   executed_at = now(), updated_at = now()
             WHERE id = :id AND status = 'executing'
            RETURNING *
            """
        ),
        {"id": action_id, "result": json.dumps(result_payload, default=str)},
    )
    return _row(result.mappings().first())


async def mark_failed(session: AsyncSession, *, action_id: uuid.UUID, error: str) -> dict | None:
    result = await session.execute(
        text(
            "UPDATE agent_actions SET status = 'failed', error = :err, updated_at = now() "
            "WHERE id = :id AND status IN ('executing', 'approved') RETURNING *"
        ),
        {"id": action_id, "err": error},
    )
    return _row(result.mappings().first())


async def mark_undone(session: AsyncSession, *, action_id: uuid.UUID, undo_result: dict) -> dict | None:
    """executed -> undone (autonomous-with-undo). Keeps the original result, records the reversal."""
    result = await session.execute(
        text(
            """
            UPDATE agent_actions
               SET status = 'undone',
                   result = jsonb_set(coalesce(result, '{}'::jsonb), '{undo}', CAST(:rev AS jsonb)),
                   updated_at = now()
             WHERE id = :id AND status = 'executed'
            RETURNING *
            """
        ),
        {"id": action_id, "rev": json.dumps(undo_result, default=str)},
    )
    return _row(result.mappings().first())
