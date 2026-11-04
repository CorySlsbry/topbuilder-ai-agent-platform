"""DB integration tests for dead-letter replay (ADR 0010).

Proves the operator replay path in both shapes: (a) the origin `event_queue` row still exists ->
it is re-armed (pending, attempts reset); (b) the origin row was PURGED -> a fresh pending event is
RE-MATERIALIZED from the quarantined snapshot, so a dead-letter is always replayable.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.db import tenant_session
from app.demo import DEMO_TENANTS
from app.repositories import events as events_repo
from app.repositories import sync as sync_repo
from app.sync import normalize, service

pytestmark = pytest.mark.integration


async def _enqueue_bill(tenant: uuid.UUID, bill_id: int, modified: str) -> str:
    event = normalize.normalize_st_export_row(
        "bill", {"id": bill_id, "modifiedOn": modified, "total": 10.0}, verb="created"
    )
    assert await service.enqueue_events(tenant, [event]) == 1
    return event.natural_key


async def _event_row(session, external_id: str) -> dict | None:
    row = (
        await session.execute(
            text(
                "SELECT id, status, retry_count, payload FROM event_queue "
                "WHERE external_id = :ext"
            ),
            {"ext": external_id},
        )
    ).mappings().first()
    return dict(row) if row else None


async def _quarantine(session, origin: dict, external_id: str) -> uuid.UUID:
    await sync_repo.dead_letter_event(
        session,
        event_id=origin["id"],
        source="servicetitan",
        event_type="accounting.bill.created",
        external_id=external_id,
        payload={"entity": "bill", "row": {"id": 1}},
        attempts=5,
        error="poison",
    )
    row = (
        await session.execute(
            text(
                "SELECT id FROM sync_dead_letter WHERE external_id = :ext "
                "ORDER BY dead_at DESC LIMIT 1"
            ),
            {"ext": external_id},
        )
    ).first()
    assert row is not None
    return row[0]


async def test_replay_rearms_the_origin_event_when_it_still_exists() -> None:
    from app import db

    tenant = DEMO_TENANTS["apex"].tenant_id
    try:
        external_id = await _enqueue_bill(tenant, 55001, "2026-06-30T10:00:00Z")
        async with tenant_session(tenant) as session:
            origin = await _event_row(session, external_id)
            assert origin is not None
            dead_id = await _quarantine(session, origin, external_id)

        async with tenant_session(tenant) as session:
            assert await sync_repo.requeue_dead_letter(session, dead_letter_id=dead_id) is True

        async with tenant_session(tenant) as session:
            rearmed = await _event_row(session, external_id)
            assert rearmed is not None
            assert rearmed["id"] == origin["id"]  # the SAME row, re-armed — not a duplicate
            assert rearmed["status"] == "pending"
            assert rearmed["retry_count"] == 0
            assert all(d["id"] != dead_id for d in await sync_repo.list_dead_letters(session))
    finally:
        await db.get_engine().dispose()
        db.get_engine.cache_clear()
        db.get_sessionmaker.cache_clear()


async def test_replay_rematerializes_a_fresh_event_when_the_origin_was_purged() -> None:
    from app import db

    tenant = DEMO_TENANTS["apex"].tenant_id
    try:
        external_id = await _enqueue_bill(tenant, 55002, "2026-06-30T11:00:00Z")
        async with tenant_session(tenant) as session:
            origin = await _event_row(session, external_id)
            assert origin is not None
            dead_id = await _quarantine(session, origin, external_id)
            # Simulate a retention purge of the origin inbox row.
            await session.execute(
                text("DELETE FROM event_queue WHERE id = :id"), {"id": origin["id"]}
            )

        async with tenant_session(tenant) as session:
            assert await sync_repo.requeue_dead_letter(session, dead_letter_id=dead_id) is True

        async with tenant_session(tenant) as session:
            fresh = await _event_row(session, external_id)
            assert fresh is not None
            assert fresh["id"] != origin["id"]  # a NEW row, materialized from the snapshot
            assert fresh["status"] == "pending"
            assert fresh["retry_count"] == 0
            remaining = [d for d in await sync_repo.list_dead_letters(session) if d["id"] == dead_id]
            assert remaining == []

        # The re-materialized event drains like any other (route -> advisory/propose, no crash).
        result = await service.drain_tenant(tenant)
        assert result["failed"] == 0
    finally:
        await db.get_engine().dispose()
        db.get_engine.cache_clear()
        db.get_sessionmaker.cache_clear()
