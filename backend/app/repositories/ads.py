"""Ad-platform persistence — accounts / templates / campaigns / metrics / conversions (ADR 0009).

Operator-session-scoped → RLS (app.operator='on'). Holds Top Builder AI's OWN ad-campaign state for
Meta / Google. Money is integer CENTS everywhere (`*_cents`). NOTHING here writes to an ad platform —
all platform WRITES go through the action gate (ADR 0007) and the live adapter; this module only
records the resulting rows. Conversion sends are idempotent at the DB layer
(`ON CONFLICT (platform, dedupe_key) DO NOTHING`); PII in `payload` is ALREADY SHA-256 hashed by the
caller (never plaintext here). House asyncpg style: nullable filters via `CAST(:p AS text) IS NULL OR
col = :p`, json columns via `CAST(:j AS jsonb)`, status transitions guarded with `WHERE status = ...`.
"""
from __future__ import annotations

import json
import uuid
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_ACCOUNT_JSONB = ("metadata",)
_TEMPLATE_JSONB = ("geo_spec", "targeting_spec", "schedule_spec", "budget_spec", "creative_spec")
_CAMPAIGN_JSONB = ("external_ids",)
_METRIC_JSONB = ("raw",)
_CONVERSION_JSONB = ("payload",)


def _row(mapping: Any, jsonb: tuple[str, ...] = ()) -> dict | None:
    if mapping is None:
        return None
    d = dict(mapping)
    for k in jsonb:
        if isinstance(d.get(k), str):
            d[k] = json.loads(d[k])
    return d


# ── ad accounts ─────────────────────────────────────────────────────────────────────────────────────
async def upsert_ad_account(
    session: AsyncSession,
    *,
    platform: str,
    external_account_id: str,
    display_name: str | None = None,
    vault_credential_id: uuid.UUID | None = None,
    status: str = "disconnected",
    metadata: dict | None = None,
) -> dict:
    """Insert or update an ad account, idempotent on (platform, external_account_id)."""
    row = (
        await session.execute(
            text(
                """
                INSERT INTO ad_accounts
                  (platform, external_account_id, display_name, vault_credential_id, status, metadata)
                VALUES
                  (:platform, :ext, :display_name, :vault, :status, CAST(:md AS jsonb))
                ON CONFLICT (platform, external_account_id) DO UPDATE SET
                    display_name        = COALESCE(EXCLUDED.display_name, ad_accounts.display_name),
                    vault_credential_id = COALESCE(EXCLUDED.vault_credential_id, ad_accounts.vault_credential_id),
                    status              = EXCLUDED.status,
                    metadata            = ad_accounts.metadata || EXCLUDED.metadata,
                    updated_at          = now()
                RETURNING *
                """
            ),
            {"platform": platform, "ext": external_account_id, "display_name": display_name,
             "vault": vault_credential_id, "status": status, "md": json.dumps(metadata or {})},
        )
    ).mappings().first()
    return _row(row, _ACCOUNT_JSONB)  # type: ignore[return-value]


async def list_ad_accounts(
    session: AsyncSession, *, platform: str | None = None
) -> list[dict]:
    rows = (
        await session.execute(
            text(
                """
                SELECT * FROM ad_accounts
                WHERE (CAST(:platform AS text) IS NULL OR platform = :platform)
                ORDER BY platform, created_at DESC
                """
            ),
            {"platform": platform},
        )
    ).mappings().all()
    return [_row(m, _ACCOUNT_JSONB) for m in rows]  # type: ignore[misc]


