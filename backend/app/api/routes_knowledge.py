"""RAG "Learn" endpoints — upload knowledge, list documents, semantic search (per tenant + agent)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import get_principal, require_runner
from app.config import get_settings
from app.db import tenant_session
from app.rag.ingest import ingest_document
from app.rag.retrieve import retrieve
from app.repositories import knowledge, runs, usage
from app.security import Principal

router = APIRouter(prefix="/v1/knowledge", tags=["knowledge"])

VALID_AGENTS = {"workforce", "financial", "inventory", "general"}


class IngestIn(BaseModel):
    source_type: str = Field(max_length=16)  # text | markdown | csv | html | url
    source_ref: str = Field(max_length=2048)
    content: str | None = Field(default=None, max_length=1_000_000)  # required unless type == "url"


class SearchIn(BaseModel):
    query: str = Field(max_length=2000)
    k: int = Field(default=5, ge=1, le=25)


def _validate_agent(agent: str, principal: Principal) -> None:
    if agent not in VALID_AGENTS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown agent '{agent}'; use one of {sorted(VALID_AGENTS)}",
        )
    # Knowledge is per-agent and feeds that agent's retrieval; a department-scoped login must not write
    # to or read another department's agent knowledge base (mirror require_agent_access everywhere else).
    from app.org import permissions

    if not permissions.can_use_agent(principal.role, principal.department, agent):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"department '{principal.department}' does not include the {agent} agent",
        )


@router.post("/{agent}/documents", status_code=status.HTTP_201_CREATED)
async def ingest(
    agent: str, body: IngestIn, principal: Principal = Depends(require_runner)
) -> dict:
    _validate_agent(agent, principal)
    limit = get_settings().knowledge_ingest_daily_limit
    async with tenant_session(principal.tenant_id) as cap_session:
        if await usage.bump_tenant(cap_session, bucket="knowledge_ingest") > limit:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "daily knowledge-ingest limit reached")
    async with tenant_session(principal.tenant_id) as session:
        result = await ingest_document(
            session,
            agent=agent,
            source_type=body.source_type,
            source_ref=body.source_ref,
            content=body.content,
        )
        await runs.insert_audit(
            session,
            actor=str(principal.user_id),
            action="knowledge.ingest",
            target=agent,
            detail=result,
        )
    return result


@router.get("/{agent}/documents")
async def list_documents(agent: str, principal: Principal = Depends(get_principal)) -> list[dict]:
    _validate_agent(agent, principal)
    async with tenant_session(principal.tenant_id) as session:
        return await knowledge.list_documents(session, agent=agent)


@router.post("/{agent}/search")
async def search(
    agent: str, body: SearchIn, principal: Principal = Depends(get_principal)
) -> list[dict]:
    _validate_agent(agent, principal)
    async with tenant_session(principal.tenant_id) as session:
        return await retrieve(session, agent=agent, query=body.query, k=body.k)
