"""Dev auth: mint a tenant-scoped JWT for a demo tenant.

Enabled only when ENV=dev. In production this is replaced by your IdP (Supabase/Auth0/Entra),
which issues the JWT carrying the tenant claim — see app/security.py.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text

from app.api.deps import get_principal
from app.config import get_settings
from app.db import tenant_session
from app.demo import DEFAULT_DEMO_SLUG, DEMO_TENANTS
from app.org import permissions
from app.security import Principal, create_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/config")
async def auth_config() -> dict:
    """Public auth discovery for the SPA: which login methods exist on this deployment.
    The anon key is publishable by design (Supabase client-side key); no secrets here."""
    settings = get_settings()
    return {
        "auth_mode": settings.auth_mode,
        "supabase_url": settings.supabase_url,
        "supabase_anon_key": settings.supabase_anon_key,
    }


@router.get("/me")
async def me(principal: Principal = Depends(get_principal)) -> dict:
    """Who am I: tenant, role, 2FA status, department scope, and org-person link."""
    tenant_name = next(
        (t.name for t in DEMO_TENANTS.values() if t.tenant_id == principal.tenant_id), None
    )
    if tenant_name is None:
        try:
            async with tenant_session(principal.tenant_id) as session:
                row = (
                    await session.execute(
                        text("SELECT name FROM tenants WHERE id = :t"), {"t": str(principal.tenant_id)}
                    )
                ).first()
                tenant_name = row[0] if row else str(principal.tenant_id)
        except Exception:
            tenant_name = str(principal.tenant_id)
    person = None
    if principal.person_id:  # dev tokens carry no membership -> person stays null
        try:
            async with tenant_session(principal.tenant_id) as session:
                row = (
                    await session.execute(
                        text(
                            "SELECT p.id, p.full_name, p.title, d.key AS department_key "
                            "FROM org_people p JOIN org_departments d ON d.id = p.department_id "
                            "WHERE p.id = :pid"
                        ),
                        {"pid": principal.person_id},
                    )
                ).first()
                if row is not None:
                    person = {
                        "id": str(row.id),
                        "full_name": row.full_name,
                        "title": row.title,
                        "department_key": row.department_key,
                    }
        except Exception:
            person = None
    agents = permissions.allowed_agents(principal.role, principal.department)
    sections = permissions.allowed_sections(principal.role, principal.department)
    return {
        "tenant_id": str(principal.tenant_id),
        "tenant_name": tenant_name,
        "email": principal.email,
        "role": principal.role,
        "aal": principal.aal,
        "two_factor_required": principal.role == "admin" and principal.aal != "aal2",
        "department": principal.department,
        "allowed_agents": sorted(agents) if agents is not None else None,
        "allowed_sections": list(sections) if sections is not None else None,
        "person": person,
    }


class DevTokenRequest(BaseModel):
    tenant_slug: str = DEFAULT_DEMO_SLUG
    role: str = "admin"
    department: str | None = None  # org dept key; lets the demo mint a department-scoped lead token


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    tenant_slug: str
    tenant_id: str
    role: str


@router.post("/dev-token", response_model=TokenResponse)
async def dev_token(req: DevTokenRequest) -> TokenResponse:
    settings = get_settings()
    if not settings.is_dev:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="dev-token is disabled outside ENV=dev"
        )
    tenant = DEMO_TENANTS.get(req.tenant_slug)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown demo tenant '{req.tenant_slug}'; try one of {list(DEMO_TENANTS)}",
        )
    token = create_token(
        tenant_id=tenant.tenant_id,
        user_id=tenant.admin_user_id,
        email=tenant.admin_email,
        role=req.role,
        department=req.department,
    )
    return TokenResponse(
        access_token=token,
        tenant_slug=tenant.slug,
        tenant_id=str(tenant.tenant_id),
        role=req.role,
    )
