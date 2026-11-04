"""Persistence for self-learning GOVERNANCE (Phase C/D): golden cases, eval runs, the tunable param
store, drift snapshots, and the preference approval lifecycle. Tenant-scoped by RLS; mirrors the
conventions in memory.py (asyncpg casts, RETURNING *).
"""
from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _row(mapping: Any) -> dict | None:
    return dict(mapping) if mapping is not None else None


# --- Golden-set cases ----------------------------------------------------------------------------
async def insert_golden(
    session: AsyncSession, *, agent: str, situation_text: str,
    must_include: list[str] | None = None, must_avoid: list[str] | None = None,
    situation_features: dict | None = None, note: str | None = None, created_by: uuid.UUID | None = None,
) -> dict | None:
    result = await session.execute(
        text(
            """
            INSERT INTO golden_cases
              (agent, situation_text, situation_features, must_include, must_avoid, note, created_by)
            VALUES (:agent, :st, CAST(:sf AS jsonb), CAST(:inc AS text[]), CAST(:avoid AS text[]), :note, :cb)
            RETURNING *
            """
        ),
        {
            "agent": agent, "st": situation_text, "sf": json.dumps(situation_features or {}),
            "inc": list(must_include or []), "avoid": list(must_avoid or []),
            "note": note, "cb": created_by,
        },
    )
    return _row(result.mappings().first())


async def list_golden(session: AsyncSession, *, agent: str | None = None) -> list[dict]:
    result = await session.execute(
        text(
            """
            SELECT * FROM golden_cases
            WHERE CAST(:agent AS text) IS NULL OR agent = :agent
            ORDER BY created_at DESC
            """
        ),
        {"agent": agent},
    )
    return [dict(m) for m in result.mappings().all()]


async def delete_golden(session: AsyncSession, *, case_id: uuid.UUID) -> None:
    await session.execute(text("DELETE FROM golden_cases WHERE id = :id"), {"id": case_id})


# --- Eval runs -----------------------------------------------------------------------------------
async def insert_eval_run(
    session: AsyncSession, *, preference_id: uuid.UUID | None, agent: str,
    golden_total: int, golden_passed: int, score: float, invariant_ok: bool, verdict: str,
    detail: dict | None = None,
) -> dict | None:
    result = await session.execute(
        text(
            """
            INSERT INTO eval_runs
              (preference_id, agent, golden_total, golden_passed, score, invariant_ok, verdict, detail)
            VALUES (:pid, :agent, :gt, :gp, :score, :inv, :verdict, CAST(:detail AS jsonb))
            RETURNING *
            """
        ),
        {
            "pid": preference_id, "agent": agent, "gt": golden_total, "gp": golden_passed,
            "score": score, "inv": invariant_ok, "verdict": verdict, "detail": json.dumps(detail or {}),
        },
    )
    return _row(result.mappings().first())


async def list_eval_runs(session: AsyncSession, *, preference_id: uuid.UUID, limit: int = 10) -> list[dict]:
    result = await session.execute(
        text("SELECT * FROM eval_runs WHERE preference_id = :pid ORDER BY created_at DESC LIMIT :limit"),
        {"pid": preference_id, "limit": limit},
    )
    return [dict(m) for m in result.mappings().all()]


# --- Tunable params --------------------------------------------------------------------------------
async def get_param(
    session: AsyncSession, *, name: str, agent: str | None = None, default: float = 0.0
) -> float:
    """Resolve a knob, most-specific wins: (tenant,agent) > (tenant,*) > (global,agent) > (global,*)."""
    result = await session.execute(
        text(
            """
            SELECT value FROM learning_params
            WHERE name = :name AND (agent = :agent OR agent IS NULL)
            ORDER BY (tenant_id IS NOT NULL) DESC, (agent IS NOT NULL) DESC
            LIMIT 1
            """
        ),
        {"name": name, "agent": agent},
    )
    row = result.scalar_one_or_none()
    return float(row) if row is not None else default


async def set_param(
    session: AsyncSession, *, name: str, value: float, agent: str, updated_by: uuid.UUID | None = None
) -> dict | None:
    """Upsert a tenant+agent-scoped knob (the bandit tuner / admin writes here)."""
    result = await session.execute(
        text(
            """
            INSERT INTO learning_params (agent, name, value, updated_by)
            VALUES (:agent, :name, :value, :ub)
            ON CONFLICT (tenant_id, agent, name)
            DO UPDATE SET value = EXCLUDED.value, updated_by = EXCLUDED.updated_by, updated_at = now()
            RETURNING *
            """
        ),
        {"agent": agent, "name": name, "value": value, "ub": updated_by},
    )
    return _row(result.mappings().first())


async def list_params(session: AsyncSession) -> list[dict]:
    result = await session.execute(text("SELECT * FROM learning_params ORDER BY name, agent NULLS FIRST"))
    return [dict(m) for m in result.mappings().all()]


