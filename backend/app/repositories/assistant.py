"""Assistant persistence: the per-tenant daily usage counter (cost guardrail) and the
email-workflow overrides the admin assistant applies. Tenant-scoped sessions, RLS-isolated."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def increment_usage(session: AsyncSession) -> int:
    """Count one assistant message for today; returns the count AFTER incrementing."""
    row = (
        await session.execute(
            text(
                "INSERT INTO assistant_usage (day, used) VALUES (CURRENT_DATE, 1) "
                "ON CONFLICT (tenant_id, day) DO UPDATE SET used = assistant_usage.used + 1 "
                "RETURNING used"
            )
        )
    ).first()
    return int(row[0])


async def get_usage(session: AsyncSession) -> int:
    row = (
        await session.execute(
            text("SELECT used FROM assistant_usage WHERE day = CURRENT_DATE")
        )
    ).first()
    return int(row[0]) if row else 0


async def list_email_overrides(session: AsyncSession) -> list[dict]:
    rows = (
        await session.execute(
            text(
                "SELECT workflow_id, subject, preview, rationale, updated_by, updated_at "
                "FROM email_workflow_overrides ORDER BY updated_at DESC"
            )
        )
    ).mappings().all()
    return [dict(m) for m in rows]


async def upsert_email_override(
    session: AsyncSession, *, workflow_id: str, subject: str, preview: str,
    rationale: str, updated_by: str,
) -> dict:
    row = (
        await session.execute(
            text(
                """
                INSERT INTO email_workflow_overrides (workflow_id, subject, preview, rationale, updated_by)
                VALUES (:wid, :subject, :preview, :rationale, :by)
                ON CONFLICT (tenant_id, workflow_id) DO UPDATE
                   SET subject = EXCLUDED.subject, preview = EXCLUDED.preview,
                       rationale = EXCLUDED.rationale, updated_by = EXCLUDED.updated_by,
                       updated_at = now()
                RETURNING workflow_id, subject, preview, rationale, updated_by, updated_at
                """
            ),
            {"wid": workflow_id, "subject": subject, "preview": preview,
             "rationale": rationale, "by": updated_by},
        )
    ).mappings().first()
    return dict(row)
