"""A/R Collections agent endpoints.

``POST /v1/agents/collections/runs`` runs the deterministic A/R engine and persists it as an advisory
worklist (admin/analyst with Collections access). ``GET /runs/latest`` reads it back. ``POST
/runs/{run_id}/dunning`` PROPOSES sending a dunning step for a worklist customer through the
human-approved action gate (ADR 0007) — params are assembled SERVER-SIDE from the persisted run, so a
caller cannot inject a dunning send for a customer who is current/reconciled. Propose only; an admin
still approves + executes via the existing ``/v1/actions`` routes.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status

from app.actions import service as actions_service
from app.actions.schemas import ActionOut, ProposeActionIn
from app.agents.collections import service
from app.agents.collections.schemas import CollectionsRunResult
from app.api.deps import require_agent_access, require_agent_runner
from app.security import Principal

router = APIRouter(prefix="/v1/agents/collections", tags=["collections"])


@router.post("/runs", response_model=CollectionsRunResult, status_code=status.HTTP_201_CREATED)
async def trigger_run(
    force: bool = Query(False, description="Bypass idempotency and force a fresh run"),
    principal: Principal = Depends(require_agent_runner("collections")),
) -> CollectionsRunResult:
    """Build the A/R collections worklist (bucket, status, owner, next-action, dunning draft) and
    persist it (admin/analyst only). Advisory — nothing is sent here (dunning goes through the gate)."""
    return await service.run_collections_analysis(principal, force=force)


@router.get("/runs/latest")
async def latest_run(principal: Principal = Depends(require_agent_access("collections"))) -> dict:
    result = await service.get_latest_result(principal)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no collections runs yet")
    return result


@router.get("/runs")
async def list_runs(
    limit: int = Query(20, ge=1, le=100),
    principal: Principal = Depends(require_agent_access("collections")),
) -> list[dict]:
    return await service.list_recent_runs(principal, limit=limit)


@router.get("/runs/{run_id}")
async def get_run(
    run_id: uuid.UUID, principal: Principal = Depends(require_agent_access("collections"))
) -> dict:
    result = await service.get_result_by_id(principal, run_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="collections run not found")
    return result


@router.post("/runs/{run_id}/dunning", response_model=ActionOut, status_code=status.HTTP_201_CREATED)
async def propose_dunning(
    run_id: uuid.UUID,
    customer_id: str = Body(..., embed=True, description="The worklist customer to dun"),
    principal: Principal = Depends(require_agent_runner("collections")),
) -> ActionOut:
    """Propose a dunning step (email / SMS / call) for a worklist customer through the action gate.

    The action kind + params are assembled server-side from the persisted run (the compliance-gated
    channel, the engine-computed balance/age/step, and the ready-to-send draft), so a caller cannot
    inject a send for a customer who is current/reconciled or has no compliant channel. Propose only —
    approval + execution stay on the existing ``/v1/actions/{id}/{approve,execute}`` admin routes.
    """
    stored = await service.get_result_by_id(principal, run_id)
    if stored is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="collections run not found")
    result = CollectionsRunResult.model_validate(stored)
    try:
        kind, params = service.proposed_dunning_params(result, customer_id, run_id=run_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    payload = ProposeActionIn(agent="collections", kind=kind, run_id=run_id, params=params)
    return await actions_service.propose_action(principal, payload)
