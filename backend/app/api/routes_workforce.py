"""Workforce Optimization agent endpoints."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.agents.workforce import service
from app.agents.workforce.schemas import WorkforceRunResult
from app.api.deps import require_agent_access, require_agent_runner
from app.security import Principal

router = APIRouter(prefix="/v1/agents/workforce", tags=["workforce"])


@router.post("/runs", response_model=WorkforceRunResult, status_code=status.HTTP_201_CREATED)
async def trigger_run(
    horizon_days: int = Query(21, ge=7, le=28, description="Forecast horizon (days)"),
    force: bool = Query(False, description="Bypass idempotency and force a fresh run"),
    principal: Principal = Depends(require_agent_runner("workforce")),
) -> WorkforceRunResult:
    """Run a workforce analysis now and persist it (admin/analyst only)."""
    return await service.run_workforce_analysis(principal, horizon_days=horizon_days, force=force)


@router.get("/runs/latest")
async def latest_run(principal: Principal = Depends(require_agent_access("workforce"))) -> dict:
    result = await service.get_latest_result(principal)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no runs yet")
    return result


@router.get("/runs")
async def list_runs(
    limit: int = Query(20, ge=1, le=100),
    principal: Principal = Depends(require_agent_access("workforce")),
) -> list[dict]:
    return await service.list_recent_runs(principal, limit=limit)


@router.get("/runs/{run_id}")
async def get_run(
    run_id: uuid.UUID, principal: Principal = Depends(require_agent_access("workforce"))
) -> dict:
    result = await service.get_result_by_id(principal, run_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")
    return result
