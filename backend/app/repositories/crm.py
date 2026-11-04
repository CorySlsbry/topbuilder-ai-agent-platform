"""CRM persistence — contacts / leads / activities (ADR 0009). Operator-session-scoped → RLS.

These are Top Builder AI's OWN go-to-market leads (NOT tenant/customer data); they carry no tenant_id
and are reachable only under `db.operator_session()` (app.operator='on'). Mirrors the house asyncpg
style: `CAST(:p AS text) IS NULL OR col = :p` for nullable filters, `CAST(:j AS jsonb)` for json columns,
`RETURNING *`. A stage change is never a bare UPDATE — it also writes a `stage_change` activity so the
lead's history is append-only and auditable. Money is integer CENTS (`value_cents`).
"""
from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# jsonb columns decoded back to dicts on the way out (asyncpg may hand them back as str)
_CONTACT_JSONB = ("meta",)
_LEAD_JSONB = ("utm", "ad_ref")
_ACTIVITY_JSONB = ("detail",)


def _row(mapping: Any, jsonb: tuple[str, ...] = ()) -> dict | None:
    if mapping is None:
        return None
    d = dict(mapping)
    for k in jsonb:
        if isinstance(d.get(k), str):
            d[k] = json.loads(d[k])
    return d


# ── contacts ──────────────────────────────────────────────────────────────────────────────────────
async def upsert_contact(
    session: AsyncSession,
    *,
    email: str | None = None,
    phone: str | None = None,
    full_name: str | None = None,
    company: str | None = None,
    title: str | None = None,
    meta: dict | None = None,
) -> dict:
    """Insert or update a contact, deduped by email (the UNIQUE key).

    On a known email, non-null fields overwrite (COALESCE keeps an existing value when the new one is
    null), so re-ingesting the same lead enriches rather than clobbers. With no email there is nothing
    to dedupe on, so a fresh contact row is inserted.
    """
    if email:
        row = (
            await session.execute(
                text(
                    """
                    INSERT INTO crm_contacts (email, phone, full_name, company, title, meta)
                    VALUES (:email, :phone, :full_name, :company, :title, CAST(:meta AS jsonb))
                    ON CONFLICT (email) DO UPDATE SET
                        phone     = COALESCE(EXCLUDED.phone, crm_contacts.phone),
                        full_name = COALESCE(EXCLUDED.full_name, crm_contacts.full_name),
                        company   = COALESCE(EXCLUDED.company, crm_contacts.company),
                        title     = COALESCE(EXCLUDED.title, crm_contacts.title),
                        meta      = crm_contacts.meta || EXCLUDED.meta,
                        updated_at = now()
                    RETURNING *
                    """
                ),
                {"email": email, "phone": phone, "full_name": full_name, "company": company,
                 "title": title, "meta": json.dumps(meta or {})},
            )
        ).mappings().first()
    else:
        row = (
            await session.execute(
                text(
                    """
                    INSERT INTO crm_contacts (email, phone, full_name, company, title, meta)
                    VALUES (NULL, :phone, :full_name, :company, :title, CAST(:meta AS jsonb))
                    RETURNING *
                    """
                ),
                {"phone": phone, "full_name": full_name, "company": company, "title": title,
                 "meta": json.dumps(meta or {})},
            )
        ).mappings().first()
    return _row(row, _CONTACT_JSONB)  # type: ignore[return-value]


# ── leads ─────────────────────────────────────────────────────────────────────────────────────────
async def create_lead(
    session: AsyncSession,
    *,
    contact_id: uuid.UUID | None,
    stage: str = "new",
    source: str = "manual",
    value_cents: int = 0,
    utm: dict | None = None,
    ad_ref: dict | None = None,
    owner: str | None = None,
) -> dict:
    row = (
        await session.execute(
            text(
                """
                INSERT INTO crm_leads
                  (contact_id, stage, source, value_cents, utm, ad_ref, owner)
                VALUES
                  (:contact_id, :stage, :source, :value_cents,
                   CAST(:utm AS jsonb), CAST(:ad_ref AS jsonb), :owner)
                RETURNING *
                """
            ),
            {"contact_id": contact_id, "stage": stage, "source": source,
             "value_cents": int(value_cents), "utm": json.dumps(utm or {}),
             "ad_ref": json.dumps(ad_ref or {}), "owner": owner},
        )
    ).mappings().first()
    return _row(row, _LEAD_JSONB)  # type: ignore[return-value]


async def get_lead(session: AsyncSession, *, lead_id: uuid.UUID) -> dict | None:
    row = (
        await session.execute(
            text("SELECT * FROM crm_leads WHERE id = :id"), {"id": lead_id}
        )
    ).mappings().first()
    return _row(row, _LEAD_JSONB)


