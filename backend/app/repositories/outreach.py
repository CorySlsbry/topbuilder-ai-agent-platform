"""Persistence for outreach authority + the send ledger (migration 0027).

The send_outreach_email executor resolves every compliance fact from HERE (never from action
params, which the proposer controls): the authoritative contact record, the suppression list, and
the per-subdomain send counts that make the warm-up cap enforceable. Runs on a tenant-scoped
session (RLS confines every read/write to the executing action's tenant).
"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def resolve_contact(session: AsyncSession, *, email_normalized: str) -> dict | None:
    """The authoritative facts for one contact, or None (unresolvable => the caller HOLDS)."""
    row = (
        await session.execute(
            text(
                "SELECT email_normalized, country, consent, consent_basis, bounced, unsubscribed "
                "FROM outreach_contacts WHERE email_normalized = :e"
            ),
            {"e": email_normalized},
        )
    ).mappings().first()
    return dict(row) if row else None


async def add_suppression(
    session: AsyncSession, *, email_normalized: str, reason: str = "manual"
) -> None:
    """Add (or keep) a suppression entry — idempotent per (tenant, email). Used by unsubscribe
    handling and the outreach-send undo (retract a mistaken send)."""
    await session.execute(
        text(
            "INSERT INTO email_suppression (email_normalized, reason) VALUES (:e, :r) "
            "ON CONFLICT (tenant_id, email_normalized) DO NOTHING"
        ),
        {"e": email_normalized, "r": reason},
    )


async def is_suppressed(session: AsyncSession, *, email_normalized: str) -> bool:
    row = (
        await session.execute(
            text("SELECT 1 FROM email_suppression WHERE email_normalized = :e LIMIT 1"),
            {"e": email_normalized},
        )
    ).first()
    return row is not None


async def sent_today_count(session: AsyncSession, *, subdomain: str) -> int:
    """Sends already recorded today (UTC) for this sending subdomain — the warm-up cap meter."""
    row = (
        await session.execute(
            text(
                "SELECT count(*) FROM outreach_sends "
                "WHERE subdomain = :d AND sent_at >= date_trunc('day', now() AT TIME ZONE 'utc')"
            ),
            {"d": subdomain},
        )
    ).first()
    return int(row[0]) if row else 0


async def first_send_at(session: AsyncSession, *, subdomain: str) -> dt.datetime | None:
    """The subdomain's first-ever send (its warm-up age anchor). None = never sent (day 0)."""
    row = (
        await session.execute(
            text("SELECT min(sent_at) FROM outreach_sends WHERE subdomain = :d"), {"d": subdomain}
        )
    ).first()
    return row[0] if row else None


async def record_send(
    session: AsyncSession,
    *,
    email_normalized: str,
    subdomain: str,
    action_id: uuid.UUID | None = None,
) -> None:
    await session.execute(
        text(
            "INSERT INTO outreach_sends (contact_email_normalized, subdomain, action_id) "
            "VALUES (:e, :d, :a)"
        ),
        {"e": email_normalized, "d": subdomain, "a": action_id},
    )
