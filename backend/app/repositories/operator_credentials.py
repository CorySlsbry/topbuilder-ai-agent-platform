"""Operator credential vault (ad-platform OAuth tokens). Operator-session-scoped → RLS (ADR 0009).

These are PLATFORM-OPERATOR / GTM tokens (Meta, Google Ads), NOT tenant/customer credentials — they
live in `operator_credentials` (0023), reachable only under `db.operator_session()` (app.operator='on').
Secrets are AES-256-GCM encrypted at rest with the SAME cipher as the tenant vault (app/crypto.py): the
caller passes a plaintext `secret` dict, we `json.dumps` + `encrypt` it; only the encrypted blob touches
the DB. The returned id is what `ad_accounts.vault_credential_id` references. `list_credentials` returns
metadata ONLY — it never decrypts or returns a secret.
"""
from __future__ import annotations

import json
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.crypto import get_cipher


async def store_credential(
    session: AsyncSession,
    *,
    provider: str,
    secret: dict,
    metadata: dict | None = None,
    external_ref: str | None = None,
) -> uuid.UUID:
    """Encrypt + UPSERT an operator credential, returning its id (-> ad_accounts.vault_credential_id).

    Idempotent on (provider, external_ref): a re-connect of the same ad account rotates the secret in
    place rather than duplicating the row. Only the AES-256-GCM ciphertext is stored; the plaintext
    `secret` dict never reaches the database or the logs.
    """
    ciphertext = get_cipher().encrypt(json.dumps(secret))
    row = (
        await session.execute(
            text(
                """
                INSERT INTO operator_credentials
                  (provider, external_ref, secret_ciphertext, metadata)
                VALUES (:provider, :ext, :ct, CAST(:md AS jsonb))
                ON CONFLICT (provider, external_ref)
                DO UPDATE SET secret_ciphertext = EXCLUDED.secret_ciphertext,
                              metadata = EXCLUDED.metadata,
                              updated_at = now()
                RETURNING id
                """
            ),
            {
                "provider": provider,
                "ext": external_ref,
                "ct": ciphertext,
                "md": json.dumps(metadata or {}),
            },
        )
    ).first()
    return row[0]  # type: ignore[index]


async def get_credential(
    session: AsyncSession,
    *,
    credential_id: uuid.UUID | None = None,
    provider: str | None = None,
) -> dict | None:
    """Decrypt + return the secret dict for one credential, looked up by id OR provider.

    By id (the `ad_accounts.vault_credential_id` path) is exact; by provider returns the most recently
    updated credential for that platform. Returns None when nothing matches.
    """
    if credential_id is not None:
        row = (
            await session.execute(
                text("SELECT secret_ciphertext FROM operator_credentials WHERE id = :id"),
                {"id": credential_id},
            )
        ).first()
    elif provider is not None:
        row = (
            await session.execute(
                text(
                    """
                    SELECT secret_ciphertext FROM operator_credentials
                    WHERE provider = :p
                    ORDER BY updated_at DESC LIMIT 1
                    """
                ),
                {"p": provider},
            )
        ).first()
    else:
        raise ValueError("get_credential requires credential_id or provider")
    if not row:
        return None
    return json.loads(get_cipher().decrypt(row[0]))


async def list_credentials(session: AsyncSession, *, provider: str | None = None) -> list[dict]:
    """Credential metadata ONLY (never the secret) — id/provider/external_ref/metadata/timestamps."""
    rows = (
        await session.execute(
            text(
                """
                SELECT id, provider, external_ref, metadata, created_at, updated_at
                FROM operator_credentials
                WHERE (CAST(:p AS text) IS NULL OR provider = :p)
                ORDER BY provider, updated_at DESC
                """
            ),
            {"p": provider},
        )
    ).mappings().all()
    return [dict(m) for m in rows]
