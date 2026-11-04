"""Seed-on-read demo run history for the executive KPI timeseries — DEMO tenants ONLY (fail closed).

Mirrors app/repositories/org.ensure_seeded (the house seed-on-read pattern): the first sparse read
backfills deterministic history rows, then every later read finds the coverage dense and no-ops.

  * Demo gate: a tenant_id not in app/demo.py DEMO_TENANTS returns immediately — a real customer's
    run history is NEVER touched.
  * Idempotent three ways: the sparsity gate (< 60% day coverage), the (agent, day) existence check
    against real succeeded runs, and deterministic uuid5 run ids + ON CONFLICT DO NOTHING.
  * Best-effort: any failure is logged and swallowed — the endpoint always serves whatever real
    runs exist.
  * RLS-scoped: inserts run inside the tenant's session; the agent_runs.tenant_id column default
    stamps app.current_tenant on every row (the platform-wide convention — see runs.py).

ADR 0003: every seeded figure comes from the PURE deterministic generator in
app/org/demo_history.py — no LLM, no live data, and each payload carries a ``seeded`` marker.
"""
from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime, time, timedelta

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import tenant_session
from app.demo import DEMO_TENANTS, DemoTenant
from app.org import demo_history
from app.repositories import runs as runs_repo

log = structlog.get_logger(__name__)

# Namespace for deterministic seeded-run ids: re-running the seed can only ever hit the same PK.
_RUN_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://topbuilderai.com/demo-run-history")
_SEED_HORIZON_DAYS = 30
_SEED_DURATION_MS = 1200

_INSERT_SEEDED_RUN = text(
    """
    INSERT INTO agent_runs
      (id, agent, status, inputs_hash, horizon_days, created_by,
       started_at, finished_at, duration_ms, result)
    VALUES
      (:id, :agent, 'succeeded', :inputs_hash, :horizon_days, :created_by,
       :started_at, :finished_at, :duration_ms, CAST(:result AS jsonb))
    ON CONFLICT (id) DO NOTHING
    """
)


def _demo_tenant(tenant_id: uuid.UUID) -> DemoTenant | None:
    return next((t for t in DEMO_TENANTS.values() if t.tenant_id == tenant_id), None)


def seeded_run_id(tenant_slug: str, agent: str, day: date) -> uuid.UUID:
    """Deterministic id for the seeded (tenant, agent, day) row — the ON CONFLICT dedupe key."""
    return uuid.uuid5(_RUN_NAMESPACE, f"{tenant_slug}:{agent}:{day.isoformat()}")


async def _insert_seeded_run(
    session: AsyncSession,
    *,
    run_id: uuid.UUID,
    agent: str,
    day: date,
    created_by: uuid.UUID,
    result: dict,
) -> None:
    started = datetime.combine(day, time(12, 0), tzinfo=UTC)  # mid-day UTC, per the seed contract
    await session.execute(
        _INSERT_SEEDED_RUN,
        {
            "id": run_id,
            "agent": agent,
            "inputs_hash": f"demo-history:{agent}:{day.isoformat()}",
            "horizon_days": _SEED_HORIZON_DAYS,
            "created_by": created_by,
            "started_at": started,
            "finished_at": started,
            "duration_ms": _SEED_DURATION_MS,
            "result": json.dumps(result),
        },
    )


async def ensure_demo_run_history(tenant_id: uuid.UUID, *, start: date, end: date) -> int:
    """Backfill deterministic run history over [start, end] for a sparse DEMO tenant.

    Returns the number of rows planned (0 for non-demo tenants, dense windows, or on failure).
    Never raises — a seeding failure must never break the timeseries read.
    """
    tenant = _demo_tenant(tenant_id)
    if tenant is None:
        return 0  # non-demo tenants are NEVER seeded (fail closed)
    end = min(end, date.today())  # history only — never fabricate future days
    # Bound the SEED window to the horizon regardless of the caller's axis window: a 366-day
    # timeseries request must never trigger ~2,200 sequential inserts in the foreground GET.
    start = max(start, end - timedelta(days=_SEED_HORIZON_DAYS))
    if start > end:
        return 0
    try:
        async with tenant_session(tenant_id) as session:
            existing = await runs_repo.list_succeeded_run_days_by_agent(
                session, start=start, end=end
            )
            plan = demo_history.plan_seed_runs(tenant.slug, existing, start, end)
            for agent, day, result in plan:
                await _insert_seeded_run(
                    session,
                    run_id=seeded_run_id(tenant.slug, agent, day),
                    agent=agent,
                    day=day,
                    created_by=tenant.admin_user_id,
                    result=result,
                )
            return len(plan)
    except Exception:
        log.warning("demo_run_history.seed_failed", tenant=tenant.slug, exc_info=True)
        return 0
