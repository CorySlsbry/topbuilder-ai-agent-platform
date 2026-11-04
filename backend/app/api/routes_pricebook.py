"""Pricebook agent endpoints.

``POST /v1/agents/pricebook/runs`` runs the deterministic re-pricing engine and persists it as an
advisory set of item changes (admin/analyst with Pricebook access). ``GET /runs/latest`` reads it back.
``POST /runs/{run_id}/update`` PROPOSES writing a recomputed price for one item through the
human-approved action gate (ADR 0007) — params are assembled SERVER-SIDE from the persisted run, so a
caller cannot inject an arbitrary price for an item. Propose only; an admin still approves + executes via
the existing ``/v1/actions`` routes. Pricebook changes are customer-facing prices, so the kind is
ALWAYS human-in-the-loop (never auto-executed, even in auto mode).
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile, status

from app.actions import service as actions_service
from app.actions.schemas import ActionOut, ProposeActionIn
from app.agents.pricebook import price_file, service
from app.agents.pricebook.schemas import PricebookRunResult
from app.api.deps import require_agent_access, require_agent_runner
from app.security import Principal

router = APIRouter(prefix="/v1/agents/pricebook", tags=["pricebook"])

MAX_PRICE_FILE_BYTES = 5_000_000  # cap an uploaded supplier price file (DoS guard)


@router.post("/price-file", response_model=PricebookRunResult, status_code=status.HTTP_201_CREATED)
async def upload_price_file(
    file: UploadFile = File(...),
    vendor: str = Query("vendor", description="Default vendor name when the file has no vendor column"),
    principal: Principal = Depends(require_agent_runner("pricebook")),
) -> PricebookRunResult:
    """Upload a supplier/distributor price file (CSV or Excel) -> parse vendor unit costs -> re-price the
    pricebook under the sold-hour model (advisory). This is the 'teach the agent from an Excel sheet'
    path for the distributors ServiceTitan's own procurement integration doesn't cover. Advisory only —
    no price is written here; each change still goes through the human-approved action gate."""
    data = await file.read(MAX_PRICE_FILE_BYTES + 1)
    if len(data) > MAX_PRICE_FILE_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "price file too large (max 5 MB)")
    try:
        updates = price_file.parse_price_file(file.filename or "upload.csv", data, default_vendor=vendor)
    except price_file.PriceFileError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"could not parse the price file: {exc}") from exc
    return await service.run_pricebook_from_price_file(principal, updates=updates)


@router.post("/runs", response_model=PricebookRunResult, status_code=status.HTTP_201_CREATED)
async def trigger_run(
    force: bool = Query(False, description="Bypass idempotency and force a fresh run"),
    principal: Principal = Depends(require_agent_runner("pricebook")),
) -> PricebookRunResult:
    """Re-price the Pricebook against the latest vendor cost update (old->new price, deltas, margin,
    flags) and persist it (admin/analyst only). Advisory — no price is written here (writes go through
    the gate)."""
    return await service.run_pricebook_analysis(principal, force=force)


@router.get("/runs/latest")
async def latest_run(principal: Principal = Depends(require_agent_access("pricebook"))) -> dict:
    result = await service.get_latest_result(principal)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no pricebook runs yet")
    return result


@router.get("/runs")
async def list_runs(
    limit: int = Query(20, ge=1, le=100),
    principal: Principal = Depends(require_agent_access("pricebook")),
) -> list[dict]:
    return await service.list_recent_runs(principal, limit=limit)


@router.get("/runs/{run_id}")
async def get_run(
    run_id: uuid.UUID, principal: Principal = Depends(require_agent_access("pricebook"))
) -> dict:
    result = await service.get_result_by_id(principal, run_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="pricebook run not found")
    return result


@router.post("/runs/{run_id}/update", response_model=ActionOut, status_code=status.HTTP_201_CREATED)
async def propose_update(
    run_id: uuid.UUID,
    code: str = Body(..., embed=True, description="The pricebook item code to re-price"),
    principal: Principal = Depends(require_agent_runner("pricebook")),
) -> ActionOut:
    """Propose writing a recomputed price for one item through the action gate.

    The action kind + params are assembled server-side from the persisted run (the engine-computed
    old/new price + the drivers), so a caller cannot inject an arbitrary price or re-price an unchanged
    item. Propose only — approval + execution stay on the existing ``/v1/actions/{id}/{approve,execute}``
    admin routes, and a pricebook update is ALWAYS human-in-the-loop.
    """
    stored = await service.get_result_by_id(principal, run_id)
    if stored is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="pricebook run not found")
    result = PricebookRunResult.model_validate(stored)
    try:
        kind, params = service.proposed_pricebook_update_params(result, code, run_id=run_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    payload = ProposeActionIn(agent="pricebook", kind=kind, run_id=run_id, params=params)
    return await actions_service.propose_action(principal, payload)
