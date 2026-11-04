"""Inventory & Supply Chain agent endpoints."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.agents.inventory import service
from app.agents.inventory.schemas import ConsumableProrationResult, InventoryRunResult
from app.api.deps import require_agent_access, require_agent_runner
from app.security import Principal

router = APIRouter(prefix="/v1/agents/inventory", tags=["inventory"])


@router.post("/runs", response_model=InventoryRunResult, status_code=status.HTTP_201_CREATED)
async def trigger_run(
    force: bool = Query(False, description="Bypass idempotency and force a fresh run"),
    principal: Principal = Depends(require_agent_runner("inventory")),
) -> InventoryRunResult:
    """Run an inventory analysis now and persist it (admin/analyst only)."""
    return await service.run_inventory_analysis(principal, force=force)


@router.post(
    "/proration/runs",
    response_model=ConsumableProrationResult,
    status_code=status.HTTP_201_CREATED,
)
async def trigger_proration_run(
    force: bool = Query(False, description="Bypass idempotency and force a fresh run"),
    principal: Principal = Depends(require_agent_runner("inventory")),
) -> ConsumableProrationResult:
    """Prorate partially-consumed consumable lots (spools, copper coils) across the jobs they served,
    instead of dumping the whole lot cost on the single replenish job (advisory; admin/analyst only)."""
    return await service.run_consumable_proration(principal, force=force)


@router.get("/proration/runs/latest")
async def latest_proration_run(
    principal: Principal = Depends(require_agent_access("inventory")),
) -> dict:
    result = await service.get_latest_proration_result(principal)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no proration runs yet")
    return result


@router.get("/runs/latest")
async def latest_run(principal: Principal = Depends(require_agent_access("inventory"))) -> dict:
    result = await service.get_latest_result(principal)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no runs yet")
    return result


@router.get("/runs")
async def list_runs(
    limit: int = Query(20, ge=1, le=100), principal: Principal = Depends(require_agent_access("inventory"))
) -> list[dict]:
    return await service.list_recent_runs(principal, limit=limit)


@router.get("/runs/{run_id}")
async def get_run(run_id: uuid.UUID, principal: Principal = Depends(require_agent_access("inventory"))) -> dict:
    result = await service.get_result_by_id(principal, run_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")
    return result
