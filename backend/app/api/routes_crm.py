"""CRM API (ADR 0009) — operator-only leads / contacts / activities pipeline.

These are Top Builder AI's OWN go-to-market leads (NOT tenant/customer data). EVERY route is gated to a
PLATFORM OPERATOR: ``Depends(require_admin)`` (admin role + verified 2FA / aal2) PLUS the verified email
on ``settings.platform_operator_emails`` — the same two-line pattern as ``routes_data_rights.py``. The DB
is opened with ``db.operator_session()`` (``app.operator='on'``), so the operator-only RLS in migration
0023 is the defense-in-depth layer under the app gate.

The one un-gated route is ``POST /v1/crm/leads/ingest`` — a public lead webhook (an ad-platform / landing
form posts a lead). It carries NO user JWT; instead it is HMAC-signed (``webhook_signing_secret``), MAC-
bound to a fixed operator scope + a timestamp (replay-protected), exactly like the ServiceTitan webhook.
"""
from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from app.api.deps import require_admin
from app.config import get_settings
from app.db import operator_session
from app.repositories import crm
from app.security import Principal
from app.webhooks import verify_webhook

router = APIRouter(prefix="/v1/crm", tags=["crm"])

# The webhook MAC is bound to this fixed scope (the operator CRM has no tenant); it sits in the same
# position as the tenant_id in the ServiceTitan webhook so a capture can't be replayed at another path.
_WEBHOOK_SCOPE = "operator-crm"

_VALID_STAGES = {"new", "contacted", "booked", "demoed", "won", "lost"}


def _is_platform_operator(principal: Principal) -> bool:
    """The caller's verified email is on the platform-operator allowlist (closed by default)."""
    allow = get_settings().platform_operator_email_set
    return bool(principal.email) and principal.email.strip().lower() in allow


def _require_platform_operator(principal: Principal) -> None:
    if not _is_platform_operator(principal):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "the Ads-CRM is a platform-operator surface — your account is not an operator",
        )


# ── request models ────────────────────────────────────────────────────────────────────────────────
class ContactIn(BaseModel):
    email: str | None = None
    phone: str | None = None
    full_name: str | None = None
    company: str | None = None
    title: str | None = None
    meta: dict = Field(default_factory=dict)


class LeadIn(BaseModel):
    contact_id: uuid.UUID | None = None
    stage: str = "new"
    source: str = "manual"
    value_cents: int = 0
    utm: dict = Field(default_factory=dict)
    ad_ref: dict = Field(default_factory=dict)
    owner: str | None = None


class StageIn(BaseModel):
    stage: str
    lost_reason: str | None = None


class ActivityIn(BaseModel):
    kind: str = "note"
    body: str | None = None
    detail: dict = Field(default_factory=dict)


class LeadIngestIn(BaseModel):
    """The lead shape a landing form / ad-platform webhook posts (PII allowed — operator data store)."""

    email: str | None = None
    phone: str | None = None
    full_name: str | None = None
    company: str | None = None
    title: str | None = None
    source: str = "landing"
    value_cents: int = 0
    utm: dict = Field(default_factory=dict)
    ad_ref: dict = Field(default_factory=dict)
    owner: str | None = None
    note: str | None = None


# ── contacts ──────────────────────────────────────────────────────────────────────────────────────
@router.get("/contacts")
async def list_or_get_contacts(
    principal: Principal = Depends(require_admin),
) -> dict:
    _require_platform_operator(principal)
    # No list-all in the repo (leads are the index); expose the create surface + dedupe via POST.
    return {"contacts": []}


@router.post("/contacts", status_code=status.HTTP_201_CREATED)
async def create_contact(
    payload: ContactIn, principal: Principal = Depends(require_admin)
) -> dict:
    _require_platform_operator(principal)
    async with operator_session() as session:
        contact = await crm.upsert_contact(
            session, email=payload.email, phone=payload.phone, full_name=payload.full_name,
            company=payload.company, title=payload.title, meta=payload.meta,
        )
    return {"contact": contact}


