"""Booking-agent phone voice: the registry + per-tenant selection (mirrors routes_providers)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.deps import get_principal, require_admin
from app.db import tenant_session
from app.repositories import tenant_settings
from app.security import Principal
from app.voice import voices

router = APIRouter(prefix="/v1", tags=["voice"])


@router.get("/voice/options")
async def list_voice_options(principal: Principal = Depends(get_principal)) -> list[dict]:
    """The voices the 24/7 booking agent can answer with."""
    return voices.as_list()


@router.get("/tenant/voice")
async def get_tenant_voice(principal: Principal = Depends(get_principal)) -> dict:
    async with tenant_session(principal.tenant_id) as session:
        key = await tenant_settings.get_booking_voice(session)
    return {"voice": key}


class VoiceIn(BaseModel):
    voice: str


@router.put("/tenant/voice")
async def set_tenant_voice(
    body: VoiceIn, principal: Principal = Depends(require_admin)
) -> dict:
    key = body.voice.strip().lower()
    if not voices.is_valid(key):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"unknown voice '{body.voice}'; valid: {sorted(voices.VOICES)}",
        )
    async with tenant_session(principal.tenant_id) as session:
        await tenant_settings.set_booking_voice(session, key=key)
    return {"voice": key}