async def list_leads(
    session: AsyncSession, *, stage: str | None = None, limit: int = 100
) -> list[dict]:
    rows = (
        await session.execute(
            text(
                """
                SELECT * FROM crm_leads
                WHERE (CAST(:stage AS text) IS NULL OR stage = :stage)
                ORDER BY created_at DESC LIMIT :limit
                """
            ),
            {"stage": stage, "limit": limit},
        )
    ).mappings().all()
    return [_row(m, _LEAD_JSONB) for m in rows]  # type: ignore[misc]


async def set_stage(
    session: AsyncSession,
    *,
    lead_id: uuid.UUID,
    stage: str,
    actor: str | None = None,
    lost_reason: str | None = None,
) -> dict | None:
    """Move a lead to a new stage AND record a `stage_change` activity (append-only history).

    Returns None if the lead doesn't exist (the UPDATE matched nothing). The activity captures the
    from/to stages in `detail` so the pipeline movement is fully auditable.
    """
    current = await get_lead(session, lead_id=lead_id)
    if current is None:
        return None
    updated = (
        await session.execute(
            text(
                """
                UPDATE crm_leads
                   SET stage = :stage,
                       lost_reason = CASE WHEN :stage = 'lost' THEN :lost_reason ELSE lost_reason END,
                       updated_at = now()
                 WHERE id = :id
                RETURNING *
                """
            ),
            {"id": lead_id, "stage": stage, "lost_reason": lost_reason},
        )
    ).mappings().first()
    if updated is None:
        return None
    await add_activity(
        session,
        lead_id=lead_id,
        kind="stage_change",
        body=f"{current['stage']} → {stage}",
        detail={"from": current["stage"], "to": stage, "lost_reason": lost_reason},
        actor=actor,
    )
    return _row(updated, _LEAD_JSONB)


# ── activities ────────────────────────────────────────────────────────────────────────────────────
async def add_activity(
    session: AsyncSession,
    *,
    lead_id: uuid.UUID,
    kind: str,
    body: str | None = None,
    detail: dict | None = None,
    actor: str | None = None,
) -> dict:
    row = (
        await session.execute(
            text(
                """
                INSERT INTO crm_activities (lead_id, kind, body, detail, actor)
                VALUES (:lead_id, :kind, :body, CAST(:detail AS jsonb), :actor)
                RETURNING *
                """
            ),
            {"lead_id": lead_id, "kind": kind, "body": body,
             "detail": json.dumps(detail or {}), "actor": actor},
        )
    ).mappings().first()
    return _row(row, _ACTIVITY_JSONB)  # type: ignore[return-value]


async def list_activities(
    session: AsyncSession, *, lead_id: uuid.UUID, limit: int = 100
) -> list[dict]:
    rows = (
        await session.execute(
            text(
                """
                SELECT * FROM crm_activities
                WHERE lead_id = :lead_id
                ORDER BY created_at DESC LIMIT :limit
                """
            ),
            {"lead_id": lead_id, "limit": limit},
        )
    ).mappings().all()
    return [_row(m, _ACTIVITY_JSONB) for m in rows]  # type: ignore[misc]


# ── combined ingest ─────────────────────────────────────────────────────────────────────────────────
async def ingest_lead(
    session: AsyncSession,
    *,
    email: str | None = None,
    phone: str | None = None,
    full_name: str | None = None,
    company: str | None = None,
    title: str | None = None,
    contact_meta: dict | None = None,
    stage: str = "new",
    source: str = "manual",
    value_cents: int = 0,
    utm: dict | None = None,
    ad_ref: dict | None = None,
    owner: str | None = None,
    activity_kind: str = "system",
    activity_body: str | None = None,
    activity_detail: dict | None = None,
    actor: str | None = None,
) -> dict:
    """Upsert the contact (dedupe by email) + create a lead + seed an opening activity in one call.

    The single entry point a webhook / landing-form / ad-lead handler calls. Returns
    {contact, lead, activity}. Contact dedupe is by email; with no email a fresh contact is created.
    """
    contact = await upsert_contact(
        session, email=email, phone=phone, full_name=full_name,
        company=company, title=title, meta=contact_meta,
    )
    lead = await create_lead(
        session, contact_id=contact["id"], stage=stage, source=source,
        value_cents=value_cents, utm=utm, ad_ref=ad_ref, owner=owner,
    )
    activity = await add_activity(
        session, lead_id=lead["id"], kind=activity_kind,
        body=activity_body or f"Lead created from {source}",
        detail=activity_detail, actor=actor,
    )
    return {"contact": contact, "lead": lead, "activity": activity}
