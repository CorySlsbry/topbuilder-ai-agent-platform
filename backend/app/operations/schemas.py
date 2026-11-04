"""API schemas for communications + tasks."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CommunicationOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: uuid.UUID
    channel: str
    direction: str
    contact_name: str | None = None
    contact_phone: str | None = None
    contact_email: str | None = None
    subject: str | None = None
    body: str | None = None
    status: str
    occurred_at: datetime
    customer_ref: str | None = None
    related_job_ref: str | None = None
    agent_handled: bool = False


class SendCommunicationIn(BaseModel):
    channel: str  # sms | email | call
    contact_name: str | None = None
    contact_phone: str | None = None
    contact_email: str | None = None
    subject: str | None = None
    body: str


class CommunicationStatusIn(BaseModel):
    status: str  # new | handled


class TaskOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: uuid.UUID
    title: str
    detail: str | None = None
    department: str
    status: str
    priority: int
    source_agent: str | None = None
    related_ref: str | None = None
    assignee_role: str | None = None
    due_at: datetime | None = None
    created_at: datetime


class CreateTaskIn(BaseModel):
    title: str
    detail: str | None = None
    department: str = "front_desk"
    priority: int = 3
    source_agent: str | None = None
    related_ref: str | None = None
    assignee_role: str | None = None


class UpdateTaskIn(BaseModel):
    status: str | None = None
    assignee_role: str | None = None