# ── leads ─────────────────────────────────────────────────────────────────────────────────────────
@router.get("/leads")
async def list_leads(
    stage: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    principal: Principal = Depends(require_admin),
) -> dict:
    _require_platform_operator(principal)
    async with operator_session() as session:
        leads = await crm.list_leads(session, stage=stage, limit=limit)
    return {"leads": leads}


@router.post("/leads", status_code=status.HTTP_201_CREATED)
async def create_lead(payload: LeadIn, principal: Principal = Depends(require_admin)) -> dict:
    _require_platform_operator(principal)
    if payload.stage not in _VALID_STAGES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"invalid stage '{payload.stage}'")
    async with operator_session() as session:
        lead = await crm.create_lead(
            session, contact_id=payload.contact_id, stage=payload.stage, source=payload.source,
            value_cents=payload.value_cents, utm=payload.utm, ad_ref=payload.ad_ref, owner=payload.owner,
        )
    return {"lead": lead}


@router.get("/leads/{lead_id}")
async def get_lead(lead_id: uuid.UUID, principal: Principal = Depends(require_admin)) -> dict:
    _require_platform_operator(principal)
    async with operator_session() as session:
        lead = await crm.get_lead(session, lead_id=lead_id)
        if lead is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "lead not found")
        activities = await crm.list_activities(session, lead_id=lead_id)
    return {"lead": lead, "activities": activities}


@router.patch("/leads/{lead_id}/stage")
async def set_lead_stage(
    lead_id: uuid.UUID, payload: StageIn, principal: Principal = Depends(require_admin)
) -> dict:
    _require_platform_operator(principal)
    if payload.stage not in _VALID_STAGES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"invalid stage '{payload.stage}'")
    async with operator_session() as session:
        lead = await crm.set_stage(
            session, lead_id=lead_id, stage=payload.stage,
            actor=principal.email or str(principal.user_id), lost_reason=payload.lost_reason,
        )
        if lead is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "lead not found")
    return {"lead": lead}


@router.post("/leads/{lead_id}/activities", status_code=status.HTTP_201_CREATED)
async def add_activity(
    lead_id: uuid.UUID, payload: ActivityIn, principal: Principal = Depends(require_admin)
) -> dict:
    _require_platform_operator(principal)
    async with operator_session() as session:
        if await crm.get_lead(session, lead_id=lead_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "lead not found")
        activity = await crm.add_activity(
            session, lead_id=lead_id, kind=payload.kind, body=payload.body, detail=payload.detail,
            actor=principal.email or str(principal.user_id),
        )
    return {"activity": activity}


# ── public lead ingest (HMAC-signed webhook — NO user JWT) ───────────────────────────────────────────
@router.post("/leads/ingest", status_code=status.HTTP_202_ACCEPTED)
async def ingest_lead(
    request: Request,
    payload: LeadIngestIn,
    x_signature: str | None = Header(default=None),
    x_timestamp: str | None = Header(default=None),
) -> dict:
    """Capture a lead from a landing form / ad-platform webhook. HMAC-signed (no user JWT).

    The MAC binds a fixed operator scope + a timestamp over the raw body, replay-protected — the same
    construction as the ServiceTitan webhook. 404 when no signing secret is configured (the endpoint
    hides itself); 401 on a bad/stale/missing signature.
    """
    secret = get_settings().webhook_signing_secret
    if not secret:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "lead ingest not configured")
    body = await request.body()
    ok, reason = verify_webhook(
        tenant_id=_WEBHOOK_SCOPE, timestamp=x_timestamp, body=body,
        signature=x_signature, secret=secret, now=time.time(),
    )
    if not ok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"lead ingest rejected: {reason}")
    async with operator_session() as session:
        result = await crm.ingest_lead(
            session, email=payload.email, phone=payload.phone, full_name=payload.full_name,
            company=payload.company, title=payload.title, source=payload.source,
            value_cents=payload.value_cents, utm=payload.utm, ad_ref=payload.ad_ref,
            owner=payload.owner, activity_kind="system",
            activity_body=payload.note or f"Lead captured from {payload.source}",
        )
    return {"status": "captured", "lead_id": str(result["lead"]["id"])}
