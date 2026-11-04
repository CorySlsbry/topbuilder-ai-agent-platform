"""Support / operator-reporting surface.

  * POST /v1/support/intake — an AUTHENTICATED user submits a bug / feature / question (the in-app
    "report a problem / request a feature / ask a question" form). We persist the report and fire the
    Slack + email fan-out to the operator (Cory). Authenticated (not public) to avoid drive-by spam;
    the reporter's identity is taken from the JWT, never the body.
  * GET /v1/support — operator-only list (+ optional kind filter) of everything captured.
  * POST /v1/support/cron/digest — machine-auth (X-Cron-Key) daily digest, mirroring the sync crons:
    404 when no cron_secret is configured, 403 on a bad key.

Reporting is best-effort: a Slack/email failure never fails the user's submission (the row still lands).
"""
from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.deps import get_principal, require_admin
from app.config import get_settings
from app.db import operator_session
from app.notify import support_kinds
from app.notify.capture import capture_support_request
from app.repositories import support as support_repo
from app.security import Principal

router = APIRouter(prefix="/v1/support", tags=["support"])


def _check_cron(x_cron_key: str | None) -> None:
    settings = get_settings()
    if not settings.cron_secret:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "cron not configured")
    if not x_cron_key or not hmac.compare_digest(x_cron_key, settings.cron_secret):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "bad cron key")


class IntakeIn(BaseModel):
    kind: str
    message: str = Field(min_length=1, max_length=6000)
    name: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=320)


@router.post("/intake", status_code=status.HTTP_202_ACCEPTED)
async def intake(body: IntakeIn, principal: Principal = Depends(get_principal)) -> dict:
    """Capture a user-submitted bug / feature / question and notify the operator. 202 = accepted;
    the notification fan-out is best-effort and never blocks or fails the submission."""
    if not support_kinds.is_intake_kind(body.kind):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"kind must be one of {sorted(support_kinds.INTAKE_KINDS)}",
        )
    # Identity comes from the verified principal, not the client-supplied name/email (anti-spoof).
    row = await capture_support_request(
        kind=body.kind,
        name=body.name,
        email=principal.email or body.email,
        message=body.message,
        source="in_app",
        meta={"tenant_id": str(principal.tenant_id), "user_id": str(principal.user_id),
              "role": principal.role},
    )
    return {"status": "received", "id": str(row["id"]) if row else None}


@router.get("")
async def list_support(
    kind: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    principal: Principal = Depends(require_admin),
) -> dict:
    """Operator-only: list captured support requests, newest first, optionally filtered by kind."""
    if kind is not None and not support_kinds.is_kind(kind):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"unknown kind '{kind}'")
    async with operator_session() as session:
        rows = await support_repo.list_support_requests(session, kind=kind, limit=limit)
    return {"support_requests": rows, "count": len(rows)}


@router.post("/cron/digest")
async def cron_digest(
    hours: int = Query(24, ge=1, le=168),
    x_cron_key: str | None = Header(default=None, alias="X-Cron-Key"),
) -> dict:
    """Summarize the last `hours` of support requests by kind and send ONE Slack + email digest."""
    _check_cron(x_cron_key)
    from app.notify import notifier

    async with operator_session() as session:
        counts, total = await support_repo.counts_since(session, hours=hours)
    result = await notifier.send_digest(get_settings(), counts, total=total)
    return {"window_hours": hours, "total": total, "by_kind": counts, "delivery": result}
