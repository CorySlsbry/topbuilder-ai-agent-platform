"""Persistence for agent runs, recommendations, reasoning logs, and audit events.

All queries run on a tenant-scoped session (see app/db.py), so RLS auto-filters by tenant and the
`tenant_id` column default stamps the current tenant on insert — application code never passes it.
"""
from __future__ import annotations

import dataclasses
import json
import uuid
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.workforce.analytics import WorkforceAnalysis


def _payload(obj: Any) -> str:
    return json.dumps(dataclasses.asdict(obj), default=str)


def _maybe_json(value: Any) -> Any:
    """asyncpg may hand back jsonb as text via a raw select; normalize to a Python object."""
    return json.loads(value) if isinstance(value, str) else value


async def create_run(
    session: AsyncSession,
    *,
    run_id: uuid.UUID,
    agent: str,
    status: str,
    horizon_days: int,
    inputs_hash: str | None,
    created_by: uuid.UUID,
    duration_ms: int,
    error: str | None = None,
    result: dict | None = None,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    cost_usd: float | None = None,
) -> None:
    """Persist a run. `tokens_in/tokens_out/cost_usd` meter the narration LLM (migration 0024) and are
    NULL on the deterministic template path (no model call) — they never carry a business figure."""
    await session.execute(
        text(
            """
            INSERT INTO agent_runs
              (id, agent, status, inputs_hash, horizon_days, created_by,
               finished_at, duration_ms, error, result,
               tokens_in, tokens_out, cost_usd)
            VALUES
              (:id, :agent, :status, :inputs_hash, :horizon_days, :created_by,
               now(), :duration_ms, :error, CAST(:result AS jsonb),
               :tokens_in, :tokens_out, :cost_usd)
            """
        ),
        {
            "id": run_id,
            "agent": agent,
            "status": status,
            "inputs_hash": inputs_hash,
            "horizon_days": horizon_days,
            "created_by": created_by,
            "duration_ms": duration_ms,
            "error": error,
            "result": json.dumps(result) if result is not None else None,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_usd": cost_usd,
        },
    )


async def insert_recommendations(
    session: AsyncSession, *, run_id: uuid.UUID, analysis: WorkforceAnalysis
) -> None:
    insert = text(
        """
        INSERT INTO agent_recommendations
          (run_id, kind, payload, confidence, economic_impact_cents)
        VALUES (:run_id, :kind, CAST(:payload AS jsonb), :confidence, :cents)
        """
    )
    for risk in analysis.understaffing_risks:
        await session.execute(
            insert,
            {
                "run_id": run_id,
                "kind": "understaffing",
                "payload": _payload(risk),
                "confidence": risk.confidence,
                "cents": risk.economic_impact_cents,
            },
        )
    for risk in analysis.overtime_risks:
        await session.execute(
            insert,
            {
                "run_id": run_id,
                "kind": "overtime",
                "payload": _payload(risk),
                "confidence": risk.confidence,
                "cents": risk.economic_impact_cents,
            },
        )


async def insert_reasoning_logs(
    session: AsyncSession, *, run_id: uuid.UUID, analysis: WorkforceAnalysis, reasoning_source: str
) -> None:
    rows: list[tuple[str, str]] = [
        (
            "analyze:summary",
            f"inputs_hash={analysis.inputs_hash}; "
            f"understaffing={len(analysis.understaffing_risks)}; "
            f"overtime={len(analysis.overtime_risks)}; reasoning_source={reasoning_source}",
        )
    ]
    rows += [
        (f"understaffing:{r.trade}:wk{r.week_offset}", r.reasoning)
        for r in analysis.understaffing_risks
    ]
    rows += [(f"overtime:{r.technician_id}", r.reasoning) for r in analysis.overtime_risks]

    insert = text(
        "INSERT INTO agent_reasoning_logs (run_id, step, detail) VALUES (:run_id, :step, :detail)"
    )
    for step, detail in rows:
        await session.execute(insert, {"run_id": run_id, "step": step, "detail": detail})


async def add_recommendations(session: AsyncSession, *, run_id: uuid.UUID, rows: list[dict]) -> None:
    """Agent-agnostic recommendation insert.

    Each row: {kind: str, payload: dict, confidence: float|None, economic_impact_cents: int|None}.
    """
    insert = text(
        """
        INSERT INTO agent_recommendations
          (run_id, kind, payload, confidence, economic_impact_cents)
        VALUES (:run_id, :kind, CAST(:payload AS jsonb), :confidence, :cents)
        """
    )
    for row in rows:
        await session.execute(
            insert,
            {
                "run_id": run_id,
                "kind": row["kind"],
                "payload": json.dumps(row["payload"], default=str),
                "confidence": row.get("confidence"),
                "cents": row.get("economic_impact_cents"),
            },
        )


