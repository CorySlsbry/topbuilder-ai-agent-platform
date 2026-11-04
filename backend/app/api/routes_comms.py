"""Communications endpoints — the inbox (calls/sms/email/voicemail/web) + 2-way send."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_principal, require_runner
from app.operations import service
from app.operations.schemas import CommunicationOut, CommunicationStatusIn, SendCommunicationIn
from app.security import Principal

router = APIRouter(prefix="/v1/communications", tags=["operations"])


@router.get("", response_model=list[CommunicationOut])
async def list_comms(
    channel: str | None = Query(None),
    status_: str | None = Query(None, alias="status"),
    principal: Principal = Depends(get_principal),
) -> list[CommunicationOut]:
    return await service.list_communications(principal, channel=channel, status=status_)


@router.post("", response_model=CommunicationOut, status_code=status.HTTP_201_CREATED)
async def send_comm(
    payload: SendCommunicationIn, principal: Principal = Depends(require_runner)
) -> CommunicationOut:
    """Send an outbound message (the 2-way side). Fixture records it; live routes through ServiceTitan."""
    return await service.send_communication(principal, payload)


@router.patch("/{comm_id}", response_model=CommunicationOut)
async def set_status(
    comm_id: uuid.UUID, payload: CommunicationStatusIn, principal: Principal = Depends(require_runner)
) -> CommunicationOut:
    result = await service.set_communication_status(principal, comm_id, payload.status)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="communication not found")
    return result
