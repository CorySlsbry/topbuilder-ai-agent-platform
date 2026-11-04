"""Daily usage counters — generic cost/abuse guardrails (migration 0018).

`bump_tenant` runs inside the caller's tenant_session (RLS-scoped). `bump_global` runs on a plain
session and meters non-tenant buckets (per-IP, global) — these are DB-backed so the ceilings hold
ACROSS Cloud Run instances (the in-process rate limiter does not). Each returns the count AFTER
incrementing, so the caller compares against its limit.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def bump_tenant(session: AsyncSession, *, bucket: str, amount: int = 1) -> int:
    row = (
        await session.execute(
            text(
                "INSERT INTO daily_counters (day, bucket, used) VALUES (CURRENT_DATE, :b, :n) "
                "ON CONFLICT (tenant_id, day, bucket) DO UPDATE SET used = daily_counters.used + :n "
                "RETURNING used"
            ),
            {"b": bucket, "n": amount},
        )
    ).first()
    return int(row[0])


async def bump_global(session: AsyncSession, *, bucket: str, amount: int = 1) -> int:
    row = (
        await session.execute(
            text(
                "INSERT INTO global_counters (day, bucket, used) VALUES (CURRENT_DATE, :b, :n) "
                "ON CONFLICT (day, bucket) DO UPDATE SET used = global_counters.used + :n "
                "RETURNING used"
            ),
            {"b": bucket, "n": amount},
        )
    ).first()
    return int(row[0])
