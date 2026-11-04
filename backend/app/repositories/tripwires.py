"""tripwire_orders persistence (migration 0029) — operator-global, RLS under app.operator='on'.

These are Top Builder AI's OWN tripwire sales (Stripe Payment Links) at the PLATFORM-OPERATOR
layer — NOT tenant/customer data, so NO tenant_id. Reachable only under `db.operator_session()`,
exactly like support_requests (0028) and the Ads-CRM tables (ADR 0009). House asyncpg style:
`CAST(:p AS text) IS NULL OR col = :p` for nullable filters, `CAST(:j AS jsonb)` for json,
`RETURNING *`.

Idempotency is structural: `insert_order` is INSERT .. ON CONFLICT (stripe_session_id) DO NOTHING
RETURNING * — a duplicate Stripe delivery returns None and the caller skips all side effects.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_JSONB = ("intake",)


def _row(mapping: Any) -> dict | None:
    if mapping is None:
        return None
    d = dict(mapping)
    for k in _JSONB:
        if isinstance(d.get(k), str):
            d[k] = json.loads(d[k])
    return d


async def insert_order(
    session: AsyncSession,
    *,
    product_key: str,
    stripe_session_id: str,
    stripe_payment_intent: str | None = None,
    stripe_event_id: str | None = None,
    email: str | None = None,
    name: str | None = None,
    amount_cents: int | None = None,
    currency: str = "usd",
    intake: dict | None = None,
) -> dict | None:
    """Insert one paid order. Returns the row, or None when stripe_session_id already exists
    (Stripe redelivery / duplicate event) — the idempotency contract the webhook relies on."""
    row = (
        await session.execute(
            text(
                """
                INSERT INTO tripwire_orders
                  (product_key, stripe_session_id, stripe_payment_intent, stripe_event_id,
                   email, name, amount_cents, currency, intake)
                VALUES
                  (:product_key, :stripe_session_id, :stripe_payment_intent, :stripe_event_id,
                   :email, :name, :amount_cents, :currency, CAST(:intake AS jsonb))
                ON CONFLICT (stripe_session_id) DO NOTHING
                RETURNING *
                """
            ),
            {
                "product_key": product_key,
                "stripe_session_id": stripe_session_id,
                "stripe_payment_intent": stripe_payment_intent,
                "stripe_event_id": stripe_event_id,
                "email": email,
                "name": name,
                "amount_cents": amount_cents,
                "currency": currency,
                "intake": json.dumps(intake or {}),
            },
        )
    ).mappings().first()
    return _row(row)


async def list_orders(
    session: AsyncSession, *, product_key: str | None = None, limit: int = 100
) -> list[dict]:
    rows = (
        await session.execute(
            text(
                """
                SELECT * FROM tripwire_orders
                WHERE (CAST(:product_key AS text) IS NULL OR product_key = :product_key)
                ORDER BY created_at DESC
                LIMIT :limit
                """
            ),
            {"product_key": product_key, "limit": limit},
        )
    ).mappings().all()
    return [_row(m) for m in rows]  # type: ignore[misc]


async def mark_crm_synced(session: AsyncSession, order_id: uuid.UUID) -> None:
    await session.execute(
        text("UPDATE tripwire_orders SET crm_synced_at = now() WHERE id = :id"),
        {"id": order_id},
    )
