"""Persistence for the event-detection layer (ADR 0010): durable cursors + a leased drain queue.

All queries are tenant-scoped by RLS (the caller runs inside `db.tenant_session`). The drain uses a
**lease** model on `event_queue`: a claimed row flips to `processing` with a `next_attempt_at` lease
expiry, so an overlapping cron run skips it (FOR UPDATE SKIP LOCKED) and a crashed worker's row is
reclaimable once the lease lapses — never stranded `pending` forever, never double-processed.
"""
from __future__ import annotations

import datetime as dt
import json
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _loads(payload: object) -> dict:
    """asyncpg returns jsonb as text; decode to a dict (defensive against either shape)."""
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, str) and payload:
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return {}
    return {}


# --- cursors ---------------------------------------------------------------------------------------
async def list_cursors(session: AsyncSession) -> list[dict]:
    """All of this tenant's detection cursors (RLS-scoped) — the poll tick iterates these."""
    rows = (
        await session.execute(
            text(
                "SELECT source, entity, cursor_token, cadence_seconds, last_run_at, last_status "
                "FROM sync_cursor ORDER BY source, entity"
            )
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def get_cursor(session: AsyncSession, *, source: str, entity: str) -> dict | None:
    row = (
        await session.execute(
            text(
                "SELECT source, entity, cursor_token, cadence_seconds, last_run_at, last_status "
                "FROM sync_cursor WHERE source = :source AND entity = :entity"
            ),
            {"source": source, "entity": entity},
        )
    ).mappings().first()
    return dict(row) if row else None


async def upsert_cursor(
    session: AsyncSession,
    *,
    source: str,
    entity: str,
    cursor_token: str | None,
    status: str,
    now: dt.datetime,
    error: str | None = None,
    cadence_seconds: int | None = None,
) -> None:
    """Advance a cursor AFTER its batch is durably enqueued in the same transaction, so a crashed or
    skipped tick resumes gap-free."""
    await session.execute(
        text(
            """
            INSERT INTO sync_cursor (source, entity, cursor_token, cadence_seconds,
                                     last_run_at, last_status, last_error, updated_at)
            VALUES (:source, :entity, :token, COALESCE(:cadence, 900), :now, :status, :error, :now)
            ON CONFLICT (tenant_id, source, entity) DO UPDATE SET
                cursor_token = EXCLUDED.cursor_token,
                cadence_seconds = COALESCE(:cadence, sync_cursor.cadence_seconds),
                last_run_at = EXCLUDED.last_run_at,
                last_status = EXCLUDED.last_status,
                last_error = EXCLUDED.last_error,
                updated_at = EXCLUDED.updated_at
            """
        ),
        {"source": source, "entity": entity, "token": cursor_token, "status": status,
         "error": error, "now": now, "cadence": cadence_seconds},
    )


async def mark_cursor_error(
    session: AsyncSession, *, source: str, entity: str, now: dt.datetime, error: str
) -> None:
    """Record a poll failure WITHOUT touching cursor_token — so a mid-tick failure never rewinds the
    page-granular advances already committed this tick (which would re-pull + re-propose those pages)."""
    await session.execute(
        text(
            "UPDATE sync_cursor SET last_status = 'error', last_error = :error, last_run_at = :now, "
            "updated_at = :now WHERE source = :source AND entity = :entity"
        ),
        {"source": source, "entity": entity, "error": error, "now": now},
    )


# --- leased drain queue ----------------------------------------------------------------------------
async def claim_for_processing(
    session: AsyncSession, *, limit: int, now: dt.datetime, lease_seconds: int = 300
) -> list[dict]:
    """Atomically claim due events: status `pending` past its backoff, OR a `processing` row whose
    lease has lapsed (a crashed worker). Flip to `processing`, bump the attempt count, and set a fresh
    lease. One transaction, so overlapping cron runs never grab the same row."""
    rows = (
        await session.execute(
            text(
                """
                WITH due AS (
                    SELECT id FROM event_queue
                    WHERE (status = 'pending'
                           AND (next_attempt_at IS NULL OR next_attempt_at <= :now))
                       OR (status = 'processing'
                           AND next_attempt_at IS NOT NULL AND next_attempt_at <= :now)
                    ORDER BY received_at ASC
                    LIMIT :limit
                    FOR UPDATE SKIP LOCKED
                )
                UPDATE event_queue q
                   SET status = 'processing',
                       retry_count = q.retry_count + 1,
                       next_attempt_at = :now + make_interval(secs => :lease)
                  FROM due
                 WHERE q.id = due.id
             RETURNING q.id, q.source, q.event_type, q.external_id, q.payload, q.retry_count
                """
            ),
            {"now": now, "limit": limit, "lease": lease_seconds},
        )
    ).mappings().all()
    out: list[dict] = []
    for row in rows:
        item = dict(row)
        item["payload"] = _loads(item.get("payload"))
        out.append(item)
    return out


async def complete_event(session: AsyncSession, *, event_id: uuid.UUID, note: str | None = None) -> None:
    await session.execute(
        text(
            "UPDATE event_queue SET status = 'processed', processed_at = now(), "
            "error = :note, next_attempt_at = NULL WHERE id = :id"
        ),
        {"id": event_id, "note": note},
    )


async def retry_event(
    session: AsyncSession, *, event_id: uuid.UUID, error: str, backoff_seconds: int, now: dt.datetime
) -> None:
    """Return a transiently-failed event to `pending` with an exponential-ish backoff window."""
    await session.execute(
        text(
            "UPDATE event_queue SET status = 'pending', error = :error, "
            "next_attempt_at = :now + make_interval(secs => :backoff) WHERE id = :id"
        ),
        {"id": event_id, "error": error, "now": now, "backoff": backoff_seconds},
    )


async def dead_letter_event(
    session: AsyncSession,
    *,
    event_id: uuid.UUID,
    source: str,
    event_type: str,
    external_id: str | None,
    payload: dict,
    attempts: int,
    error: str,
) -> None:
    """Quarantine a poison event so it can't head-of-line block the tenant's drain; mark it failed."""
    await session.execute(
        text(
            """
            INSERT INTO sync_dead_letter (event_id, source, event_type, external_id, payload,
                                          attempts, last_error)
            VALUES (:event_id, :source, :event_type, :external_id, CAST(:payload AS jsonb),
                    :attempts, :error)
            """
        ),
        {"event_id": event_id, "source": source, "event_type": event_type,
         "external_id": external_id, "payload": json.dumps(payload), "attempts": attempts,
         "error": error},
    )
    await session.execute(
        text("UPDATE event_queue SET status = 'failed', processed_at = now(), error = :error, "
             "next_attempt_at = NULL WHERE id = :id"),
        {"id": event_id, "error": error},
    )


async def list_dead_letters(session: AsyncSession, *, limit: int = 50) -> list[dict]:
    rows = (
        await session.execute(
            text(
                "SELECT id, event_id, source, event_type, external_id, attempts, last_error, dead_at "
                "FROM sync_dead_letter ORDER BY dead_at DESC LIMIT :limit"
            ),
            {"limit": limit},
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def requeue_dead_letter(session: AsyncSession, *, dead_letter_id: uuid.UUID) -> bool:
    """Operator replay: re-arm the originating event_queue row (reset attempts/lease) and remove the
    quarantine record. When the origin row is gone (purged), RE-MATERIALIZE a fresh pending event
    from the quarantined snapshot instead — a dead-letter is always replayable. Returns False only
    if the dead-letter itself is gone."""
    row = (
        await session.execute(
            text(
                "SELECT event_id, source, event_type, external_id, payload "
                "FROM sync_dead_letter WHERE id = :id"
            ),
            {"id": dead_letter_id},
        )
    ).mappings().first()
    if not row:
        return False
    rearmed = 0
    if row["event_id"] is not None:
        result = await session.execute(
            text(
                "UPDATE event_queue SET status = 'pending', retry_count = 0, next_attempt_at = NULL, "
                "error = NULL WHERE id = :id"
            ),
            {"id": row["event_id"]},
        )
        rearmed = result.rowcount or 0
    if not rearmed:
        # Origin purged — insert a fresh pending event from the snapshot. The dedupe index
        # (tenant_id, source, external_id) still applies: if the same change was re-detected in the
        # meantime, this collapses into that row rather than duplicating it.
        await session.execute(
            text(
                """
                INSERT INTO event_queue (source, event_type, external_id, payload)
                VALUES (:source, :event_type, :external_id, CAST(:payload AS jsonb))
                ON CONFLICT (tenant_id, source, external_id) WHERE external_id IS NOT NULL
                    DO NOTHING
                """
            ),
            {"source": row["source"], "event_type": row["event_type"],
             "external_id": row["external_id"], "payload": json.dumps(_loads(row["payload"]))},
        )
    await session.execute(
        text("DELETE FROM sync_dead_letter WHERE id = :id"), {"id": dead_letter_id}
    )
    return True


async def get_tenant_by_realm(session: AsyncSession, *, realm_id: str) -> uuid.UUID | None:
    """Resolve a QuickBooks `realmId` to its tenant. Called inside an operator_session (the webhook has
    no tenant context yet); the `operator_read` policy on qbo_connection permits the SELECT."""
    row = (
        await session.execute(
            text("SELECT tenant_id FROM qbo_connection WHERE realm_id = :realm"),
            {"realm": realm_id},
        )
    ).first()
    return row[0] if row else None