async def add_reasoning(
    session: AsyncSession, *, run_id: uuid.UUID, rows: list[tuple[str, str]]
) -> None:
    insert = text(
        "INSERT INTO agent_reasoning_logs (run_id, step, detail) VALUES (:run_id, :step, :detail)"
    )
    for step, detail in rows:
        await session.execute(insert, {"run_id": run_id, "step": step, "detail": detail})


async def insert_audit(
    session: AsyncSession, *, actor: str, action: str, target: str | None, detail: dict
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO audit_events (actor, action, target, detail)
            VALUES (:actor, :action, :target, CAST(:detail AS jsonb))
            """
        ),
        {"actor": actor, "action": action, "target": target, "detail": json.dumps(detail)},
    )


async def get_latest_result(session: AsyncSession, *, agent: str) -> dict | None:
    row = (
        await session.execute(
            text(
                "SELECT result FROM agent_runs "
                "WHERE agent = :agent AND status = 'succeeded' AND result IS NOT NULL "
                "ORDER BY started_at DESC LIMIT 1"
            ),
            {"agent": agent},
        )
    ).first()
    return _maybe_json(row[0]) if row and row[0] is not None else None


async def get_result_by_id(session: AsyncSession, *, run_id: uuid.UUID) -> dict | None:
    row = (
        await session.execute(
            text("SELECT result FROM agent_runs WHERE id = :id"), {"id": run_id}
        )
    ).first()
    return _maybe_json(row[0]) if row and row[0] is not None else None


async def get_existing_result_by_hash(
    session: AsyncSession, *, agent: str, inputs_hash: str
) -> dict | None:
    """Idempotency: the most recent succeeded run for this (tenant, agent, inputs_hash)."""
    row = (
        await session.execute(
            text(
                "SELECT result FROM agent_runs "
                "WHERE agent = :agent AND status = 'succeeded' AND inputs_hash = :h "
                "AND result IS NOT NULL ORDER BY started_at DESC LIMIT 1"
            ),
            {"agent": agent, "h": inputs_hash},
        )
    ).first()
    return _maybe_json(row[0]) if row and row[0] is not None else None


async def list_succeeded_runs_in_range(
    session: AsyncSession, *, start: date, end: date
) -> list[dict]:
    """Every succeeded run with a result over [start, end] (inclusive), tenant-scoped by RLS.

    Returns ``{"date": <YYYY-MM-DD date>, "agent": str, "result": dict}`` ordered oldest→newest so a
    later run on the same day overrides an earlier one when the pure timeseries layer folds by day.
    The result jsonb is normalized to a Python object. Powers the executive KPI timeseries view.
    """
    rows = (
        await session.execute(
            text(
                """
                SELECT (started_at AT TIME ZONE 'UTC')::date AS run_date, agent, result
                FROM agent_runs
                WHERE status = 'succeeded' AND result IS NOT NULL
                  AND (started_at AT TIME ZONE 'UTC')::date BETWEEN :start AND :end
                ORDER BY started_at ASC
                """
            ),
            {"start": start, "end": end},
        )
    ).mappings().all()
    return [
        {"date": m["run_date"], "agent": m["agent"], "result": _maybe_json(m["result"])}
        for m in rows
    ]


async def list_succeeded_run_days_by_agent(
    session: AsyncSession, *, start: date, end: date
) -> dict[str, set[date]]:
    """Distinct UTC run days per agent for succeeded runs with a result over [start, end] inclusive
    (tenant-scoped by RLS) — the sparsity probe for the demo-history seeder. An (agent, day) present
    here is never re-seeded, so real runs always keep their day."""
    rows = (
        await session.execute(
            text(
                """
                SELECT DISTINCT agent, (started_at AT TIME ZONE 'UTC')::date AS run_date
                FROM agent_runs
                WHERE status = 'succeeded' AND result IS NOT NULL
                  AND (started_at AT TIME ZONE 'UTC')::date BETWEEN :start AND :end
                """
            ),
            {"start": start, "end": end},
        )
    ).mappings().all()
    days_by_agent: dict[str, set[date]] = {}
    for m in rows:
        days_by_agent.setdefault(m["agent"], set()).add(m["run_date"])
    return days_by_agent


async def list_runs(session: AsyncSession, *, agent: str, limit: int = 20) -> list[dict]:
    rows = (
        await session.execute(
            text(
                """
                SELECT id, agent, status, started_at, finished_at, duration_ms,
                       horizon_days, inputs_hash
                FROM agent_runs
                WHERE agent = :agent
                ORDER BY started_at DESC
                LIMIT :limit
                """
            ),
            {"agent": agent, "limit": limit},
        )
    ).mappings().all()
    return [dict(m) for m in rows]
