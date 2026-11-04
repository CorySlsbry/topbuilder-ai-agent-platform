"""Field-system providers: the registry + per-tenant selection (the dynamic layer)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.deps import get_principal, require_admin
from app.db import tenant_session
from app.integrations.providers import registry
from app.repositories import tenant_settings
from app.security import Principal

router = APIRouter(prefix="/v1", tags=["providers"])


@router.get("/providers")
async def list_providers(principal: Principal = Depends(get_principal)) -> list[dict]:
    """The top-10 contractor/builder systems the platform adapts to."""
    return registry.as_list()


@router.get("/tenant/provider")
async def get_tenant_provider(principal: Principal = Depends(get_principal)) -> dict:
    async with tenant_session(principal.tenant_id) as session:
        slug = await tenant_settings.get_fsm_provider(session)
    p = registry.get_provider(slug)
    return {"provider": slug, "display": p.display, "segment": p.segment, "status": p.status}


class ProviderIn(BaseModel):
    provider: str


@router.put("/tenant/provider")
async def set_tenant_provider(
    body: ProviderIn, principal: Principal = Depends(require_admin)
) -> dict:
    slug = body.provider.strip().lower()
    if not registry.is_valid(slug):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"unknown provider '{body.provider}'; valid: {sorted(registry.PROVIDERS)}",
        )
    async with tenant_session(principal.tenant_id) as session:
        await tenant_settings.set_fsm_provider(session, slug=slug)
    p = registry.get_provider(slug)
    return {"provider": slug, "display": p.display, "segment": p.segment, "status": p.status}
