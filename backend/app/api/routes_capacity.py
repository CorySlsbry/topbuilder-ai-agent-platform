"""Rolling-capacity agent endpoints (part of the Workforce agent).

``POST /v1/agents/workforce/capacity`` runs the deterministic rolling-capacity engine and persists it as
an advisory run (admin/analyst with Workforce access). From each technician's ACTUAL on-site hours
(clock-in at dispatch -> clock-out at completion) it maintains a recency-weighted, credibility-blended
moving-target estimate per (technician, job type) — surfacing who is genuinely faster or slower than the
job-type baseline — then projects the upcoming week from those learned durations to flag overtime
*before* it is worked and name same-trade technicians with slack who could absorb the overflow.

Advisory only: nothing is written back to ServiceTitan here. A staffing/redistribution action would go
through the human-approved action gate (ADR 0007).
"""
from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.agents.workforce import capacity_service
from app.agents.workforce.capacity_schemas import CapacityRunResult
from app.api.deps import require_agent_access, require_agent_runner
from app.security import Principal

router = APIRouter(prefix="/v1/agents/workforce/capacity", tags=["workforce"])


@router.post("", response_model=CapacityRunResult, status_code=status.HTTP_201_CREATED)
async def trigger_run(
    as_of: date | None = Query(None, description="Analysis date (defaults to today)"),
    force: bool = Query(False, description="Bypass idempotency and force a fresh run"),
    principal: Principal = Depends(require_agent_runner("workforce")),
) -> CapacityRunResult:
    """Compute the rolling-capacity analysis and persist it (admin/analyst only). Advisory — nothing is
    written back to ServiceTitan."""
    return await capacity_service.run_capacity_analysis(principal, as_of=as_of, force=force)


@router.get("/latest")
async def latest_run(principal: Principal = Depends(require_agent_access("workforce"))) -> dict:
    result = await capacity_service.get_latest_result(principal)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no capacity runs yet")
    return result


@router.get("/runs/{run_id}")
async def get_run(
    run_id: uuid.UUID, principal: Principal = Depends(require_agent_access("workforce"))
) -> dict:
    result = await capacity_service.get_result_by_id(principal, run_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="capacity run not found")
    return result
