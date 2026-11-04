"""24/7 Booking agent endpoints."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.agents.booking import service
from app.agents.booking.schemas import BookingRunResult
from app.api.deps import require_agent_access, require_agent_runner
from app.security import Principal

router = APIRouter(prefix="/v1/agents/booking", tags=["booking"])


@router.post("/runs", response_model=BookingRunResult, status_code=status.HTTP_201_CREATED)
async def trigger_run(
    force: bool = Query(False, description="Bypass idempotency and force a fresh run"),
    principal: Principal = Depends(require_agent_runner("booking")),
) -> BookingRunResult:
    """Qualify, slot, and value the latest inbound-intake batch, then persist it (admin/analyst only).

    Bookings are PROPOSED only — never written back to ServiceTitan (ADR 0006).
    """
    return await service.run_booking_analysis(principal, force=force)


@router.get("/runs/latest")
async def latest_run(principal: Principal = Depends(require_agent_access("booking"))) -> dict:
    result = await service.get_latest_result(principal)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no runs yet")
    return result


@router.get("/runs")
async def list_runs(
    limit: int = Query(20, ge=1, le=100), principal: Principal = Depends(require_agent_access("booking"))
) -> list[dict]:
    return await service.list_recent_runs(principal, limit=limit)


@router.get("/runs/{run_id}")
async def get_run(run_id: uuid.UUID, principal: Principal = Depends(require_agent_access("booking"))) -> dict:
    result = await service.get_result_by_id(principal, run_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")
    return result