# --- Drift snapshots -------------------------------------------------------------------------------
async def insert_drift(
    session: AsyncSession, *, agent: str, window_days: int, sample_size: int,
    edit_rate: float | None, reject_rate: float | None, avg_effectiveness: float | None, flagged: bool,
) -> dict | None:
    result = await session.execute(
        text(
            """
            INSERT INTO drift_snapshots
              (agent, window_days, sample_size, edit_rate, reject_rate, avg_effectiveness, flagged)
            VALUES (:agent, :wd, :ss, :er, :rr, :ae, :flag)
            RETURNING *
            """
        ),
        {"agent": agent, "wd": window_days, "ss": sample_size, "er": edit_rate,
         "rr": reject_rate, "ae": avg_effectiveness, "flag": flagged},
    )
    return _row(result.mappings().first())


async def list_drift(session: AsyncSession, *, agent: str | None = None, limit: int = 20) -> list[dict]:
    result = await session.execute(
        text(
            """
            SELECT * FROM drift_snapshots
            WHERE CAST(:agent AS text) IS NULL OR agent = :agent
            ORDER BY created_at DESC LIMIT :limit
            """
        ),
        {"agent": agent, "limit": limit},
    )
    return [dict(m) for m in result.mappings().all()]


# --- Preference approval lifecycle ----------------------------------------------------------------
async def get_preference(session: AsyncSession, *, preference_id: uuid.UUID) -> dict | None:
    result = await session.execute(
        text("SELECT * FROM agent_preferences WHERE id = :id"), {"id": preference_id}
    )
    return _row(result.mappings().first())


async def list_preferences(
    session: AsyncSession, *, agent: str | None = None, status: str | None = None, limit: int = 100
) -> list[dict]:
    result = await session.execute(
        text(
            """
            SELECT * FROM agent_preferences
            WHERE (CAST(:agent AS text) IS NULL OR agent = :agent)
              AND (CAST(:status AS text) IS NULL OR status = :status)
            ORDER BY
              CASE status WHEN 'candidate' THEN 0 WHEN 'active' THEN 1 ELSE 2 END,
              support_count DESC, last_confirmed_at DESC
            LIMIT :limit
            """
        ),
        {"agent": agent, "status": status, "limit": limit},
    )
    return [dict(m) for m in result.mappings().all()]


async def record_eval(
    session: AsyncSession, *, preference_id: uuid.UUID, score: float, total: int, passed: int
) -> dict | None:
    result = await session.execute(
        text(
            """
            UPDATE agent_preferences
            SET eval_score = :score, eval_total = :total, eval_passed = :passed
            WHERE id = :id RETURNING *
            """
        ),
        {"id": preference_id, "score": score, "total": total, "passed": passed},
    )
    return _row(result.mappings().first())


async def approve_preference(
    session: AsyncSession, *, preference_id: uuid.UUID,
    reviewed_by: uuid.UUID | None, rollout_pct: int = 100,
) -> dict | None:
    """Promote a candidate to ACTIVE (optionally behind a canary %). Only candidates can be approved."""
    result = await session.execute(
        text(
            """
            UPDATE agent_preferences
            SET status = 'active', reviewed_by = :rb, reviewed_at = now(),
                rollout_pct = :pct, activated_at = now()
            WHERE id = :id AND status = 'candidate'
            RETURNING *
            """
        ),
        {"id": preference_id, "rb": reviewed_by, "pct": max(0, min(100, rollout_pct))},
    )
    return _row(result.mappings().first())


async def set_rollout(session: AsyncSession, *, preference_id: uuid.UUID, rollout_pct: int) -> dict | None:
    result = await session.execute(
        text(
            "UPDATE agent_preferences SET rollout_pct = :pct WHERE id = :id AND status = 'active' RETURNING *"
        ),
        {"id": preference_id, "pct": max(0, min(100, rollout_pct))},
    )
    return _row(result.mappings().first())


async def reject_preference(
    session: AsyncSession, *, preference_id: uuid.UUID, reviewed_by: uuid.UUID | None
) -> dict | None:
    result = await session.execute(
        text(
            """
            UPDATE agent_preferences
            SET status = 'rejected', reviewed_by = :rb, reviewed_at = now()
            WHERE id = :id AND status IN ('candidate', 'quarantined')
            RETURNING *
            """
        ),
        {"id": preference_id, "rb": reviewed_by},
    )
    return _row(result.mappings().first())


async def retire_preference(
    session: AsyncSession, *, preference_id: uuid.UUID, reviewed_by: uuid.UUID | None
) -> dict | None:
    result = await session.execute(
        text(
            """
            UPDATE agent_preferences
            SET status = 'retired', reviewed_by = :rb, reviewed_at = now()
            WHERE id = :id AND status = 'active'
            RETURNING *
            """
        ),
        {"id": preference_id, "rb": reviewed_by},
    )
    return _row(result.mappings().first())
