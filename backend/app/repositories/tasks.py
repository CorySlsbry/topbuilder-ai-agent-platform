"""Task persistence (agent-generated worklist + manual). Tenant-scoped session → RLS."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def count(session: AsyncSession) -> int:
    return (await session.execute(text("SELECT count(*) FROM tasks"))).scalar_one()


async def seed(session: AsyncSession, rows: list[dict]) -> None:
    now = datetime.now(timezone.utc)
    insert = text(
        """
        INSERT INTO tasks
          (title, detail, department, status, priority, source_agent, related_ref, assignee_role, due_at)
        VALUES
          (:title, :detail, :department, :status, :priority, :source_agent, :related_ref, :assignee_role, :due_at)
        """
    )
    for r in rows:
        due = r.get("due_in_hours")
        await session.execute(
            insert,
            {
                "title": r["title"],
                "detail": r.get("detail"),
                "department": r.get("department", "front_desk"),
                "status": r.get("status", "open"),
                "priority": int(r.get("priority", 3)),
                "source_agent": r.get("source_agent"),
                "related_ref": r.get("related_ref"),
                "assignee_role": r.get("assignee_role"),
                "due_at": (now + timedelta(hours=float(due))) if due is not None else None,
            },
        )


async def list_(
    session: AsyncSession, *, department: str | None = None, status: str | None = None, limit: int = 100
) -> list[dict]:
    rows = (
        await session.execute(
            text(
                """
                SELECT * FROM tasks
                WHERE (CAST(:department AS text) IS NULL OR department = :department)
                  AND (CAST(:status AS text) IS NULL OR status = :status)
                ORDER BY (status = 'done'), priority DESC, created_at DESC LIMIT :limit
                """
            ),
            {"department": department, "status": status, "limit": limit},
        )
    ).mappings().all()
    return [dict(m) for m in rows]


async def insert(
    session: AsyncSession, *, title: str, detail: str | None, department: str, priority: int,
    source_agent: str | None, related_ref: str | None, assignee_role: str | None,
) -> dict:
    row = (
        await session.execute(
            text(
                """
                INSERT INTO tasks (title, detail, department, priority, source_agent, related_ref, assignee_role)
                VALUES (:title, :detail, :department, :priority, :source_agent, :related_ref, :assignee_role)
                RETURNING *
                """
            ),
            {"title": title, "detail": detail, "department": department, "priority": priority,
             "source_agent": source_agent, "related_ref": related_ref, "assignee_role": assignee_role},
        )
    ).mappings().first()
    return dict(row)


async def update(
    session: AsyncSession, *, task_id: uuid.UUID, status: str | None = None, assignee_role: str | None = None
) -> dict | None:
    row = (
        await session.execute(
            text(
                """
                UPDATE tasks
                   SET status = COALESCE(:status, status),
                       assignee_role = COALESCE(:assignee_role, assignee_role)
                 WHERE id = :id
                RETURNING *
                """
            ),
            {"status": status, "assignee_role": assignee_role, "id": task_id},
        )
    ).mappings().first()
    return dict(row) if row else None
