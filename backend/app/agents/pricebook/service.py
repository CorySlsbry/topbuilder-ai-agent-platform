"""Orchestration entry point for the Pricebook agent.

Runs the LangGraph agent (compute, no DB) then persists atomically inside a single tenant-scoped
transaction — the same shape as ``collections/service.py``. Item-change rows are persisted as advisory
recommendations; nothing is written to the customer's Pricebook here. Writing a recomputed price goes
through the human-approved action gate (ADR 0007), and pricebook writes are ALWAYS human-in-the-loop.
"""
from __future__ import annotations

import dataclasses
import uuid
from datetime import date, datetime, timezone
from time import perf_counter

from app.agents import _telemetry
from app.agents.pricebook.analytics import PricebookAnalysis
from app.agents.pricebook.graph import PRICEBOOK_GRAPH
from app.agents.pricebook.schemas import PricebookRunResult, build_result
from app.config import get_settings
from app.db import tenant_session
from app.integrations.pricebook.client import get_pricebook_client
from app.repositories import runs
from app.security import Principal

AGENT = "pricebook"
# A re-price is an as-of snapshot, not a forecast horizon; record the lookback window in the shared
# `horizon_days` column for run bookkeeping (idempotency keys off `inputs_hash`).
LOOKBACK_DAYS = 0
# Coarse, situation-independent retrieval query (the high-value learned signal — CIPHER preferences
# distilled from past human edits — is general). The graph stays pure: the service retrieves, the
# narration layer only narrates.
_LESSON_QUERY = (
    "Pricebook re-pricing advisory narrative: sold-hour pricing model, vendor cost update, materials "
    "cost recompute, price delta and margin impact, items flagged beyond tolerance for review."
)


def _recommendation_rows(analysis: PricebookAnalysis) -> list[dict]:
    """One advisory recommendation per pricebook item change. Economic impact = the price delta."""
    return [
        {
            "kind": "pricebook_reprice",
            "payload": dataclasses.asdict(c),
            "confidence": None,
            "economic_impact_cents": c.price_delta_cents,
        }
        for c in analysis.changes
    ]


def _reasoning_rows(analysis: PricebookAnalysis, reasoning_source: str) -> list[tuple[str, str]]:
    t = analysis.totals
    rows: list[tuple[str, str]] = [
        (
            "analyze:summary",
            f"inputs_hash={analysis.inputs_hash}; items={t.items}; items_affected={t.items_affected}; "
            f"items_flagged={t.items_flagged}; total_price_delta_cents={t.total_price_delta_cents}; "
            f"vendor_coverage_pct={t.vendor_coverage_pct}; reasoning_source={reasoning_source}",
        )
    ]
    rows += [
        (f"reprice:{c.code}", f"{c.old_price_cents}->{c.new_price_cents} ({c.price_delta_pct:+.1f}%)")
        for c in analysis.changes
        if c.price_delta_cents != 0
    ]
    return rows


def _situation_brief(analysis: PricebookAnalysis) -> str:
    """A numbers-light description of the SITUATION for case retrieval — never the authoritative
    figures (those live only in the deterministic engine, per ADR 0003)."""
    t = analysis.totals
    return (
        f"Pricebook re-pricing advisory run; {t.items} catalog item(s), {t.items_affected} re-priced by "
        f"a vendor cost update, {t.items_flagged} flagged beyond tolerance for human review."
    )


class _PriceFileClient:
    """Wrap the tenant's pricebook client to swap in vendor updates parsed from an uploaded price file
    (Alex's 'teach the agent from an Excel sheet' path) — the items stay the real pricebook."""

    def __init__(self, base, updates) -> None:
        self._base = base
        self._updates = updates

    async def get_items(self):
        return await self._base.get_items()

    async def get_vendor_updates(self):
        return self._updates


async def run_pricebook_from_price_file(
    principal: Principal, *, updates, as_of: date | None = None
) -> PricebookRunResult:
    """Re-price the tenant's pricebook against vendor updates parsed from an uploaded supplier price file.
    Advisory + persisted exactly like a normal run; the actual price write still goes through the gate."""
    settings = get_settings()
    as_of = as_of or date.today()
    base = get_pricebook_client(as_of=as_of, settings=settings)
    return await run_pricebook_analysis(
        principal, as_of=as_of, force=True, client=_PriceFileClient(base, updates)
    )


