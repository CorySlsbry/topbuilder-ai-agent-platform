"""Ads API (ADR 0009) — operator-only ad accounts / templates / campaigns / metrics + nightly sync.

EVERY interactive route is gated to a PLATFORM OPERATOR (``Depends(require_admin)`` + the
``platform_operator_emails`` allowlist, the ``routes_data_rights`` pattern) and opens the DB with
``db.operator_session()``. Reads are plain operator reads; the ONE write that touches an ad platform —
``POST /v1/ads/campaigns/build`` — does NOT write here: it PROPOSES an ``ads.create_campaign`` action
through the human-approved gate (ADR 0007) and returns the proposed action id for a human to approve +
execute. ``POST /v1/ads/cron/sync`` is the machine-auth nightly job (``X-Cron-Key``, no user JWT).
"""
from __future__ import annotations

import hmac
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel

from app.actions.service import ActionConflict
from app.ads import service as ads_service
from app.api.deps import require_admin
from app.config import get_settings
from app.db import operator_session
from app.repositories import ads as ads_repo
from app.security import Principal

router = APIRouter(prefix="/v1/ads", tags=["ads"])


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


class BuildCampaignIn(BaseModel):
    """Build a campaign from a stored template against a connected ad account (by id or slug)."""

    ad_account_id: uuid.UUID
    template_id: uuid.UUID | None = None
    template_slug: str | None = None


# ── ad accounts ─────────────────────────────────────────────────────────────────────────────────────
@router.get("/accounts")
async def list_ad_accounts(
    platform: str | None = Query(None),
    principal: Principal = Depends(require_admin),
) -> dict:
    _require_platform_operator(principal)
    async with operator_session() as session:
        accounts = await ads_repo.list_ad_accounts(session, platform=platform)
    return {"accounts": accounts}


# ── templates ─────────────────────────────────────────────────────────────────────────────────────
@router.get("/templates")
async def list_templates(principal: Principal = Depends(require_admin)) -> dict:
    _require_platform_operator(principal)
    async with operator_session() as session:
        templates = await ads_repo.list_templates(session)
    return {"templates": templates}


# ── build (propose ads.create_campaign through the action gate) ─────────────────────────────────────
@router.post("/campaigns/build", status_code=status.HTTP_201_CREATED)
async def build_campaign(
    payload: BuildCampaignIn, principal: Principal = Depends(require_admin)
) -> dict:
    """Assemble the plan + PROPOSE an ``ads.create_campaign`` action. Returns the proposed action id.

    No platform write happens here — the proposal is inert until a human approves + executes it through
    ``/v1/actions/{id}/approve`` + ``/execute`` (the campaign is created PAUSED).
    """
    _require_platform_operator(principal)
    if not payload.template_id and not payload.template_slug:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "provide a template_id or template_slug"
        )
    async with operator_session() as session:
        accounts = await ads_repo.list_ad_accounts(session)
        account = next((a for a in accounts if a["id"] == payload.ad_account_id), None)
        if account is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "ad account not found")
        template = await ads_repo.get_template(
            session, slug=payload.template_slug, template_id=payload.template_id
        )
        if template is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "campaign template not found")

    try:
        proposed = await ads_service.plan_and_propose(principal, account=account, template=template)
    except ValueError as exc:  # engine rejected the spec (bad window / platform / budget)
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except ActionConflict as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return proposed


# ── campaigns + metrics ─────────────────────────────────────────────────────────────────────────────
@router.get("/campaigns")
async def list_campaigns(
    status_filter: str | None = Query(None, alias="status"),
    platform: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    principal: Principal = Depends(require_admin),
) -> dict:
    _require_platform_operator(principal)
    async with operator_session() as session:
        campaigns = await ads_repo.list_campaigns(
            session, status=status_filter, platform=platform, limit=limit
        )
    return {"campaigns": campaigns}


@router.get("/campaigns/{campaign_id}/metrics")
async def campaign_metrics(
    campaign_id: uuid.UUID,
    limit: int = Query(90, ge=1, le=365),
    principal: Principal = Depends(require_admin),
) -> dict:
    _require_platform_operator(principal)
    async with operator_session() as session:
        campaign = await ads_repo.get_campaign(session, campaign_id=campaign_id)
        if campaign is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "campaign not found")
        metrics = await ads_repo.list_metrics(session, campaign_id=campaign_id, limit=limit)
    return {"campaign": campaign, "metrics": metrics}


# ── nightly sync (machine-auth, X-Cron-Key — NO user JWT) ───────────────────────────────────────────
@router.post("/cron/sync")
async def cron_sync(x_cron_key: str | None = Header(default=None, alias="X-Cron-Key")) -> dict:
    """Scheduler entrypoint: pull campaign metrics + fire due conversion sends. Shared-secret auth.

    404 when no ``cron_secret`` is configured (the endpoint hides itself); 403 on a bad key. Operator-
    scoped inside (``operator_session``); no tenant loop — the Ads-CRM is a single platform-operator store.
    """
    settings = get_settings()
    if not settings.cron_secret:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "cron not configured")
    if not x_cron_key or not hmac.compare_digest(x_cron_key, settings.cron_secret):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "bad cron key")
    return await ads_service.sync(settings)
