"""Human-approved action endpoints (ADR 0007): propose -> approve -> execute, gated + audited."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.actions import service
from app.actions.ownership import KIND_OWNER
from app.actions.schemas import ActionOut, ProposeActionIn
from app.actions.service import (
    ActionConflict,
    ActionDisabled,
    ActionExecutionError,
    ActionForbidden,
    ActionNotFound,
)
from app.api.deps import get_principal, require_lead_or_admin, require_runner
from app.org import permissions
from app.security import Principal

router = APIRouter(prefix="/v1/actions", tags=["actions"])


@router.post("", response_model=ActionOut, status_code=status.HTTP_201_CREATED)
async def propose(payload: ProposeActionIn, principal: Principal = Depends(require_runner)) -> ActionOut:
    """Propose a write to a system of record (admin/analyst). Proposing touches nothing external.

    Scope the proposal by BOTH the action's owning agent (derived from the KIND) and the declared
    ``agent`` — the same dept bar the dedicated run routes enforce — so a runner can't hand-craft a
    cross-department write (e.g. a workforce ``payroll_adjustment``) through this generic route.
    Admin / no-department is unrestricted.
    """
    for agent in {KIND_OWNER.get(payload.kind), payload.agent}:
        if agent and not permissions.can_use_agent(principal.role, principal.department, agent):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"department '{principal.department}' does not include the {agent} agent for this action",
            )
    return await service.propose_action(principal, payload)


@router.get("", response_model=list[ActionOut])
async def list_actions(
    agent: str | None = Query(None),
    status: str | None = Query(None, description="filter by status, e.g. 'proposed' for the approvals queue"),
    limit: int = Query(50, ge=1, le=200),
    principal: Principal = Depends(get_principal),
) -> list[ActionOut]:
    """The caller's actions. Department-scoped server-side: a department principal sees only actions
    whose owning agent is in their department (their approvals queue); admin/leadership sees all."""
    return await service.list_actions(principal, agent=agent, status=status, limit=limit)


@router.get("/{action_id}", response_model=ActionOut)
async def get_action(action_id: uuid.UUID, principal: Principal = Depends(get_principal)) -> ActionOut:
    action = await service.get_action(principal, action_id)
    if action is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="action not found")
    return action


@router.post("/{action_id}/approve", response_model=ActionOut)
async def approve(action_id: uuid.UUID, principal: Principal = Depends(require_lead_or_admin)) -> ActionOut:
    """A department lead (or admin) approves a proposed action in their department. No write happens
    here — only execute writes. The per-department + money/legal authz runs in the service layer."""
    try:
        return await service.approve_action(principal, action_id)
    except ActionNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="action not found") from None
    except ActionForbidden as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ActionConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/{action_id}/reject", response_model=ActionOut)
async def reject(action_id: uuid.UUID, principal: Principal = Depends(require_lead_or_admin)) -> ActionOut:
    """A department lead (or admin) DISAPPROVES a proposed action (it is never executed). Same
    per-department authorization as approve."""
    try:
        return await service.reject_action(principal, action_id)
    except ActionNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="action not found") from None
    except ActionForbidden as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ActionConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/{action_id}/execute", response_model=ActionOut)
async def execute(action_id: uuid.UUID, principal: Principal = Depends(require_lead_or_admin)) -> ActionOut:
    """A department lead (or admin) executes an approved action in their department — the actual write,
    only if ACTIONS_ENABLED. Idempotent. The per-department + money/legal authz runs in the service."""
    try:
        return await service.execute_action(principal, action_id)
    except ActionNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="action not found") from None
    except ActionForbidden as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ActionDisabled as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ActionConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ActionExecutionError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post("/{action_id}/undo", response_model=ActionOut)
async def undo(action_id: uuid.UUID, principal: Principal = Depends(require_lead_or_admin)) -> ActionOut:
    """Reverse an executed action (autonomous-with-undo) — runs a compensation write. Idempotent. A
    lead may only undo within their own department."""
    try:
        return await service.undo_action(principal, action_id)
    except ActionNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="action not found") from None
    except ActionForbidden as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ActionConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ActionExecutionError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