async def run_pricebook_analysis(
    principal: Principal, *, as_of: date | None = None, force: bool = False, client=None
) -> PricebookRunResult:
    settings = get_settings()
    as_of = as_of or date.today()
    client = client or get_pricebook_client(as_of=as_of, settings=settings)
    started = perf_counter()

    # Self-learning READ: steer NARRATION only (ADR-0003 — never figures). Isolated + best-effort.
    lessons = ""
    try:
        from app.learning import service as learning

        async with tenant_session(principal.tenant_id) as ls:
            lessons = await learning.retrieve_lessons(
                ls, agent=AGENT, query_text=_LESSON_QUERY, settings=settings
            )
    except Exception:
        lessons = ""

    telemetry = _telemetry.start_collection()  # per-run narration cost (NULL on template path)
    try:
        state = await PRICEBOOK_GRAPH.ainvoke(
            {"as_of": as_of, "settings": settings, "client": client, "lessons": lessons}
        )
    except Exception as exc:
        duration_ms = int((perf_counter() - started) * 1000)
        async with tenant_session(principal.tenant_id) as session:
            failed_id = uuid.uuid4()
            await runs.create_run(
                session, run_id=failed_id, agent=AGENT, status="failed", horizon_days=LOOKBACK_DAYS,
                inputs_hash=None, created_by=principal.user_id, duration_ms=duration_ms,
                error=str(exc), result=None,
            )
            await runs.insert_audit(
                session, actor=str(principal.user_id), action="pricebook.run.failed",
                target=str(failed_id), detail={"error": str(exc)},
            )
        raise

    analysis: PricebookAnalysis = state["analysis"]
    narrative: str = state["narrative"]
    reasoning_source: str = state.get("reasoning_source", "template")
    duration_ms = int((perf_counter() - started) * 1000)
    run_id = uuid.uuid4()
    result = build_result(
        analysis,
        narrative=narrative,
        analysis_timestamp=datetime.now(timezone.utc),
        run_id=run_id,
    )

    async with tenant_session(principal.tenant_id) as session:
        if not force:
            existing = await runs.get_existing_result_by_hash(
                session, agent=AGENT, inputs_hash=analysis.inputs_hash
            )
            if existing is not None:
                return PricebookRunResult.model_validate(existing)
        await runs.create_run(
            session, run_id=run_id, agent=AGENT, status="succeeded", horizon_days=LOOKBACK_DAYS,
            inputs_hash=analysis.inputs_hash, created_by=principal.user_id, duration_ms=duration_ms,
            result=result.model_dump(mode="json"), **telemetry.as_run_fields(),
        )
        await runs.add_recommendations(session, run_id=run_id, rows=_recommendation_rows(analysis))
        await runs.add_reasoning(session, run_id=run_id, rows=_reasoning_rows(analysis, reasoning_source))
        await runs.insert_audit(
            session, actor=str(principal.user_id), action="pricebook.run", target=str(run_id),
            detail={
                "inputs_hash": analysis.inputs_hash,
                "items": analysis.totals.items,
                "items_affected": analysis.totals.items_affected,
                "total_price_delta_cents": analysis.totals.total_price_delta_cents,
                "reasoning_source": reasoning_source,
            },
        )

    # Self-learning WRITE: record this run as a CASE. Best-effort + ISOLATED so it can never roll back.
    try:
        from app.learning import service as learning

        async with tenant_session(principal.tenant_id) as ls:
            await learning.record_case(
                ls,
                agent=AGENT,
                run_id=run_id,
                problem_text=_situation_brief(analysis),
                recommendation_summary=(narrative or "")[:600],
                recommendation_kind="pricebook_advisory",
                problem_features={
                    "items": analysis.totals.items,
                    "items_affected": analysis.totals.items_affected,
                },
                settings=settings,
            )
    except Exception:
        pass

    return result


# --------------------------------------------------------------------------------------------
# Action-gate param assembly (server-side) for the gated "update a pricebook price" endpoint.
# --------------------------------------------------------------------------------------------
def proposed_pricebook_update_params(
    result: PricebookRunResult, code: str, *, run_id: uuid.UUID | None = None
) -> tuple[str, dict]:
    """Build the (kind, params) for a pricebook price update for one item, assembled server-side.

    Pure helper (tested): finds the item in the persisted run, refuses an unchanged item (no new price
    to write), and packages the engine-computed old/new price + the drivers so a caller can never inject
    an arbitrary price. The recomputed ``new_price`` and the prior ``old_price`` (for undo) come straight
    from the engine. Returns the action ``kind`` (always ``update_pricebook_item``).
    """
    match = next((c for c in result.changes if c.code == code), None)
    if match is None:
        raise ValueError(f"item '{code}' is not in this pricebook run")
    if match.price_delta_usd == 0:
        raise ValueError(f"item '{code}' price is unchanged — nothing to update")
    params = {
        "code": match.code,
        "name": match.name,
        "category": match.category,
        "old_price_cents": round(match.old_price_usd * 100),
        "new_price_cents": round(match.new_price_usd * 100),
        "price_delta_usd": match.price_delta_usd,
        "price_delta_pct": match.price_delta_pct,
        "changed_skus": match.changed_skus,
        "beyond_tolerance": match.beyond_tolerance,
        "run_id": str(run_id) if run_id else (str(result.run_id) if result.run_id else None),
    }
    return "update_pricebook_item", params


async def get_latest_result(principal: Principal) -> dict | None:
    async with tenant_session(principal.tenant_id) as session:
        return await runs.get_latest_result(session, agent=AGENT)


async def get_result_by_id(principal: Principal, run_id: uuid.UUID) -> dict | None:
    async with tenant_session(principal.tenant_id) as session:
        return await runs.get_result_by_id(session, run_id=run_id)


async def list_recent_runs(principal: Principal, *, limit: int = 20) -> list[dict]:
    async with tenant_session(principal.tenant_id) as session:
        return await runs.list_runs(session, agent=AGENT, limit=limit)
