"""Seed the trade-show geofence campaign templates into ``ad_campaign_templates`` (ADR 0009).

Operator-scoped, idempotent. Opens a ``db.operator_session()`` (sets ``app.operator='on'`` so the
operator-only RLS policy in migration 0023 grants access) and UPSERTs every template from
``app.ads.seed`` on its ``slug`` — re-running refreshes the rows in place rather than duplicating them.

Run from ``backend/`` (so ``app`` imports), against a DB that has migration 0023 applied:

    python scripts/seed_ads_templates.py

Exit 0 = seeded; prints one line per template (slug · daily $ · lifetime cap $ · # geo pins).
"""
from __future__ import annotations

import asyncio

from app.ads import seed
from app.db import operator_session


async def _run() -> int:
    async with operator_session() as session:
        rows = await seed.seed_templates(session)
    for row in rows:
        budget = row.get("budget_spec") or {}
        geo = row.get("geo_spec") or {}
        daily = (budget.get("daily_cents", 0)) / 100
        cap = (budget.get("lifetime_cap_cents", 0)) / 100
        pins = len(geo.get("custom_locations", []))
        print(f"  ✓ {row['slug']:<32} ${daily:>5.2f}/day · cap ${cap:>6.2f} · {pins} geo pins")
    print(f"Seeded {len(rows)} trade-show templates.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run()))
