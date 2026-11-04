"""Encrypted credential vault (per tenant, RLS-scoped). Secrets are Fernet-encrypted at rest."""
from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.crypto import get_cipher


async def store_credential(
    session: AsyncSession, *, provider: str, secret: dict, metadata: dict | None = None
) -> None:
    ciphertext = get_cipher().encrypt(json.dumps(secret))
    await session.execute(
        text(
            """
            INSERT INTO tenant_credentials (provider, secret_ciphertext, metadata)
            VALUES (:provider, :ct, CAST(:md AS jsonb))
            ON CONFLICT (tenant_id, provider)
            DO UPDATE SET secret_ciphertext = EXCLUDED.secret_ciphertext,
                          metadata = EXCLUDED.metadata,
                          updated_at = now()
            """
        ),
        {"provider": provider, "ct": ciphertext, "md": json.dumps(metadata or {})},
    )


async def get_credential(session: AsyncSession, *, provider: str) -> dict | None:
    row = (
        await session.execute(
            text("SELECT secret_ciphertext FROM tenant_credentials WHERE provider = :p"),
            {"p": provider},
        )
    ).first()
    if not row:
        return None
    return json.loads(get_cipher().decrypt(row[0]))


async def list_providers(session: AsyncSession) -> list[dict]:
    """Provider metadata only — never returns secrets."""
    rows = (
        await session.execute(
            text("SELECT provider, metadata, updated_at FROM tenant_credentials ORDER BY provider")
        )
    ).mappings().all()
    return [dict(m) for m in rows]
