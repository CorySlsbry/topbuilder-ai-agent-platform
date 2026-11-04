"""API schemas for human-approved actions (ADR 0007)."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ProposeActionIn(BaseModel):
    agent: str
    kind: str
    params: dict = Field(default_factory=dict)
    run_id: uuid.UUID | None = None
    idempotency_key: str | None = None  # caller-supplied; else derived from kind + params


class ActionOut(BaseModel):
    id: uuid.UUID
    run_id: uuid.UUID | None = None
    agent: str
    kind: str
    status: str
    params: dict
    idempotency_key: str
    result: dict | None = None
    error: str | None = None
    requested_by: uuid.UUID | None = None
    approved_by: uuid.UUID | None = None
    approved_at: datetime | None = None
    executed_at: datetime | None = None
    created_at: datetime

    @classmethod
    def from_row(cls, row: dict) -> "ActionOut":
        return cls(
            id=row["id"],
            run_id=row.get("run_id"),
            agent=row["agent"],
            kind=row["kind"],
            status=row["status"],
            params=row.get("params") or {},
            idempotency_key=row["idempotency_key"],
            result=row.get("result"),
            error=row.get("error"),
            requested_by=row.get("requested_by"),
            approved_by=row.get("approved_by"),
            approved_at=row.get("approved_at"),
            executed_at=row.get("executed_at"),
            created_at=row["created_at"],
        )


class PolicyOut(BaseModel):
    agent: str
    mode: str  # off | hitl | auto
    updated_at: datetime | None = None


class PolicyIn(BaseModel):
    mode: str
