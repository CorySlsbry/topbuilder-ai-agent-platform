"""Event-detection layer endpoints (ADR 0010): the poll + drain crons, the app-owned emit path, and
operator dead-letter visibility.

The two crons are machine-auth (`X-Cron-Key`, no user JWT) and mirror the existing scheduled jobs:
404 when no `cron_secret` is configured, 403 on a bad key. `emit` is the real-time app-owned producer
(field-PWA receipt snap, email-in) and scopes the tenant from the caller's JWT, never the body.
"""
from __future__ import annotations

import hmac
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.deps import require_admin, require_runner
from app.config import get_settings
from app.db import tenant_session
from app.repositories import sync as sync_repo
from app.security import Principal
from app.sync import normalize, service
from app.sync.router import known_entities

router = APIRouter(prefix="/v1/sync", tags=["sync"])


def _check_cron(x_cron_key: str | None) -> None:
    settings = get_settings()
    if not settings.cron_secret:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "cron not configured")
    if not x_cron_key or not hmac.compare_digest(x_cron_key, settings.cron_secret):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "bad cron key")


@router.post("/cron/poll")
async def cron_poll(x_cron_key: str | None = Header(default=None, alias="X-Cron-Key")) -> dict:
    """Detect new ServiceTitan/QuickBooks items (the change-feed backbone) and enqueue them, for every
    tenant. Demo iterates the seeded tenants; prod enumerates via an admin connection."""
    _check_cron(x_cron_key)
    from app.demo import DEMO_TENANTS

    results = [await service.poll_tenant(dt.tenant_id) for dt in DEMO_TENANTS.values()]
    return {"tenants": len(DEMO_TENANTS), "results": results}


@router.post("/cron/drain")
async def cron_drain(
    limit: int = Query(100, ge=1, le=500),
    x_cron_key: str | None = Header(default=None, alias="X-Cron-Key"),
) -> dict:
    """Drain the inbox: route each detected event to its agent and PROPOSE through the gate (advisory
    by default), for every tenant."""
    _check_cron(x_cron_key)
    from app.demo import DEMO_TENANTS

    totals = {"claimed": 0, "proposed": 0, "advisory": 0, "no_route": 0, "failed": 0}
    for dt in DEMO_TENANTS.values():
        result = await service.drain_tenant(dt.tenant_id, limit=limit)
        for key in totals:
            totals[key] += result.get(key, 0)
    return {"tenants": len(DEMO_TENANTS), **totals}


class SyncEmitIn(BaseModel):
    entity: str
    provider_id: str
    verb: str = "created"
    job_ref: str | None = None
    payload: dict = Field(default_factory=dict)


@router.post("/emit", status_code=status.HTTP_202_ACCEPTED)
async def emit_event(body: SyncEmitIn, principal: Principal = Depends(require_runner)) -> dict:
    """App-owned instant detection (field-PWA receipt snap, email-in): enqueue a normalized event
    under the CALLER's tenant (from the JWT, never the body); the drain cron processes it. Runner
    roles only (the same bar as triggering a run) — a read-only viewer can't seed the inbox — and
    the emitting user is stamped into the payload for the audit trail."""
    # Reject unknown entities so a caller can't pollute the inbox with garbage event types. NOTE
    # (Phase 2): per-entity emit authorization (e.g. a field tech may emit `attachment` but not
    # `bill`) is a finer-grained gate to add when emit is wired to the field PWA; today every emitted
    # action is still advisory-by-default and human-gated, and scoped to the caller's own tenant.
    if body.entity not in known_entities():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"unknown entity '{body.entity}'")
    event = normalize.normalize_inapp(
        body.entity,
        {**body.payload, "emitted_by": str(principal.user_id)},
        provider_id=body.provider_id,
        verb=body.verb,
        job_ref=body.job_ref,
    )
    inserted = await service.enqueue_events(principal.tenant_id, [event])
    return {"status": "queued" if inserted else "duplicate_ignored", "natural_key": event.natural_key}


@router.get("/dead-letters")
async def dead_letters(
    limit: int = Query(50, ge=1, le=200), principal: Principal = Depends(require_admin)
) -> list[dict]:
    """Operator view of quarantined poison events for replay/triage."""
    async with tenant_session(principal.tenant_id) as session:
        return await sync_repo.list_dead_letters(session, limit=limit)


@router.post("/dead-letters/{dead_letter_id}/replay", status_code=status.HTTP_202_ACCEPTED)
async def replay_dead_letter(
    dead_letter_id: uuid.UUID, principal: Principal = Depends(require_admin)
) -> dict:
    """Operator replay: re-arm a quarantined event (reset attempts/lease) so the next drain retries it."""
    async with tenant_session(principal.tenant_id) as session:
        ok = await sync_repo.requeue_dead_letter(session, dead_letter_id=dead_letter_id)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "dead-letter not found")
    return {"status": "requeued", "id": str(dead_letter_id)}
