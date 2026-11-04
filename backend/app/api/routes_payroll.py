"""Payroll agent endpoints (part of the Workforce agent).

``POST /v1/agents/workforce/payroll`` runs the deterministic payroll engine for a pay period and
persists it as an advisory run (admin/analyst with Workforce access). Pay is computed from the clock
(dispatch -> completion), with California overtime and the three pay classes; workers whose pay-form
hours diverge from the clock are flagged for a manual **payroll adjustment**.

``POST /v1/agents/workforce/payroll/adjustments`` PROPOSES that adjustment for a flagged worker through
the human-approved action gate (ADR 0007) — propose only; an admin still approves + executes via the
existing ``/v1/actions`` routes. Proposing touches nothing external.
"""
from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status

from app.actions import service as actions_service
from app.actions.schemas import ActionOut, ProposeActionIn
from app.agents.workforce import payroll_service
from app.agents.workforce.payroll_schemas import PayrollRunResult
from app.api.deps import require_agent_access, require_agent_runner
from app.security import Principal

router = APIRouter(prefix="/v1/agents/workforce/payroll", tags=["workforce"])


@router.post("", response_model=PayrollRunResult, status_code=status.HTTP_201_CREATED)
async def trigger_run(
    period_start: date | None = Query(None, description="Pay-period start (defaults to today)"),
    period_end: date | None = Query(None, description="Pay-period end (defaults to a 7-day window)"),
    force: bool = Query(False, description="Bypass idempotency and force a fresh run"),
    principal: Principal = Depends(require_agent_runner("workforce")),
) -> PayrollRunResult:
    """Compute payroll for the period and persist it (admin/analyst only). Advisory — nothing is
    written back to ServiceTitan here (the adjustment goes through the action gate)."""
    return await payroll_service.run_payroll_analysis(
        principal, period_start=period_start, period_end=period_end, force=force
    )


@router.get("/latest")
async def latest_run(principal: Principal = Depends(require_agent_access("workforce"))) -> dict:
    result = await payroll_service.get_latest_result(principal)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no payroll runs yet")
    return result


@router.get("/runs")
async def list_runs(
    limit: int = Query(20, ge=1, le=100),
    principal: Principal = Depends(require_agent_access("workforce")),
) -> list[dict]:
    return await payroll_service.list_recent_runs(principal, limit=limit)


@router.get("/runs/{run_id}")
async def get_run(
    run_id: uuid.UUID, principal: Principal = Depends(require_agent_access("workforce"))
) -> dict:
    result = await payroll_service.get_result_by_id(principal, run_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="payroll run not found")
    return result


@router.post("/adjustments", response_model=ActionOut, status_code=status.HTTP_201_CREATED)
async def propose_adjustment(
    run_id: uuid.UUID = Body(..., embed=True, description="The payroll run the worker was flagged in"),
    worker_id: str = Body(..., embed=True, description="The flagged worker to adjust"),
    principal: Principal = Depends(require_agent_runner("workforce")),
) -> ActionOut:
    """Propose a ``payroll_adjustment`` for a flagged worker through the action gate (admin/analyst).

    Params are assembled server-side from the persisted run (the clock vs claimed hours + period), so a
    caller cannot inject an adjustment for a worker whose hours already reconcile. Propose only —
    approval + execution stay on the existing ``/v1/actions/{id}/{approve,execute}`` admin routes.
    """
    stored = await payroll_service.get_result_by_id(principal, run_id)
    if stored is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="payroll run not found")
    result = PayrollRunResult.model_validate(stored)
    try:
        params = payroll_service.proposed_adjustment_params(result, worker_id, run_id=run_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    payload = ProposeActionIn(
        agent="workforce", kind="payroll_adjustment", run_id=run_id, params=params
    )
    return await actions_service.propose_action(principal, payload)
