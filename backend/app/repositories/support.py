"""support_requests persistence (migration 0028) — operator-global, RLS under app.operator='on'.

These are Top Builder AI's OWN operational signals (new signups, assistant requests, and user-submitted
bug/feature/question reports) at the PLATFORM-OPERATOR layer — NOT tenant/customer data, so NO tenant_id.
Reachable only under `db.operator_session()`, exactly like the Ads-CRM tables (ADR 0009). House asyncpg
style: `CAST(:p AS text) IS NULL OR col = :p` for nullable filters, `CAST(:j AS jsonb)` for json, `RETURNING *`.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_JSONB = ("meta",)


def _row(mapping: Any) -> dict | None:
    if mapping is None:
        return None
    d = dict(mapping)
    for k in _JSONB:
        if isinstance(d.get(k), str):
            d[k] = json.loads(d[k])
    return d


async def create_support_request(
    session: AsyncSession,
    *,
    kind: str,
    name: str | None = None,
    email: str | None = None,
    message: str | None = None,
    source: str = "in_app",
    meta: dict | None = None,
) -> dict:
    row = (
        await session.execute(
            text(
                """
                INSERT INTO support_requests (kind, name, email, message, source, meta)
                VALUES (:kind, :name, :email, :message, :source, CAST(:meta AS jsonb))
                RETURNING *
                """
            ),
            {
                "kind": kind,
                "name": name,
                "email": email,
                "message": message,
                "source": source,
                "meta": json.dumps(meta or {}),
            },
        )
    ).mappings().first()
    return _row(row)  # type: ignore[return-value]


async def list_support_requests(
    session: AsyncSession, *, kind: str | None = None, limit: int = 100
) -> list[dict]:
    rows = (
        await session.execute(
            text(
                """
                SELECT * FROM support_requests
                WHERE (CAST(:kind AS text) IS NULL OR kind = :kind)
                ORDER BY created_at DESC
                LIMIT :limit
                """
            ),
            {"kind": kind, "limit": limit},
        )
    ).mappings().all()
    return [_row(m) for m in rows]  # type: ignore[misc]


async def mark_notified(session: AsyncSession, request_id: uuid.UUID) -> None:
    await session.execute(
        text("UPDATE support_requests SET notified_at = now() WHERE id = :id"),
        {"id": request_id},
    )


async def counts_since(session: AsyncSession, *, hours: int = 24) -> tuple[dict[str, int], int]:
    """Per-kind counts of requests created in the last `hours`, plus the total. For the daily digest."""
    rows = (
        await session.execute(
            text(
                """
                SELECT kind, count(*) AS n
                FROM support_requests
                WHERE created_at >= now() - make_interval(hours => :hours)
                GROUP BY kind
                """
            ),
            {"hours": hours},
        )
    ).mappings().all()
    counts = {r["kind"]: int(r["n"]) for r in rows}
    return counts, sum(counts.values())
