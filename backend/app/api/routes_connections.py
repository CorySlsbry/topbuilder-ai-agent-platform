"""Connection (credential vault) endpoints — store/list/test per-tenant integration secrets.

Secrets are Fernet-encrypted at rest (ADR 0002 / app/crypto.py) and never returned by the API.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.deps import get_principal, require_admin
from app.config import get_settings
from app.db import tenant_session
from app.repositories import credentials, runs
from app.security import Principal

router = APIRouter(prefix="/v1/connections", tags=["connections"])


class ConnectionIn(BaseModel):
    provider: str  # servicetitan | quickbooks
    secret: dict
    metadata: dict = {}


@router.get("")
async def list_connections(principal: Principal = Depends(get_principal)) -> list[dict]:
    async with tenant_session(principal.tenant_id) as session:
        return await credentials.list_providers(session)


@router.put("")
async def upsert_connection(
    body: ConnectionIn, principal: Principal = Depends(require_admin)
) -> dict:
    if not get_settings().credential_encryption_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="credential vault not configured (set CREDENTIAL_ENCRYPTION_KEY)",
        )
    async with tenant_session(principal.tenant_id) as session:
        await credentials.store_credential(
            session, provider=body.provider, secret=body.secret, metadata=body.metadata
        )
        await runs.insert_audit(
            session,
            actor=str(principal.user_id),
            action="connection.upsert",
            target=body.provider,
            detail={"provider": body.provider},
        )
    return {"ok": True, "provider": body.provider}


@router.post("/{provider}/test")
async def test_connection(
    provider: str, principal: Principal = Depends(require_admin)
) -> dict:
    settings = get_settings()
    async with tenant_session(principal.tenant_id) as session:
        secret = await credentials.get_credential(session, provider=provider)
    if secret is None:
        raise HTTPException(status_code=404, detail=f"no stored credentials for '{provider}'")
    try:
        if provider == "servicetitan":
            from app.integrations.servicetitan.live_client import LiveServiceTitanClient

            scoped = settings.model_copy(
                update={
                    "servicetitan_client_id": secret.get("client_id"),
                    "servicetitan_client_secret": secret.get("client_secret"),
                    "servicetitan_app_key": secret.get("app_key"),
                    "servicetitan_tenant_id": secret.get("tenant_id"),
                }
            )
            await LiveServiceTitanClient(scoped)._access_token()
        elif provider == "quickbooks":
            from app.integrations.accounting.quickbooks_client import QuickBooksClient

            scoped = settings.model_copy(
                update={
                    "quickbooks_client_id": secret.get("client_id"),
                    "quickbooks_client_secret": secret.get("client_secret"),
                    "quickbooks_refresh_token": secret.get("refresh_token"),
                    "quickbooks_realm_id": secret.get("realm_id"),
                }
            )
            await QuickBooksClient(scoped)._access_token()
        else:
            raise HTTPException(status_code=400, detail=f"unknown provider '{provider}'")
        return {"ok": True, "provider": provider}
    except HTTPException:
        raise
    except Exception as exc:  # auth failure / network — report, don't 500
        return {"ok": False, "provider": provider, "error": str(exc)}
