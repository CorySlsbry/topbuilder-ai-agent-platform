"""Best-effort buyer sync into the Salisbury CRM (a SEPARATE Supabase Postgres, not our app DB).

FAIL-CLOSED by design: no `crm_sync_db_url` -> skip (logged once); no buyer email -> skip; ANY
connection/SQL failure -> log + False. The caller (app/tripwires/service.py) treats the sync as a
side effect that must never lose or delay the order.

Connection: asyncpg.connect(dsn, timeout=10, statement_cache_size=0) — statement_cache_size=0 keeps
this safe behind Supabase's transaction-mode pooler (prepared statements cannot be cached when the
pooler multiplexes clients over backends; same rule as our own db.py).

Schema assumptions (the CRM is external — we cannot introspect it at build time, so every statement
is written defensively):
  * crm_contacts(id, email, first_name, last_name, source, lead_source_type, email_normalized, ...)
    — matched by email_normalized = lower(email) via SELECT-then-INSERT (no reliance on a unique
    constraint we haven't verified).
  * crm_tags(id, name) — we could NOT verify a unique constraint on `name` (would need
    `SELECT ... FROM information_schema.table_constraints/constraint_column_usage WHERE
    table_name='crm_tags'` against the live CRM), so `ON CONFLICT (name)` is NOT safe to assume:
    we SELECT-then-INSERT instead.
  * crm_contact_tags(contact_id, tag_id) — linked via INSERT ... WHERE NOT EXISTS (works with or
    without a unique constraint; ON CONFLICT DO NOTHING with no constraint would still allow dupes).
  * crm_activities(id, contact_id, type, ...) — the exact column list beyond (contact_id, type) is
    unverified, so the activity insert runs in its OWN savepoint with a rich-then-minimal fallback:
    a column mismatch can never break the contact + tag sync.
"""
from __future__ import annotations

import json
import logging

from app.config import Settings

log = logging.getLogger("app.tripwires")

_warned_unconfigured = False  # log the missing-DSN skip once, not per order

ACTIVITY_TYPE = "tripwire_purchase"


# ── pure helpers (oracle-tested) ──────────────────────────────────────────────────────────────────
def split_name(full_name: str | None) -> tuple[str | None, str | None]:
    """Split a display name on the FIRST space -> (first_name, last_name). Total: None/blank in,
    (None, None) out; a single token becomes the first name."""
    if not full_name or not full_name.strip():
        return None, None
    first, _, rest = full_name.strip().partition(" ")
    return first, (rest.strip() or None)


def tag_names(product_key: str) -> list[str]:
    """The CRM tags every tripwire buyer gets: the brand tag + a per-product buyer tag."""
    return ["topbuilderai", f"tripwire-{product_key}-buyer"]


# ── the sync (impure — best-effort, never raises) ─────────────────────────────────────────────────
async def _ensure_tag(conn, name: str):
    """Tag id for `name`, creating the row if missing. SELECT-then-INSERT (see module docstring:
    a unique constraint on crm_tags.name is unverified, so ON CONFLICT (name) is not assumed)."""
    tag_id = await conn.fetchval("SELECT id FROM crm_tags WHERE name = $1 LIMIT 1", name)
    if tag_id is None:
        tag_id = await conn.fetchval("INSERT INTO crm_tags (name) VALUES ($1) RETURNING id", name)
    return tag_id


async def _insert_activity(conn, contact_id, *, product_key: str, amount_cents: int | None) -> None:
    """Log the purchase activity. Its OWN savepoints so an unexpected crm_activities column list
    aborts ONLY this insert, never the already-applied contact + tag work."""
    # crm_activities columns (verified live 2026-07-03): id, contact_id, type, summary (NOT NULL),
    # metadata jsonb, created_at, source_campaign_id.
    summary = f"Tripwire purchase: {product_key}"
    meta = json.dumps(
        {"product_key": product_key, "amount_cents": amount_cents, "source": "stripe"}
    )
    try:
        async with conn.transaction():  # savepoint (we are inside the outer transaction)
            await conn.execute(
                "INSERT INTO crm_activities (contact_id, type, summary, metadata) "
                "VALUES ($1, $2, $3, $4::jsonb)",
                contact_id, ACTIVITY_TYPE, summary, meta,
            )
        return
    except Exception:
        log.warning("crm_sync: rich crm_activities insert failed — retrying minimal columns")
    try:
        async with conn.transaction():
            await conn.execute(
                "INSERT INTO crm_activities (contact_id, type, summary) VALUES ($1, $2, $3)",
                contact_id, ACTIVITY_TYPE, summary,
            )
    except Exception:
        log.exception("crm_sync: crm_activities insert failed (contact+tags still synced)")


async def sync_buyer(
    settings: Settings,
    *,
    email: str | None,
    name: str | None,
    product_key: str,
    amount_cents: int | None = None,
) -> bool:
    """Upsert the buyer as a CRM contact, tag them, and log the purchase activity. Returns True
    only when the contact + tags landed (the caller then stamps tripwire_orders.crm_synced_at).
    NEVER raises."""
    global _warned_unconfigured
    dsn = getattr(settings, "crm_sync_db_url", None)
    if not dsn:
        if not _warned_unconfigured:
            log.info("crm_sync: CRM_SYNC_DB_URL unset — tripwire buyers will not sync to the CRM")
            _warned_unconfigured = True
        return False
    if not email or not email.strip():
        log.warning("crm_sync: no buyer email on the checkout session — skipping CRM sync")
        return False
    email = email.strip()

    import asyncpg  # local import: keeps pure-test imports connection-free

    conn = None
    try:
        conn = await asyncpg.connect(dsn, timeout=10, statement_cache_size=0)
        async with conn.transaction():
            contact_id = await conn.fetchval(
                "SELECT id FROM crm_contacts WHERE email_normalized = lower($1) LIMIT 1", email
            )
            if contact_id is None:
                first_name, last_name = split_name(name)
                # NOTE: crm_contacts.email_normalized is a GENERATED column (verified live 2026-07-03
                # via GeneratedAlwaysError) — it must NOT appear in the INSERT; Postgres derives it.
                contact_id = await conn.fetchval(
                    """
                    INSERT INTO crm_contacts
                      (email, first_name, last_name, source, lead_source_type)
                    VALUES ($1, $2, $3, 'tripwire', 'tripwire')
                    RETURNING id
                    """,
                    email, first_name, last_name,
                )
            for tag in tag_names(product_key):
                tag_id = await _ensure_tag(conn, tag)
                if tag_id is not None:
                    await conn.execute(
                        """
                        INSERT INTO crm_contact_tags (contact_id, tag_id)
                        SELECT $1, $2
                        WHERE NOT EXISTS (
                          SELECT 1 FROM crm_contact_tags WHERE contact_id = $1 AND tag_id = $2
                        )
                        """,
                        contact_id, tag_id,
                    )
            await _insert_activity(
                conn, contact_id, product_key=product_key, amount_cents=amount_cents
            )
        return True
    except Exception:
        log.exception("crm_sync: buyer sync failed (order is unaffected)")
        return False
    finally:
        if conn is not None:
            try:
                await conn.close()
            except Exception:
                log.warning("crm_sync: connection close failed", exc_info=True)
