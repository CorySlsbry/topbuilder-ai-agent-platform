"""Re-encrypt every stored credential under the **current primary** key (key rotation sweep).

Run this AFTER rotating ``CREDENTIAL_ENCRYPTION_KEY`` to a new value and moving the previous value
into ``CREDENTIAL_ENCRYPTION_KEY_OLD`` (so the old ciphertext still decrypts). Every encrypted secret
is decrypted (primary, any retired key, or the legacy Fernet path) and re-encrypted under the primary
AES-256-GCM key via :func:`app.crypto.rotate_ciphertext`. Once the sweep is clean you can drop the
old key from ``CREDENTIAL_ENCRYPTION_KEY_OLD``.

Idempotent: re-encrypting already-primary ciphertext just re-nonces it, so re-running is safe. The
sweep is RLS-scoped — it iterates tenants and re-encrypts each tenant's rows under its own
``app.current_tenant``, exactly like a normal request (no superuser bypass).

Targets:
  * ``tenant_credentials.secret_ciphertext`` (the ServiceTitan / QuickBooks / provider vault)
  * ``servicetitan_connections`` encrypted columns, IF that table carries any (schema-tolerant: the
    script discovers ``*_ciphertext`` / ``*_encrypted`` text columns and skips the table otherwise).

Usage (from backend/, inside the api container so asyncpg + the app are importable):
    python scripts/rotate_credentials.py                       # sweep the demo tenants
    python scripts/rotate_credentials.py --tenant <uuid> ...   # sweep explicit tenant ids
    python scripts/rotate_credentials.py --dry-run             # report counts, write nothing

See docs/CREDENTIAL_ROTATION.md for the full rotation + compromise-response runbook.
"""
from __future__ import annotations

import argparse
import asyncio
import pathlib
import sys
import uuid

# Make `app` importable regardless of how this script is invoked.
BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.crypto import rotate_ciphertext  # noqa: E402
from app.db import tenant_session  # noqa: E402
from app.demo import DEMO_TENANTS  # noqa: E402

# (table, ciphertext column). tenant_credentials always exists; servicetitan_connections columns are
# discovered at runtime so the sweep tolerates a schema that has not added encrypted columns there.
_VAULT_TABLE = "tenant_credentials"
_VAULT_COLUMN = "secret_ciphertext"
_CONNECTIONS_TABLE = "servicetitan_connections"


async def _encrypted_text_columns(session: AsyncSession, table: str) -> list[str]:
    """Discover text columns that look like ciphertext (``*_ciphertext`` / ``*_encrypted``).

    Lets the sweep cover ``servicetitan_connections`` if it ever stores encrypted tokens, without
    hardcoding a column that may not exist yet (the current schema has none).
    """
    rows = (
        await session.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = :t
                  AND data_type IN ('text', 'character varying')
                  AND (column_name LIKE '%ciphertext' OR column_name LIKE '%encrypted')
                ORDER BY column_name
                """
            ),
            {"t": table},
        )
    ).scalars().all()
    return list(rows)


async def _rotate_column(
    session: AsyncSession, *, table: str, column: str, dry_run: bool
) -> int:
    """Re-encrypt every non-null value of ``table.column`` for the session's tenant. Returns the count."""
    rows = (
        await session.execute(
            text(f"SELECT id, {column} AS ct FROM {table} WHERE {column} IS NOT NULL")  # noqa: S608
        )
    ).mappings().all()
    rotated = 0
    for row in rows:
        new_ct = rotate_ciphertext(row["ct"])
        if not dry_run:
            await session.execute(
                text(f"UPDATE {table} SET {column} = :ct WHERE id = :id"),  # noqa: S608
                {"ct": new_ct, "id": row["id"]},
            )
        rotated += 1
    return rotated


async def _rotate_tenant(tenant_id: uuid.UUID, *, dry_run: bool) -> int:
    """Sweep one tenant's vault (and any encrypted connection columns) under its RLS scope."""
    total = 0
    async with tenant_session(tenant_id) as session:
        total += await _rotate_column(
            session, table=_VAULT_TABLE, column=_VAULT_COLUMN, dry_run=dry_run
        )
        for column in await _encrypted_text_columns(session, _CONNECTIONS_TABLE):
            total += await _rotate_column(
                session, table=_CONNECTIONS_TABLE, column=column, dry_run=dry_run
            )
    return total


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Re-encrypt stored credentials under the new key.")
    parser.add_argument(
        "--tenant",
        action="append",
        default=[],
        metavar="UUID",
        help="Tenant id to sweep (repeatable). Default: the demo tenants.",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Report counts without writing any changes."
    )
    return parser.parse_args(argv)


def _tenants(args: argparse.Namespace) -> list[uuid.UUID]:
    if args.tenant:
        return [uuid.UUID(t) for t in args.tenant]
    return [t.tenant_id for t in DEMO_TENANTS.values()]


async def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    tenants = _tenants(args)
    mode = "DRY-RUN (no writes)" if args.dry_run else "rotating"
    print(f"Credential rotation [{mode}] across {len(tenants)} tenant(s)...")

    grand_total = 0
    for tenant_id in tenants:
        count = await _rotate_tenant(tenant_id, dry_run=args.dry_run)
        grand_total += count
        print(f"  tenant {tenant_id}: {count} secret(s) re-encrypted")

    verb = "would re-encrypt" if args.dry_run else "re-encrypted"
    print(f"\nDone: {verb} {grand_total} secret(s) under the current primary key.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
