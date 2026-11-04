"""Communications persistence (calls/sms/email/voicemail/web). Tenant-scoped session → RLS."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def count(session: AsyncSession) -> int:
    return (await session.execute(text("SELECT count(*) FROM communications"))).scalar_one()


async def seed(session: AsyncSession, rows: list[dict]) -> None:
    now = datetime.now(timezone.utc)
    insert = text(
        """
        INSERT INTO communications
          (channel, direction, contact_name, contact_phone, contact_email, subject, body,
           status, occurred_at, customer_ref, related_job_ref, agent_handled)
        VALUES
          (:channel, :direction, :contact_name, :contact_phone, :contact_email, :subject, :body,
           :status, :occurred_at, :customer_ref, :related_job_ref, :agent_handled)
        """
    )
    for r in rows:
        await session.execute(
            insert,
            {
                "channel": r["channel"],
                "direction": r.get("direction", "inbound"),
                "contact_name": r.get("contact_name"),
                "contact_phone": r.get("contact_phone"),
                "contact_email": r.get("contact_email"),
                "subject": r.get("subject"),
                "body": r.get("body"),
                "status": r.get("status", "new"),
                "occurred_at": now - timedelta(minutes=float(r.get("minutes_ago", 0))),
                "customer_ref": r.get("customer_ref"),
                "related_job_ref": r.get("related_job_ref"),
                "agent_handled": bool(r.get("agent_handled", False)),
            },
        )


async def list_(
    session: AsyncSession, *, channel: str | None = None, status: str | None = None, limit: int = 100
) -> list[dict]:
    rows = (
        await session.execute(
            text(
                """
                SELECT * FROM communications
                WHERE (CAST(:channel AS text) IS NULL OR channel = :channel)
                  AND (CAST(:status AS text) IS NULL OR status = :status)
                ORDER BY occurred_at DESC LIMIT :limit
                """
            ),
            {"channel": channel, "status": status, "limit": limit},
        )
    ).mappings().all()
    return [dict(m) for m in rows]


async def insert_outbound(
    session: AsyncSession, *, channel: str, contact_name: str | None, contact_phone: str | None,
    contact_email: str | None, subject: str | None, body: str | None,
) -> dict:
    row = (
        await session.execute(
            text(
                """
                INSERT INTO communications
                  (channel, direction, contact_name, contact_phone, contact_email, subject, body,
                   status, agent_handled)
                VALUES (:channel, 'outbound', :cn, :cp, :ce, :subject, :body, 'sent', true)
                RETURNING *
                """
            ),
            {"channel": channel, "cn": contact_name, "cp": contact_phone, "ce": contact_email,
             "subject": subject, "body": body},
        )
    ).mappings().first()
    return dict(row)


async def set_status(session: AsyncSession, *, comm_id: uuid.UUID, status: str) -> dict | None:
    row = (
        await session.execute(
            text("UPDATE communications SET status = :s WHERE id = :id RETURNING *"),
            {"s": status, "id": comm_id},
        )
    ).mappings().first()
    return dict(row) if row else None
