"""Feedback / training endpoints — humans rate, edit, and correct agent output to train the agents."""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.deps import get_principal
from app.config import get_settings
from app.db import tenant_session
from app.org import permissions
from app.repositories import feedback as repo
from app.repositories import usage
from app.security import Principal


def _require_agent_access(principal: Principal, agent: str | None) -> None:
    """403 unless the caller's department includes ``agent``. Feedback/training-signal feed the
    self-learning loop, so a department-scoped login must not rate, correct, or read ANOTHER
    department's agent (the rest of the app enforces this; these routes took agent as a free param)."""
    if agent and not permissions.can_use_agent(principal.role, principal.department, agent):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"department '{principal.department}' does not include the {agent} agent",
        )

router = APIRouter(prefix="/v1/feedback", tags=["feedback"])


class FeedbackIn(BaseModel):
    agent: str = Field(max_length=64)
    target_kind: str = Field(default="run", max_length=32)  # run | recommendation | action
    target_ref: str | None = Field(default=None, max_length=256)
    rating: str = Field(max_length=16)                       # up | down | edit
    # The corrected output (the training signal) — capped so it can't be a token-cost/DB-bloat vector.
    correction: str | None = Field(default=None, max_length=8000)
    note: str | None = Field(default=None, max_length=2000)
    run_id: uuid.UUID | None = None


class FeedbackOut(BaseModel):
    id: uuid.UUID
    agent: str
    run_id: uuid.UUID | None = None
    target_kind: str
    target_ref: str | None = None
    rating: str
    correction: str | None = None
    note: str | None = None
    created_by: uuid.UUID | None = None
    created_at: datetime

    @classmethod
    def of(cls, row: dict) -> "FeedbackOut":
        return cls(**{k: row.get(k) for k in cls.model_fields})


@router.post("", response_model=FeedbackOut, status_code=status.HTTP_201_CREATED)
async def submit(body: FeedbackIn, principal: Principal = Depends(get_principal)) -> FeedbackOut:
    """Capture a rating / edit / correction on an agent's output (dept-scoped to the caller's agents)."""
    _require_agent_access(principal, body.agent)
    limit = get_settings().feedback_daily_limit
    async with tenant_session(principal.tenant_id) as cap_session:
        if await usage.bump_tenant(cap_session, bucket="feedback") > limit:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "daily feedback limit reached")
    async with tenant_session(principal.tenant_id) as session:
        row = await repo.insert_feedback(
            session, feedback_id=uuid.uuid4(), agent=body.agent, run_id=body.run_id,
            target_kind=body.target_kind, target_ref=body.target_ref, rating=body.rating,
            correction=body.correction, note=body.note, created_by=principal.user_id,
        )
    # Self-learning loop (best-effort, ISOLATED session so it can never affect the feedback write):
    # label this run's case from the rating, and distill a substantial edit into a quorum-gated preference.
    try:
        from app.learning import service as learning

        async with tenant_session(principal.tenant_id) as ls:
            await learning.on_feedback(
                ls, agent=body.agent, run_id=body.run_id, rating=body.rating,
                target_ref=body.target_ref, correction=body.correction,
                created_by=str(principal.user_id),  # SEC-3: distinct-author quorum
            )
    except Exception:
        pass
    return FeedbackOut.of(row)  # type: ignore[arg-type]


@router.get("", response_model=list[FeedbackOut])
async def list_feedback(
    agent: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    principal: Principal = Depends(get_principal),
) -> list[FeedbackOut]:
    _require_agent_access(principal, agent)
    async with tenant_session(principal.tenant_id) as session:
        rows = await repo.list_feedback(session, agent=agent, limit=limit)
    return [FeedbackOut.of(r) for r in rows]


@router.get("/training-signal", response_model=list[FeedbackOut])
async def training_signal(
    agent: str = Query(..., description="The agent whose human corrections to retrieve"),
    limit: int = Query(20, ge=1, le=100),
    principal: Principal = Depends(get_principal),
) -> list[FeedbackOut]:
    """The corrections humans have supplied for this agent — the signal its reasoning layer learns from
    (and the source that can be ingested into the agent's Learn/RAG knowledge base)."""
    _require_agent_access(principal, agent)
    async with tenant_session(principal.tenant_id) as session:
        rows = await repo.recent_corrections(session, agent=agent, limit=limit)
    return [FeedbackOut.of(r) for r in rows]
