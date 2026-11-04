"""Routing / Dispatch agent endpoints."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.agents.routing import service
from app.agents.routing.schemas import RoutingRunResult, TriageRunResult
from app.api.deps import require_agent_access, require_agent_runner
from app.security import Principal

router = APIRouter(prefix="/v1/agents/routing", tags=["routing"])


@router.post("/runs", response_model=RoutingRunResult, status_code=status.HTTP_201_CREATED)
async def trigger_run(
    force: bool = Query(False, description="Bypass idempotency and force a fresh run"),
    principal: Principal = Depends(require_agent_runner("routing")),
) -> RoutingRunResult:
    """Build today's drive-time-optimized dispatch plan and persist it (admin/analyst only). Advisory."""
    return await service.run_routing_analysis(principal, force=force)


@router.get("/runs/latest")
async def latest_run(principal: Principal = Depends(require_agent_access("routing"))) -> dict:
    result = await service.get_latest_result(principal)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no runs yet")
    return result


@router.get("/runs")
async def list_runs(
    limit: int = Query(20, ge=1, le=100), principal: Principal = Depends(require_agent_access("routing"))
) -> list[dict]:
    return await service.list_recent_runs(principal, limit=limit)


@router.get("/runs/{run_id}")
async def get_run(run_id: uuid.UUID, principal: Principal = Depends(require_agent_access("routing"))) -> dict:
    result = await service.get_result_by_id(principal, run_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")
    return result


# --- Triage: P1/P2/P3 priority matrix + revenue-ranked tech recommendation + 3-day call board -------
@router.post("/triage", response_model=TriageRunResult, status_code=status.HTTP_201_CREATED)
async def trigger_triage(
    force: bool = Query(False, description="Bypass idempotency and force a fresh triage run"),
    principal: Principal = Depends(require_agent_runner("routing")),
) -> TriageRunResult:
    """Triage the day's jobs (P1/P2/P3), recommend the best skill+revenue+proximity tech, and build the
    3-day call board (admin/analyst only). Advisory — the dispatcher accepts or overrides."""
    return await service.run_triage_analysis(principal, force=force)


@router.get("/triage/latest")
async def latest_triage(principal: Principal = Depends(require_agent_access("routing"))) -> dict:
    result = await service.get_latest_triage(principal)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no triage runs yet")
    return result