# ── templates ─────────────────────────────────────────────────────────────────────────────────────
async def create_template(
    session: AsyncSession,
    *,
    slug: str,
    name: str,
    objective: str,
    template_type: str = "trade_show_geofence",
    geo_spec: dict | None = None,
    targeting_spec: dict | None = None,
    schedule_spec: dict | None = None,
    budget_spec: dict | None = None,
    creative_spec: dict | None = None,
) -> dict:
    """Insert or update a campaign template, idempotent on slug."""
    row = (
        await session.execute(
            text(
                """
                INSERT INTO ad_campaign_templates
                  (slug, name, template_type, objective, geo_spec, targeting_spec,
                   schedule_spec, budget_spec, creative_spec)
                VALUES
                  (:slug, :name, :ttype, :objective, CAST(:geo AS jsonb), CAST(:targeting AS jsonb),
                   CAST(:schedule AS jsonb), CAST(:budget AS jsonb), CAST(:creative AS jsonb))
                ON CONFLICT (slug) DO UPDATE SET
                    name           = EXCLUDED.name,
                    template_type  = EXCLUDED.template_type,
                    objective      = EXCLUDED.objective,
                    geo_spec       = EXCLUDED.geo_spec,
                    targeting_spec = EXCLUDED.targeting_spec,
                    schedule_spec  = EXCLUDED.schedule_spec,
                    budget_spec    = EXCLUDED.budget_spec,
                    creative_spec  = EXCLUDED.creative_spec,
                    updated_at     = now()
                RETURNING *
                """
            ),
            {"slug": slug, "name": name, "ttype": template_type, "objective": objective,
             "geo": json.dumps(geo_spec or {}), "targeting": json.dumps(targeting_spec or {}),
             "schedule": json.dumps(schedule_spec or {}), "budget": json.dumps(budget_spec or {}),
             "creative": json.dumps(creative_spec or {})},
        )
    ).mappings().first()
    return _row(row, _TEMPLATE_JSONB)  # type: ignore[return-value]


async def get_template(
    session: AsyncSession, *, slug: str | None = None, template_id: uuid.UUID | None = None
) -> dict | None:
    if slug is not None:
        row = (
            await session.execute(
                text("SELECT * FROM ad_campaign_templates WHERE slug = :slug"), {"slug": slug}
            )
        ).mappings().first()
    elif template_id is not None:
        row = (
            await session.execute(
                text("SELECT * FROM ad_campaign_templates WHERE id = :id"), {"id": template_id}
            )
        ).mappings().first()
    else:
        raise ValueError("get_template requires slug or template_id")
    return _row(row, _TEMPLATE_JSONB)


async def list_templates(session: AsyncSession) -> list[dict]:
    rows = (
        await session.execute(
            text("SELECT * FROM ad_campaign_templates ORDER BY created_at DESC")
        )
    ).mappings().all()
    return [_row(m, _TEMPLATE_JSONB) for m in rows]  # type: ignore[misc]


# ── campaigns ─────────────────────────────────────────────────────────────────────────────────────
async def create_campaign_row(
    session: AsyncSession,
    *,
    platform: str,
    name: str,
    template_id: uuid.UUID | None = None,
    ad_account_id: uuid.UUID | None = None,
    status: str = "draft",
    daily_budget_cents: int = 0,
    lifetime_cap_cents: int = 0,
    start_at: Any = None,
    end_at: Any = None,
    external_campaign_id: str | None = None,
    external_ids: dict | None = None,
) -> dict:
    """Insert a campaign ROW (local record only — no platform write happens here)."""
    row = (
        await session.execute(
            text(
                """
                INSERT INTO ad_campaigns
                  (template_id, ad_account_id, platform, name, status, external_campaign_id,
                   external_ids, daily_budget_cents, lifetime_cap_cents, start_at, end_at)
                VALUES
                  (:template_id, :ad_account_id, :platform, :name, :status, :ext_campaign,
                   CAST(:ext_ids AS jsonb), :daily, :lifetime, :start_at, :end_at)
                RETURNING *
                """
            ),
            {"template_id": template_id, "ad_account_id": ad_account_id, "platform": platform,
             "name": name, "status": status, "ext_campaign": external_campaign_id,
             "ext_ids": json.dumps(external_ids or {}), "daily": int(daily_budget_cents),
             "lifetime": int(lifetime_cap_cents), "start_at": start_at, "end_at": end_at},
        )
    ).mappings().first()
    return _row(row, _CAMPAIGN_JSONB)  # type: ignore[return-value]


async def get_campaign(session: AsyncSession, *, campaign_id: uuid.UUID) -> dict | None:
    row = (
        await session.execute(
            text("SELECT * FROM ad_campaigns WHERE id = :id"), {"id": campaign_id}
        )
    ).mappings().first()
    return _row(row, _CAMPAIGN_JSONB)


