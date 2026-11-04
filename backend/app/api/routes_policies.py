"""Per-agent autonomy policy endpoints — the switch for each agent (off | hitl | auto)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.actions import service
from app.actions.schemas import PolicyIn, PolicyOut
from app.actions.service import ActionConflict
from app.api.deps import get_principal, require_admin
from app.security import Principal

router = APIRouter(prefix="/v1/agents/policies", tags=["actions"])


@router.get("", response_model=list[PolicyOut])
async def list_policies(principal: Principal = Depends(get_principal)) -> list[PolicyOut]:
    return await service.list_agent_policies(principal)


@router.get("/{agent}", response_model=PolicyOut)
async def get_policy(agent: str, principal: Principal = Depends(get_principal)) -> PolicyOut:
    return await service.get_agent_policy(principal, agent)


@router.put("/{agent}", response_model=PolicyOut)
async def set_policy(
    agent: str, payload: PolicyIn, principal: Principal = Depends(require_admin)
) -> PolicyOut:
    """Set an agent's autonomy: off (advisory) | hitl (propose→approve→execute) | auto (with undo)."""
    try:
        return await service.set_agent_policy(principal, agent, payload.mode)
    except ActionConflict as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
