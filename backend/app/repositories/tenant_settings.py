"""tenant_settings — per-tenant configuration (fsm_provider, booking_voice). Tenant-scoped session,
RLS-isolated.

`get_fsm_provider` is the read every agent run performs (best-effort; default ServiceTitan), so it
must never raise into a run: callers wrap it, and a missing row is simply the default.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.providers import registry
from app.voice import voices


async def get_fsm_provider(session: AsyncSession) -> str:
    row = (await session.execute(text("SELECT fsm_provider FROM tenant_settings"))).first()
    slug = row[0] if row else registry.DEFAULT_PROVIDER
    return slug if registry.is_valid(slug) else registry.DEFAULT_PROVIDER


async def set_fsm_provider(session: AsyncSession, *, slug: str) -> str:
    await session.execute(
        text(
            "INSERT INTO tenant_settings (fsm_provider) VALUES (:p) "
            "ON CONFLICT (tenant_id) DO UPDATE SET fsm_provider = EXCLUDED.fsm_provider, updated_at = now()"
        ),
        {"p": slug},
    )
    return slug


async def get_booking_voice(session: AsyncSession) -> str:
    row = (await session.execute(text("SELECT booking_voice FROM tenant_settings"))).first()
    key = row[0] if row else voices.DEFAULT_VOICE
    return key if voices.is_valid(key) else voices.DEFAULT_VOICE


async def set_booking_voice(session: AsyncSession, *, key: str) -> str:
    await session.execute(
        text(
            "INSERT INTO tenant_settings (booking_voice) VALUES (:v) "
            "ON CONFLICT (tenant_id) DO UPDATE SET booking_voice = EXCLUDED.booking_voice, updated_at = now()"
        ),
        {"v": key},
    )
    return key