async def list_campaigns(
    session: AsyncSession, *, status: str | None = None, platform: str | None = None, limit: int = 100
) -> list[dict]:
    rows = (
        await session.execute(
            text(
                """
                SELECT * FROM ad_campaigns
                WHERE (CAST(:status AS text) IS NULL OR status = :status)
                  AND (CAST(:platform AS text) IS NULL OR platform = :platform)
                ORDER BY created_at DESC LIMIT :limit
                """
            ),
            {"status": status, "platform": platform, "limit": limit},
        )
    ).mappings().all()
    return [_row(m, _CAMPAIGN_JSONB) for m in rows]  # type: ignore[misc]


async def update_campaign_status(
    session: AsyncSession, *, campaign_id: uuid.UUID, status: str
) -> dict | None:
    """Set a campaign's lifecycle status (draft|paused|active|ended|error). Returns None if missing."""
    row = (
        await session.execute(
            text(
                """
                UPDATE ad_campaigns SET status = :status, updated_at = now()
                WHERE id = :id RETURNING *
                """
            ),
            {"id": campaign_id, "status": status},
        )
    ).mappings().first()
    return _row(row, _CAMPAIGN_JSONB)


async def update_campaign_external_ids(
    session: AsyncSession,
    *,
    campaign_id: uuid.UUID,
    external_campaign_id: str | None = None,
    external_ids: dict | None = None,
) -> dict | None:
    """Record the platform ids returned after a real create (merges into external_ids, never clobbers).

    Called once the action-gated live create succeeds, to bind our row to the platform objects
    (adset_id, adcreative_id, ad_id, ...). `external_ids` is merged with `||` so partial syncs
    accumulate. Returns None if the campaign is missing.
    """
    row = (
        await session.execute(
            text(
                """
                UPDATE ad_campaigns
                   SET external_campaign_id = COALESCE(:ext_campaign, external_campaign_id),
                       external_ids = external_ids || CAST(:ext_ids AS jsonb),
                       last_synced_at = now(),
                       updated_at = now()
                 WHERE id = :id
                RETURNING *
                """
            ),
            {"id": campaign_id, "ext_campaign": external_campaign_id,
             "ext_ids": json.dumps(external_ids or {})},
        )
    ).mappings().first()
    return _row(row, _CAMPAIGN_JSONB)


async def update_campaign_spend(
    session: AsyncSession, *, campaign_id: uuid.UUID, spend_cents: int
) -> dict | None:
    """Set the campaign's running spend in CENTS (from the metrics sync). Returns None if missing."""
    row = (
        await session.execute(
            text(
                """
                UPDATE ad_campaigns
                   SET spend_cents = :spend, last_synced_at = now(), updated_at = now()
                 WHERE id = :id
                RETURNING *
                """
            ),
            {"id": campaign_id, "spend": int(spend_cents)},
        )
    ).mappings().first()
    return _row(row, _CAMPAIGN_JSONB)


# ── metrics ───────────────────────────────────────────────────────────────────────────────────────
async def upsert_metrics(
    session: AsyncSession,
    *,
    campaign_id: uuid.UUID,
    day: date,
    impressions: int = 0,
    clicks: int = 0,
    landing_page_views: int = 0,
    leads: int = 0,
    spend_cents: int = 0,
    raw: dict | None = None,
) -> dict:
    """Insert or replace a campaign's metrics for one day (idempotent on campaign_id, day)."""
    row = (
        await session.execute(
            text(
                """
                INSERT INTO ad_metrics
                  (campaign_id, day, impressions, clicks, landing_page_views, leads, spend_cents, raw)
                VALUES
                  (:campaign_id, :day, :impressions, :clicks, :lpv, :leads, :spend, CAST(:raw AS jsonb))
                ON CONFLICT (campaign_id, day) DO UPDATE SET
                    impressions        = EXCLUDED.impressions,
                    clicks             = EXCLUDED.clicks,
                    landing_page_views = EXCLUDED.landing_page_views,
                    leads              = EXCLUDED.leads,
                    spend_cents        = EXCLUDED.spend_cents,
                    raw                = EXCLUDED.raw
                RETURNING *
                """
            ),
            {"campaign_id": campaign_id, "day": day, "impressions": int(impressions),
             "clicks": int(clicks), "lpv": int(landing_page_views), "leads": int(leads),
             "spend": int(spend_cents), "raw": json.dumps(raw or {})},
        )
    ).mappings().first()
    return _row(row, _METRIC_JSONB)  # type: ignore[return-value]


