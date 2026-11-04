"""Persistence for the self-learning layer (case bank + learned preferences). Tenant-scoped by RLS.

A case stores the *situation* and the *recommendation shape* + the human-feedback OUTCOME — never an
authoritative computed figure (ADR 0003). Retrieval feeds the narration prompt only. Mirrors the
conventions in `feedback.py`: RLS auto-fills tenant_id, params cast for asyncpg, RETURNING *.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _row(mapping: Any) -> dict | None:
    return dict(mapping) if mapping is not None else None


def _vec(embedding: list[float] | None) -> str | None:
    """pgvector literal '[v0,v1,...]' for `CAST(:p AS vector)` (None -> SQL NULL)."""
    if embedding is None:
        return None
    return "[" + ",".join(repr(float(x)) for x in embedding) + "]"


async def insert_case(
    session: AsyncSession,
    *,
    case_id: uuid.UUID,
    agent: str,
    task_type: str,
    run_id: uuid.UUID | None,
    target_ref: str | None,
    problem_text: str,
    problem_features: dict | None,
    embedding: list[float] | None,
    recommendation_kind: str,
    recommendation_summary: str,
    model_version: str | None = None,
) -> dict | None:
    result = await session.execute(
        text(
            """
            INSERT INTO agent_cases
              (id, agent, task_type, run_id, target_ref, problem_text, problem_features, embedding,
               recommendation_kind, recommendation_summary, model_version)
            VALUES (:id, :agent, :tt, :run, :tr, :pt, CAST(:pf AS jsonb), CAST(:emb AS vector),
                    :rk, :rs, :mv)
            RETURNING *
            """
        ),
        {
            "id": case_id, "agent": agent, "tt": task_type, "run": run_id, "tr": target_ref,
            "pt": problem_text, "pf": json.dumps(problem_features or {}), "emb": _vec(embedding),
            "rk": recommendation_kind, "rs": recommendation_summary, "mv": model_version,
        },
    )
    return _row(result.mappings().first())


async def get_case_by_run(
    session: AsyncSession, *, run_id: uuid.UUID, target_ref: str | None = None
) -> dict | None:
    result = await session.execute(
        text(
            """
            SELECT * FROM agent_cases
            WHERE run_id = :run AND (CAST(:tr AS text) IS NULL OR target_ref = :tr)
            ORDER BY created_at DESC LIMIT 1
            """
        ),
        {"run": run_id, "tr": target_ref},
    )
    return _row(result.mappings().first())


async def label_case(
    session: AsyncSession, *, case_id: uuid.UUID, outcome: str,
    effectiveness: float, edit_cost: float | None = None
) -> dict | None:
    result = await session.execute(
        text(
            """
            UPDATE agent_cases
            SET outcome = :outcome, effectiveness = :eff, edit_cost = :ec, resolved_at = now()
            WHERE id = :id
            RETURNING *
            """
        ),
        {"id": case_id, "outcome": outcome, "eff": effectiveness, "ec": edit_cost},
    )
    return _row(result.mappings().first())


async def search_cases(
    session: AsyncSession, *, agent: str, embedding: list[float] | None,
    k: int = 5, min_effectiveness: float | None = None
) -> list[dict]:
    """Nearest resolved cases for this agent (brute-force cosine kNN; matches knowledge_chunks)."""
    if embedding is None:
        return []
    result = await session.execute(
        text(
            """
            SELECT id, agent, problem_text, recommendation_summary, outcome, effectiveness,
                   (embedding <=> CAST(:emb AS vector)) AS distance, created_at
            FROM agent_cases
            WHERE agent = :agent AND embedding IS NOT NULL AND outcome <> 'pending'
              AND (CAST(:min AS real) IS NULL OR effectiveness >= :min)
            ORDER BY embedding <=> CAST(:emb AS vector)
            LIMIT :k
            """
        ),
        {"agent": agent, "emb": _vec(embedding), "min": min_effectiveness, "k": k},
    )
    return [dict(m) for m in result.mappings().all()]


_QUORUM_DISTINCT_SUPPORTERS = 3


async def _record_supporter(session: AsyncSession, *, preference_id, supporter: str) -> int:
    """Register one DISTINCT corroborating user and return the distinct-supporter count."""
    await session.execute(
        text(
            "INSERT INTO agent_preference_supporters (preference_id, supporter) VALUES (:pid, :s) "
            "ON CONFLICT (tenant_id, preference_id, supporter) DO NOTHING"
        ),
        {"pid": str(preference_id), "s": supporter},
    )
    row = (
        await session.execute(
            text("SELECT count(*) FROM agent_preference_supporters WHERE preference_id = :pid"),
            {"pid": str(preference_id)},
        )
    ).first()
    return int(row[0])


async def upsert_preference(
    session: AsyncSession, *, agent: str, task_type: str | None,
    preference_text: str, embedding: list[float] | None, proposed_by: str = "edit"
) -> dict | None:
    """Corroborate a near-identical existing preference (promoting it to CANDIDATE only when
    DISTINCT supporters reach quorum), else insert a new quarantined one. SEC-3: quorum counts
    distinct users (`proposed_by`), so one actor repeating the same correction can't promote a rule
    alone. A candidate still must clear the eval gate + human approval before going ACTIVE."""
    supporter = (proposed_by or "edit").strip() or "edit"
    if embedding is not None:
        near = await session.execute(
            text(
                """
                SELECT id, support_count, (embedding <=> CAST(:emb AS vector)) AS distance
                FROM agent_preferences
                WHERE agent = :agent AND status <> 'retired' AND embedding IS NOT NULL
                ORDER BY embedding <=> CAST(:emb AS vector) LIMIT 1
                """
            ),
            {"agent": agent, "emb": _vec(embedding)},
        )
        row = near.mappings().first()
        if row is not None and row["distance"] is not None and row["distance"] <= 0.08:  # cosine sim >= ~0.92
            distinct = await _record_supporter(session, preference_id=row["id"], supporter=supporter)
            upd = await session.execute(
                text(
                    """
                    UPDATE agent_preferences
                    SET support_count = :distinct, last_confirmed_at = now(),
                        status = CASE WHEN :distinct >= :quorum AND status = 'quarantined'
                                      THEN 'candidate' ELSE status END
                    WHERE id = :id RETURNING *
                    """
                ),
                {"id": row["id"], "distinct": distinct, "quorum": _QUORUM_DISTINCT_SUPPORTERS},
            )
            return _row(upd.mappings().first())
    ins = await session.execute(
        text(
            """
            INSERT INTO agent_preferences (agent, task_type, preference_text, embedding, proposed_by,
                                           support_count)
            VALUES (:agent, :tt, :pt, CAST(:emb AS vector), :pby, 1) RETURNING *
            """
        ),
        {"agent": agent, "tt": task_type, "pt": preference_text, "emb": _vec(embedding), "pby": supporter},
    )
    new_pref = _row(ins.mappings().first())
    if new_pref is not None:
        await _record_supporter(session, preference_id=new_pref["id"], supporter=supporter)
    return new_pref


async def recent_resolved_cases(
    session: AsyncSession, *, agent: str, limit: int = 200
) -> list[dict]:
    """Resolved cases (feedback-labeled, not pending) for an agent — the raw material the nightly
    consolidation reflects over (losses to learn from, effectiveness trend for drift/tuning)."""
    result = await session.execute(
        text(
            """
            SELECT id, problem_text, recommendation_summary, outcome, effectiveness, edit_cost, created_at
            FROM agent_cases
            WHERE agent = :agent AND outcome <> 'pending'
            ORDER BY created_at DESC LIMIT :limit
            """
        ),
        {"agent": agent, "limit": limit},
    )
    return [dict(m) for m in result.mappings().all()]


async def active_preferences(session: AsyncSession, *, agent: str, limit: int = 5) -> list[dict]:
    result = await session.execute(
        text(
            """
            SELECT * FROM agent_preferences
            WHERE agent = :agent AND status = 'active'
            ORDER BY support_count DESC, last_confirmed_at DESC LIMIT :limit
            """
        ),
        {"agent": agent, "limit": limit},
    )
    return [dict(m) for m in result.mappings().all()]


async def insert_event(
    session: AsyncSession, *, agent: str, operation: str,
    target_table: str | None = None, target_id: uuid.UUID | None = None, rationale: str | None = None
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO learning_events (agent, operation, target_table, target_id, rationale)
            VALUES (:agent, :op, :tt, :tid, :r)
            """
        ),
        {"agent": agent, "op": operation, "tt": target_table, "tid": target_id, "r": rationale},
    )
