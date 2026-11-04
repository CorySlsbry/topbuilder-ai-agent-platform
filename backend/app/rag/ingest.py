"""Ingestion pipeline: parse -> chunk -> embed -> store (pgvector), tenant + agent scoped."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.rag.chunking import chunk_text
from app.rag.embeddings import get_embedding_provider
from app.rag.parsing import parse_content
from app.repositories import knowledge


async def ingest_document(
    session: AsyncSession,
    *,
    agent: str,
    source_type: str,
    source_ref: str,
    content: str | None,
    settings: Settings | None = None,
) -> dict:
    settings = settings or get_settings()
    parsed = await parse_content(source_type, source_ref, content, settings=settings)
    # Clamp the text actually embedded so a large document can't drive unbounded embedding spend.
    max_chars = settings.knowledge_max_embed_chars
    if len(parsed) > max_chars:
        parsed = parsed[:max_chars]
    chunks = chunk_text(parsed)
    provider = get_embedding_provider(settings)
    embeddings = await provider.embed(chunks) if chunks else []

    document_id = await knowledge.insert_document(
        session, agent=agent, source_type=source_type, source_ref=source_ref
    )
    for index, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        await knowledge.insert_chunk(
            session,
            document_id=document_id,
            content=chunk,
            embedding=embedding,
            metadata={"chunk_index": index, "source_ref": source_ref},
        )
    return {"document_id": str(document_id), "chunks": len(chunks), "agent": agent}
