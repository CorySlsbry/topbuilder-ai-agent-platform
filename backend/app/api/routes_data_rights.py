"""Data-rights API: retention policy disclosure + right-to-erasure purge (operator-only).

Two endpoints:

* ``GET  /v1/data/retention``        — the documented retention policy (any authenticated principal).
* ``DELETE /v1/data/tenants/{id}``   — purge ALL of one tenant's data, FK-safe. Destructive and
  irreversible, so it is gated to a PLATFORM OPERATOR (the same allowlist that guards cross-tenant
  membership administration in routes_admin): ``require_admin`` (admin role + verified 2FA / aal2)
  AND the caller's verified email on ``settings.platform_operator_emails``. A per-tenant admin —
  even targeting their own tenant — may not erase a whole dataset through the API.

The purge runs inside a session scoped to the TARGET tenant, so RLS double-scopes every DELETE; the
operation is recorded in the append-only audit log within that same transaction.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_principal, require_admin
from app.config import get_settings
from app.data_rights import service
from app.db import tenant_session
from app.repositories import runs
from app.security import Principal

router = APIRouter(prefix="/v1/data", tags=["data-rights"])


def _is_platform_operator(principal: Principal) -> bool:
    """The caller's verified email is on the platform-operator allowlist (closed by default)."""
    allow = get_settings().platform_operator_email_set
    return bool(principal.email) and principal.email.strip().lower() in allow


def _require_platform_operator(principal: Principal) -> None:
    if not _is_platform_operator(principal):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "erasing a tenant's data requires a platform-operator account",
        )


@router.get("/retention")
async def get_retention_policy(_: Principal = Depends(get_principal)) -> dict:
    """Return the documented retention policy (per-data-class windows)."""
    return {"policy": service.retention_policy()}


@router.delete("/tenants/{tenant_id}")
async def purge_tenant(
    tenant_id: uuid.UUID, principal: Principal = Depends(require_admin)
) -> dict:
    """Right-to-erasure: delete every row owned by ``tenant_id`` (operator-only, audited)."""
    _require_platform_operator(principal)
    async with tenant_session(tenant_id) as session:
        deleted = await service.purge_tenant_data(session, tenant_id)
        await runs.insert_audit(
            session,
            actor=principal.email or str(principal.user_id),
            action="data.purge_tenant",
            target=str(tenant_id),
            detail={"deleted": deleted},
        )
    return {"tenant_id": str(tenant_id), "deleted": deleted}