async def list_metrics(
    session: AsyncSession, *, campaign_id: uuid.UUID, limit: int = 365
) -> list[dict]:
    rows = (
        await session.execute(
            text(
                """
                SELECT * FROM ad_metrics
                WHERE campaign_id = :campaign_id
                ORDER BY day DESC LIMIT :limit
                """
            ),
            {"campaign_id": campaign_id, "limit": limit},
        )
    ).mappings().all()
    return [_row(m, _METRIC_JSONB) for m in rows]  # type: ignore[misc]


# ── conversion syncs ────────────────────────────────────────────────────────────────────────────────
async def create_conversion_sync(
    session: AsyncSession,
    *,
    platform: str,
    event_name: str,
    dedupe_key: str,
    lead_id: uuid.UUID | None = None,
    payload: dict | None = None,
) -> dict | None:
    """Queue one conversion send, idempotent on (platform, dedupe_key).

    Returns the new row, or None if a send for this (platform, dedupe_key) already exists (the
    `ON CONFLICT DO NOTHING` matched) — so the same conversion is never sent twice. `payload` PII is
    ALREADY SHA-256 hashed by the caller; this module never hashes or logs plaintext.
    """
    row = (
        await session.execute(
            text(
                """
                INSERT INTO conversion_syncs
                  (lead_id, platform, event_name, dedupe_key, payload)
                VALUES (:lead_id, :platform, :event_name, :dedupe_key, CAST(:payload AS jsonb))
                ON CONFLICT (platform, dedupe_key) DO NOTHING
                RETURNING *
                """
            ),
            {"lead_id": lead_id, "platform": platform, "event_name": event_name,
             "dedupe_key": dedupe_key, "payload": json.dumps(payload or {})},
        )
    ).mappings().first()
    return _row(row, _CONVERSION_JSONB)


async def list_pending_conversion_syncs(
    session: AsyncSession, *, platform: str | None = None, limit: int = 200
) -> list[dict]:
    """Conversions still in 'pending' (the worker's queue to send), oldest first."""
    rows = (
        await session.execute(
            text(
                """
                SELECT * FROM conversion_syncs
                WHERE status = 'pending'
                  AND (CAST(:platform AS text) IS NULL OR platform = :platform)
                ORDER BY created_at ASC LIMIT :limit
                """
            ),
            {"platform": platform, "limit": limit},
        )
    ).mappings().all()
    return [_row(m, _CONVERSION_JSONB) for m in rows]  # type: ignore[misc]


async def mark_conversion_sent(
    session: AsyncSession, *, conversion_id: uuid.UUID
) -> dict | None:
    """pending -> sent. Guarded so a send that already left can't be re-fired; None if not pending."""
    row = (
        await session.execute(
            text(
                """
                UPDATE conversion_syncs
                   SET status = 'sent', sent_at = now(), error = NULL
                 WHERE id = :id AND status = 'pending'
                RETURNING *
                """
            ),
            {"id": conversion_id},
        )
    ).mappings().first()
    return _row(row, _CONVERSION_JSONB)


async def mark_conversion_failed(
    session: AsyncSession, *, conversion_id: uuid.UUID, error: str
) -> dict | None:
    """pending -> failed (records the error). Returns None if the row wasn't pending."""
    row = (
        await session.execute(
            text(
                """
                UPDATE conversion_syncs
                   SET status = 'failed', error = :error
                 WHERE id = :id AND status = 'pending'
                RETURNING *
                """
            ),
            {"id": conversion_id, "error": error},
        )
    ).mappings().first()
    return _row(row, _CONVERSION_JSONB)
