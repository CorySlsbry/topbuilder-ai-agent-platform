"""Front-desk services. Seeds a realistic inbox + worklist on first read (per tenant) for the demo;
when live, communications stream from the telephony/ServiceTitan adapters and tasks are agent-generated.
"""
from __future__ import annotations

import json
import pathlib
import uuid

from app.db import tenant_session
from app.operations.schemas import (
    CommunicationOut,
    CreateTaskIn,
    SendCommunicationIn,
    TaskOut,
    UpdateTaskIn,
)
from app.repositories import communications as comms_repo
from app.repositories import tasks as tasks_repo
from app.security import Principal

_FX = pathlib.Path(__file__).parent / "fixtures"


def _load(name: str) -> list[dict]:
    return json.loads((_FX / name).read_text(encoding="utf-8"))


# --- communications -----------------------------------------------------------------------
async def list_communications(
    principal: Principal, *, channel: str | None = None, status: str | None = None
) -> list[CommunicationOut]:
    async with tenant_session(principal.tenant_id) as session:
        if await comms_repo.count(session) == 0:
            await comms_repo.seed(session, _load("communications.json"))
        rows = await comms_repo.list_(session, channel=channel, status=status)
    return [CommunicationOut.model_validate(r) for r in rows]


async def send_communication(principal: Principal, payload: SendCommunicationIn) -> CommunicationOut:
    async with tenant_session(principal.tenant_id) as session:
        row = await comms_repo.insert_outbound(
            session, channel=payload.channel, contact_name=payload.contact_name,
            contact_phone=payload.contact_phone, contact_email=payload.contact_email,
            subject=payload.subject, body=payload.body,
        )
    return CommunicationOut.model_validate(row)


async def set_communication_status(
    principal: Principal, comm_id: uuid.UUID, status: str
) -> CommunicationOut | None:
    async with tenant_session(principal.tenant_id) as session:
        row = await comms_repo.set_status(session, comm_id=comm_id, status=status)
    return CommunicationOut.model_validate(row) if row else None


# --- tasks --------------------------------------------------------------------------------
async def list_tasks(
    principal: Principal, *, department: str | None = None, status: str | None = None
) -> list[TaskOut]:
    async with tenant_session(principal.tenant_id) as session:
        if await tasks_repo.count(session) == 0:
            await tasks_repo.seed(session, _load("tasks.json"))
        rows = await tasks_repo.list_(session, department=department, status=status)
    return [TaskOut.model_validate(r) for r in rows]


async def create_task(principal: Principal, payload: CreateTaskIn) -> TaskOut:
    async with tenant_session(principal.tenant_id) as session:
        row = await tasks_repo.insert(
            session, title=payload.title, detail=payload.detail, department=payload.department,
            priority=payload.priority, source_agent=payload.source_agent,
            related_ref=payload.related_ref, assignee_role=payload.assignee_role,
        )
    return TaskOut.model_validate(row)


async def update_task(principal: Principal, task_id: uuid.UUID, payload: UpdateTaskIn) -> TaskOut | None:
    async with tenant_session(principal.tenant_id) as session:
        row = await tasks_repo.update(
            session, task_id=task_id, status=payload.status, assignee_role=payload.assignee_role
        )
    return TaskOut.model_validate(row) if row else None
