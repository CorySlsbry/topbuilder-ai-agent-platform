"""SEO/GEO Marketing agent endpoints (weekly competitor/GEO/content review)."""
from __future__ import annotations

import hmac
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from app.agents.seo import service
from app.agents.seo.schemas import SeoRunResult
from app.api.deps import require_admin
from app.config import get_settings
from app.security import Principal

# OPERATOR-ONLY (super-admin layer): the SEO/GEO agent is an internal platform-operator tool, not
# part of the customer-facing product. Every endpoint requires the admin role.
router = APIRouter(prefix="/v1/agents/seo", tags=["seo"])


@router.post("/runs", response_model=SeoRunResult, status_code=status.HTTP_201_CREATED)
async def trigger_run(
    force: bool = Query(False, description="Bypass idempotency and force a fresh run"),
    principal: Principal = Depends(require_admin),
) -> SeoRunResult:
    """Run the weekly SEO/GEO review now and persist it (admin/analyst only)."""
    return await service.run_seo_analysis(principal, force=force)


@router.get("/runs/latest")
async def latest_run(principal: Principal = Depends(require_admin)) -> dict:
    result = await service.get_latest_result(principal)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no runs yet")
    return result


@router.get("/runs")
async def list_runs(
    limit: int = Query(20, ge=1, le=100), principal: Principal = Depends(require_admin)
) -> list[dict]:
    return await service.list_recent_runs(principal, limit=limit)


@router.get("/runs/{run_id}")
async def get_run(run_id: uuid.UUID, principal: Principal = Depends(require_admin)) -> dict:
    result = await service.get_result_by_id(principal, run_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")
    return result


@router.post("/cron/weekly")
async def cron_weekly(x_cron_key: str | None = Header(default=None, alias="X-Cron-Key")) -> dict:
    """Scheduler entrypoint: run the weekly SEO/GEO review for every tenant. Machine-auth via a
    shared secret header (not a user JWT), so a scheduled job needs no expiring token. 404 when
    not configured.

    Demo: iterates the seeded demo tenants. In production this enumerates tenants via an admin
    connection (the `tenants` table is RLS-protected from `app_user`)."""
    settings = get_settings()
    if not settings.cron_secret:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "cron not configured")
    if not x_cron_key or not hmac.compare_digest(x_cron_key, settings.cron_secret):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "bad cron key")

    from app.demo import DEMO_TENANTS

    ran = 0
    failed: list[str] = []
    for dt in DEMO_TENANTS.values():
        principal = Principal(
            tenant_id=dt.tenant_id, user_id=dt.admin_user_id, email=dt.admin_email, role="admin"
        )
        try:
            await service.run_seo_analysis(principal)
            ran += 1
        except Exception:
            failed.append(dt.slug)
    return {"ran": ran, "tenants": len(DEMO_TENANTS), "failed": failed}
