"""Operator administration (super-admin layer): manage user memberships (invites).

Operator-only: every endpoint requires the admin role AND a verified second factor (aal2) via
require_admin. Memberships are e-mail invites — the user signs up / logs in with Supabase Auth
and resolution links their auth_user_id on first login (repositories/memberships.resolve).

SECURITY (the multi-tenant boundary): a per-tenant `admin` is NOT a platform operator. The
user_memberships directory is the one table with a permissive write RLS policy (resolution runs
pre-GUC), so the API authorization here is the ONLY thing stopping cross-tenant admin injection.
A caller may only administer a tenant OTHER than their own if their verified email is on the
platform-operator allowlist (settings.platform_operator_emails). Otherwise every invite/list is
forced to the caller's own tenant.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator

from app.api.deps import require_admin
from app.config import get_settings
from app.demo import DEMO_TENANTS
from app.repositories import memberships
from app.security import Principal

router = APIRouter(prefix="/v1/admin", tags=["admin"])

# 'lead' = a department lead who can APPROVE/execute writes within their department (incl. money/legal);
# 'analyst' can run + propose but not approve; 'viewer' is read-only; 'admin' is the operator.
VALID_ROLES = {"admin", "analyst", "viewer", "lead"}


def _is_platform_operator(principal: Principal) -> bool:
    allow = get_settings().platform_operator_email_set
    return bool(principal.email) and principal.email.strip().lower() in allow


def _authorize_tenant_target(target: uuid.UUID, principal: Principal) -> None:
    """A tenant admin may only administer their own tenant; cross-tenant needs platform operator."""
    if target != principal.tenant_id and not _is_platform_operator(principal):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "managing another tenant's members requires a platform-operator account",
        )


class InviteIn(BaseModel):
    email: str
    role: str = "analyst"
    tenant_slug: str | None = None  # demo tenants by slug; otherwise tenant_id
    tenant_id: uuid.UUID | None = None
    department: str | None = None  # org department key; None = unrestricted/executive view
    person_id: uuid.UUID | None = None  # org_people row this login represents

    @field_validator("email")
    @classmethod
    def _email_sane(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("not a valid e-mail address")
        return v


def _resolve_tenant(body: InviteIn, principal: Principal) -> uuid.UUID:
    if body.tenant_id is not None:
        target = body.tenant_id
    elif body.tenant_slug:
        tenant = DEMO_TENANTS.get(body.tenant_slug)
        if tenant is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown tenant slug '{body.tenant_slug}'")
        target = tenant.tenant_id
    else:
        return principal.tenant_id  # default: invite into the operator's own tenant
    _authorize_tenant_target(target, principal)  # cross-tenant target -> platform operator only
    return target


@router.get("/memberships")
async def list_memberships(
    tenant_slug: str | None = None, principal: Principal = Depends(require_admin)
) -> list[dict]:
    tenant_id = principal.tenant_id
    if tenant_slug:
        tenant = DEMO_TENANTS.get(tenant_slug)
        if tenant is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown tenant slug '{tenant_slug}'")
        tenant_id = tenant.tenant_id
        _authorize_tenant_target(tenant_id, principal)  # don't disclose another tenant's roster
    return await memberships.list_for_tenant(tenant_id)


@router.post("/memberships", status_code=status.HTTP_201_CREATED)
async def create_membership(body: InviteIn, principal: Principal = Depends(require_admin)) -> dict:
    if body.role not in VALID_ROLES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"role must be one of {sorted(VALID_ROLES)}")
    tenant_id = _resolve_tenant(body, principal)
    return await memberships.invite(
        email=body.email,
        tenant_id=tenant_id,
        role=body.role,
        department=body.department,
        person_id=body.person_id,
    )
