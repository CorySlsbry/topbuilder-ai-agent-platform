"""Transparent SQL migration runner.

Applies migrations/*.sql in lexical order, exactly once each, as the admin (superuser)
connection (`MIGRATION_DATABASE_URL`). Tracks applied files in `schema_migrations`.

Usage (from backend/):  python scripts/migrate.py
"""
from __future__ import annotations

import asyncio
import hashlib
import pathlib
import sys

# Make `app` importable regardless of how this script is invoked.
BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import asyncpg  # noqa: E402

from app.config import get_settings  # noqa: E402

MIGRATIONS_DIR = BACKEND_DIR / "migrations"


def _checksum(sql: str) -> str:
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()[:16]


async def main() -> int:
    settings = get_settings()
    conn = await asyncpg.connect(settings.migration_database_url)
    try:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
              filename   text PRIMARY KEY,
              checksum   text NOT NULL,
              applied_at timestamptz NOT NULL DEFAULT now()
            );
            """
        )
        applied = {
            row["filename"]: row["checksum"]
            for row in await conn.fetch("SELECT filename, checksum FROM schema_migrations")
        }

        files = sorted(MIGRATIONS_DIR.glob("*.sql"))
        if not files:
            print("no migration files found")
            return 0

        for path in files:
            sql = path.read_text(encoding="utf-8")
            checksum = _checksum(sql)
            if path.name in applied:
                if applied[path.name] != checksum:
                    print(
                        f"!! {path.name}: applied checksum {applied[path.name]} != current "
                        f"{checksum}; not reapplying (create a new migration instead)"
                    )
                else:
                    print(f"== {path.name} (already applied)")
                continue

            print(f">> applying {path.name} ...")
            async with conn.transaction():
                await conn.execute(sql)  # simple-protocol: supports multi-statement files
                await conn.execute(
                    "INSERT INTO schema_migrations (filename, checksum) VALUES ($1, $2)",
                    path.name,
                    checksum,
                )
            print("   ok")

        print("migrations complete")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
