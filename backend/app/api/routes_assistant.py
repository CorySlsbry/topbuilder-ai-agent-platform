"""The in-app assistant endpoint. Any authenticated principal may chat; what the assistant can
actually DO is decided per tool call by the registry's permission gate (department scope for agent
reads, operator-only for workflow writes). Stateless: the client sends its own recent history."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.api.deps import get_principal
from app.assistant import service
from app.middleware import RateLimitMiddleware
from app.security import Principal

router = APIRouter(prefix="/v1/assistant", tags=["assistant"])


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=6000)


class ChatIn(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=24)


@router.post("/chat")
async def chat(body: ChatIn, request: Request, principal: Principal = Depends(get_principal)) -> dict:
    client_ip = RateLimitMiddleware._client_key(request)  # trusted X-Forwarded-For hop
    result = await service.chat(
        principal, [m.model_dump() for m in body.messages], client_ip=client_ip
    )
    # Operator reporting: let Cory see that a customer used the assistant. Scheduled FIRE-AND-FORGET so
    # neither a capture/notify failure NOR its transport latency (a hung Slack webhook, a slow email
    # provider) can affect the assistant response the user is waiting on — the answer is already built.
    try:
        last_user = next(
            (m.content for m in reversed(body.messages) if m.role == "user"), None
        )
        from app.notify.capture import schedule_capture

        schedule_capture(
            kind="chatbot",
            name=None,
            email=principal.email,
            message=(last_user or "")[:500],
            source="assistant",
            meta={"tenant_id": str(principal.tenant_id), "user_id": str(principal.user_id)},
        )
    except Exception:  # pragma: no cover - defensive; scheduling is already best-effort internally
        pass
    return result
