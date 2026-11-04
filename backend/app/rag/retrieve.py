"""Tenant + agent scoped semantic retrieval over the knowledge base."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.rag.embeddings import get_embedding_provider
from app.repositories import knowledge


async def retrieve(
    session: AsyncSession,
    *,
    agent: str | None,
    query: str,
    k: int | None = None,
    settings: Settings | None = None,
) -> list[dict]:
    settings = settings or get_settings()
    provider = get_embedding_provider(settings)
    embeddings = await provider.embed([query])
    return await knowledge.search_chunks(
        session, agent=agent, query_embedding=embeddings[0], k=k or settings.rag_top_k
    )
