"""Persistence for the RAG knowledge base (tenant-scoped via RLS, pgvector similarity search)."""
from __future__ import annotations

import json
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _vector_literal(vec: list[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"


async def insert_document(
    session: AsyncSession, *, agent: str, source_type: str, source_ref: str
) -> uuid.UUID:
    row = (
        await session.execute(
            text(
                "INSERT INTO knowledge_documents (agent, source_type, source_ref) "
                "VALUES (:a, :st, :sr) RETURNING id"
            ),
            {"a": agent, "st": source_type, "sr": source_ref},
        )
    ).first()
    return row[0]


async def insert_chunk(
    session: AsyncSession,
    *,
    document_id: uuid.UUID,
    content: str,
    embedding: list[float],
    metadata: dict,
) -> None:
    await session.execute(
        text(
            "INSERT INTO knowledge_chunks (document_id, content, embedding, metadata) "
            "VALUES (:d, :c, CAST(:e AS vector), CAST(:m AS jsonb))"
        ),
        {"d": document_id, "c": content, "e": _vector_literal(embedding), "m": json.dumps(metadata)},
    )


async def list_documents(session: AsyncSession, *, agent: str | None = None) -> list[dict]:
    rows = (
        await session.execute(
            text(
                "SELECT id, agent, source_type, source_ref, uploaded_at FROM knowledge_documents "
                "WHERE (CAST(:agent AS text) IS NULL OR agent = :agent) ORDER BY uploaded_at DESC"
            ),
            {"agent": agent},
        )
    ).mappings().all()
    return [dict(m) for m in rows]


async def search_chunks(
    session: AsyncSession, *, agent: str | None, query_embedding: list[float], k: int
) -> list[dict]:
    rows = (
        await session.execute(
            text(
                """
                SELECT c.content, c.document_id, c.metadata,
                       1 - (c.embedding <=> CAST(:q AS vector)) AS score
                FROM knowledge_chunks c
                JOIN knowledge_documents d ON c.document_id = d.id
                WHERE (CAST(:agent AS text) IS NULL OR d.agent = :agent)
                ORDER BY c.embedding <=> CAST(:q AS vector)
                LIMIT :k
                """
            ),
            {"q": _vector_literal(query_embedding), "agent": agent, "k": k},
        )
    ).mappings().all()
    results: list[dict] = []
    for row in rows:
        item = dict(row)
        if isinstance(item.get("metadata"), str):
            item["metadata"] = json.loads(item["metadata"])
        item["score"] = round(float(item["score"]), 4)
        results.append(item)
    return results
