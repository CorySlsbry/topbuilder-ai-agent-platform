"""Inbound webhook receiver (ServiceTitan) + event-queue visibility.

The receiver is unauthenticated by JWT (ServiceTitan calls it) but **signature-verified**. The MAC
binds the path tenant_id + a timestamp, so a valid signature for one tenant can't be replayed at
another tenant's path, and stale captures are rejected. The secret is resolved PER-TENANT (the
credential vault, provider 'webhook'), falling back to the global secret. Duplicate deliveries are
idempotent via the event-queue dedupe index (migration 0017).
"""
from __future__ import annotations

import json
import time
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status

from app.api.deps import get_principal
from app.config import get_settings
from app.db import operator_session, tenant_session
from app.org import access as org_access
from app.repositories import credentials, events
from app.repositories import org as org_repo
from app.repositories import sync as sync_repo
from app.security import Principal
from app.sync import normalize as sync_normalize
from app.sync import service as sync_service
from app.webhooks import verify_qbo_signature, verify_webhook

router = APIRouter(prefix="/v1/webhooks", tags=["webhooks"])


async def _resolve_webhook_secret(tenant_id: uuid.UUID) -> str | None:
    """Per-tenant webhook secret from the vault, else the global default. Best-effort vault read."""
    try:
        async with tenant_session(tenant_id) as session:
            stored = await credentials.get_credential(session, provider="webhook")
        if isinstance(stored, dict):
            value = stored.get("secret") or stored.get("signing_secret")
            if value:
                return str(value)
    except Exception:
        pass
    return get_settings().webhook_signing_secret


@router.post("/servicetitan/{tenant_id}", status_code=status.HTTP_202_ACCEPTED)
async def receive_servicetitan(
    tenant_id: uuid.UUID,
    request: Request,
    x_signature: str | None = Header(default=None),
    x_timestamp: str | None = Header(default=None),
) -> dict:
    secret = await _resolve_webhook_secret(tenant_id)
    body = await request.body()
    ok, reason = verify_webhook(
        tenant_id=str(tenant_id), timestamp=x_timestamp, body=body,
        signature=x_signature, secret=secret or "", now=time.time(),
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"webhook rejected: {reason}")
    try:
        payload = json.loads(body or b"{}")
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {"raw": payload}
    event_type = str(payload.get("eventType") or payload.get("event") or "unknown")
    external_id = str(payload.get("id") or payload.get("eventId") or "") or None
    async with tenant_session(tenant_id) as session:
        inserted = await events.enqueue_event(
            session, source="servicetitan", event_type=event_type, external_id=external_id, payload=payload
        )
    # Real-time roster: a hire/fire employee event auto-updates the org sphere immediately (the bulk
    # /v1/org/sync is the reconcile backstop). Only acted on for fresh events (dedupe gate above).
    roster = None
    action = org_access.classify_employee_event(event_type)
    if action and inserted:
        emp = payload.get("data") or payload.get("employee") or payload
        emp = emp if isinstance(emp, dict) else {}
        ext = str(emp.get("id") or emp.get("employeeId") or external_id or "") or None
        name = str(
            emp.get("name")
            or f"{emp.get('firstName', '')} {emp.get('lastName', '')}".strip()
        )
        title = str(emp.get("title") or emp.get("role") or "")
        dept = emp.get("department") or emp.get("businessUnit")
        roster = await org_repo.apply_employee_change(
            tenant_id,
            external_ref=ext,
            action=action,
            full_name=name,
            title=title,
            department_key=str(dept) if dept else None,
        )
    return {"status": "queued" if inserted else "duplicate_ignored", "roster": roster}


@router.post("/quickbooks", status_code=status.HTTP_202_ACCEPTED)
async def receive_quickbooks(
    request: Request,
    intuit_signature: str | None = Header(default=None, alias="intuit-signature"),
) -> dict:
    """Inbound QuickBooks Online webhook (ADR 0010). Verifies the `intuit-signature` HMAC against the
    Intuit Verifier Token, resolves each notification's tenant from `realmId` (via qbo_connection,
    NEVER a session), and enqueues the changed entities into the same inbox the poll backbone feeds.
    QBO `Attachable` (receipts) is NOT webhook-eligible, so those still arrive only via the CDC poll."""
    settings = get_settings()
    token = settings.qbo_webhook_verifier_token
    if not token:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="quickbooks webhook not configured")
    body = await request.body()
    if not verify_qbo_signature(body, intuit_signature, token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="webhook rejected: invalid signature")
    try:
        payload = json.loads(body or b"{}")
    except json.JSONDecodeError:
        payload = {}
    queued = 0
    skipped_unconnected = 0
    for note in payload.get("eventNotifications") or []:
        realm_id = str(note.get("realmId") or "")
        if not realm_id:
            continue
        async with operator_session() as session:
            tenant_id = await sync_repo.get_tenant_by_realm(session, realm_id=realm_id)
        if tenant_id is None:
            skipped_unconnected += 1  # no connected tenant for this realm -> can't scope; ignore
            continue
        entities = ((note.get("dataChangeEvent") or {}).get("entities")) or []
        events_to_queue = [
            ev for ev in (sync_normalize.normalize_qbo_webhook_entity(e) for e in entities)
            if ev is not None
        ]
        if events_to_queue:
            queued += await sync_service.enqueue_events(tenant_id, events_to_queue)
    return {"status": "queued", "queued": queued, "skipped_unconnected_realms": skipped_unconnected}


@router.get("/events")
async def list_events(
    limit: int = Query(50, ge=1, le=200), principal: Principal = Depends(get_principal)
) -> list[dict]:
    async with tenant_session(principal.tenant_id) as session:
        return await events.list_events(session, limit=limit)
