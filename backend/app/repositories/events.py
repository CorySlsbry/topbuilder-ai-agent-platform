"""Persistence for the inbound webhook event queue (tenant-scoped via RLS).

The drain-side claim/complete lifecycle lives in `app/repositories/sync.py` (leased
`claim_for_processing` / `complete_event`, ADR 0010) — this module owns only the producer side
(enqueue + operator listing)."""
from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def enqueue_event(
    session: AsyncSession,
    *,
    source: str,
    event_type: str,
    external_id: str | None,
    payload: dict,
) -> bool:
    """Insert an inbound event. Returns True if inserted, False if it was a duplicate
    (same tenant+source+external_id) — replays are idempotent (migration 0017)."""
    row = (
        await session.execute(
            text(
                """
                INSERT INTO event_queue (source, event_type, external_id, payload)
                VALUES (:source, :event_type, :external_id, CAST(:payload AS jsonb))
                ON CONFLICT (tenant_id, source, external_id) WHERE external_id IS NOT NULL
                    DO NOTHING
                RETURNING id
                """
            ),
            {
                "source": source,
                "event_type": event_type,
                "external_id": external_id,
                "payload": json.dumps(payload),
            },
        )
    ).first()
    return row is not None


async def list_events(session: AsyncSession, *, limit: int = 50) -> list[dict]:
    rows = (
        await session.execute(
            text(
                "SELECT id, source, event_type, external_id, status, received_at "
                "FROM event_queue ORDER BY received_at DESC LIMIT :limit"
            ),
            {"limit": limit},
        )
    ).mappings().all()
    return [dict(m) for m in rows]
