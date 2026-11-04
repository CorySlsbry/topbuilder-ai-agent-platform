"""Task worklist endpoints — the agent-generated + manual task list, by department."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_principal, require_runner
from app.operations import service
from app.operations.schemas import CreateTaskIn, TaskOut, UpdateTaskIn
from app.security import Principal

router = APIRouter(prefix="/v1/tasks", tags=["operations"])


@router.get("", response_model=list[TaskOut])
async def list_tasks(
    department: str | None = Query(None),
    status_: str | None = Query(None, alias="status"),
    principal: Principal = Depends(get_principal),
) -> list[TaskOut]:
    return await service.list_tasks(principal, department=department, status=status_)


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
async def create_task(payload: CreateTaskIn, principal: Principal = Depends(require_runner)) -> TaskOut:
    return await service.create_task(principal, payload)


@router.patch("/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: uuid.UUID, payload: UpdateTaskIn, principal: Principal = Depends(require_runner)
) -> TaskOut:
    result = await service.update_task(principal, task_id, payload)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
    return result
