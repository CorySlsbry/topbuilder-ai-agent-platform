"""Orchestration entry point for the A/R Collections agent.

Runs the LangGraph agent (compute, no DB) then persists atomically inside a single tenant-scoped
transaction — the same shape as ``booking/service.py``. Worklist rows are persisted as advisory
recommendations; nothing is written to the customer's books here. Sending a dunning step goes through
the human-approved action gate (ADR 0007). Compute and persistence are separated so a compute failure
is recorded in its own transaction rather than rolled back with everything else.
"""
from __future__ import annotations

import dataclasses
import uuid
from datetime import date, datetime, timezone
from time import perf_counter

from app.agents.collections.analytics import (
    CHANNEL_NONE,
    STATUS_RECONCILED,
    CollectionsAnalysis,
)
from app.agents import _telemetry
from app.agents.collections.graph import COLLECTIONS_GRAPH
from app.agents.collections.schemas import CollectionsRunResult, build_result
from app.config import get_settings
from app.db import tenant_session
from app.integrations.collections.client import get_collections_client
from app.repositories import runs
from app.security import Principal

AGENT = "collections"
# Collections is an as-of A/R snapshot, not a forecast horizon; we record the lookback window in the
# shared `horizon_days` column for run bookkeeping (idempotency keys off `inputs_hash`).
LOOKBACK_DAYS = 0
# Coarse, situation-independent retrieval query (the high-value learned signal — CIPHER preferences
# distilled from past human edits — is general). The graph stays pure: the service retrieves, the
# narration layer only narrates.
_LESSON_QUERY = (
    "A/R collections advisory narrative: aging buckets, overdue balance, dunning email/SMS/call "
    "escalation, promise-to-pay, write-off / send-to-collections, prioritized worklist by age."
)


def _recommendation_rows(analysis: CollectionsAnalysis) -> list[dict]:
    """One advisory recommendation per customer worklist row. Economic impact = the open balance."""
    return [
        {
            "kind": "collections_worklist",
            "payload": dataclasses.asdict(c),
            "confidence": None,
            "economic_impact_cents": c.balance_cents,
        }
        for c in analysis.worklist
    ]


def _reasoning_rows(analysis: CollectionsAnalysis, reasoning_source: str) -> list[tuple[str, str]]:
    t = analysis.totals
    rows: list[tuple[str, str]] = [
        (
            "analyze:summary",
            f"inputs_hash={analysis.inputs_hash}; customers={t.customers}; "
            f"open_balance_cents={t.open_balance_cents}; overdue_cents={t.overdue_balance_cents}; "
            f"at_risk_cents={t.at_risk_balance_cents}; needing_action={t.customers_needing_action}; "
            f"reasoning_source={reasoning_source}",
        )
    ]
    rows += [(f"worklist:{c.customer_id}", c.next_action) for c in analysis.worklist]
    return rows


def _situation_brief(analysis: CollectionsAnalysis) -> str:
    """A numbers-light description of the SITUATION for case retrieval — never the authoritative
    figures (those live only in the deterministic engine, per ADR 0003)."""
    t = analysis.totals
    return (
        f"A/R collections advisory run; {t.customers} customer(s) with open A/R, "
        f"{t.customers_needing_action} needing outbound dunning; aged buckets across "
        f"current..121+ with a 91+ at-risk tail."
    )


async def run_collections_analysis(
    principal: Principal, *, as_of: date | None = None, force: bool = False
) -> CollectionsRunResult:
    settings = get_settings()
    as_of = as_of or date.today()
    client = get_collections_client(as_of=as_of, settings=settings)
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

    # A/R is reconciled in QuickBooks (book of record); the source_system metadata reflects that.
    provider = "QuickBooks"

    telemetry = _telemetry.start_collection()  # per-run narration cost (NULL on template path)
    try:
        state = await COLLECTIONS_GRAPH.ainvoke(
            {"as_of": as_of, "settings": settings, "client": client, "lessons": lessons, "provider": provider}
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
                session, actor=str(principal.user_id), action="collections.run.failed",
                target=str(failed_id), detail={"error": str(exc)},
            )
        raise

    analysis: CollectionsAnalysis = state["analysis"]
    narrative: str = state["narrative"]
    reasoning_source: str = state.get("reasoning_source", "template")
    duration_ms = int((perf_counter() - started) * 1000)
    run_id = uuid.uuid4()
    result = build_result(
        analysis,
        narrative=narrative,
        analysis_timestamp=datetime.now(timezone.utc),
        run_id=run_id,
        source_system=provider,
    )

    async with tenant_session(principal.tenant_id) as session:
        if not force:
            existing = await runs.get_existing_result_by_hash(
                session, agent=AGENT, inputs_hash=analysis.inputs_hash
            )
            if existing is not None:
                return CollectionsRunResult.model_validate(existing)
        await runs.create_run(
            session, run_id=run_id, agent=AGENT, status="succeeded", horizon_days=LOOKBACK_DAYS,
            inputs_hash=analysis.inputs_hash, created_by=principal.user_id, duration_ms=duration_ms,
            result=result.model_dump(mode="json"), **telemetry.as_run_fields(),
        )
        await runs.add_recommendations(session, run_id=run_id, rows=_recommendation_rows(analysis))
        await runs.add_reasoning(session, run_id=run_id, rows=_reasoning_rows(analysis, reasoning_source))
        await runs.insert_audit(
            session, actor=str(principal.user_id), action="collections.run", target=str(run_id),
            detail={
                "inputs_hash": analysis.inputs_hash,
                "customers": analysis.totals.customers,
                "overdue_balance_cents": analysis.totals.overdue_balance_cents,
                "needing_action": analysis.totals.customers_needing_action,
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
                recommendation_kind="collections_advisory",
                problem_features={
                    "customers": analysis.totals.customers,
                    "needing_action": analysis.totals.customers_needing_action,
                },
                settings=settings,
            )
    except Exception:
        pass

    return result


# --------------------------------------------------------------------------------------------
# Action-gate param assembly (server-side) for the gated "send a dunning step" endpoint.
# --------------------------------------------------------------------------------------------
_KIND_BY_CHANNEL = {
    "email": "send_dunning_email",
    "sms": "send_dunning_sms",
    "call": "place_dunning_call",
}


def proposed_dunning_params(
    result: CollectionsRunResult, customer_id: str, *, run_id: uuid.UUID | None = None
) -> tuple[str, dict]:
    """Build the (kind, params) for a dunning action for a worklist customer, assembled server-side.

    Pure helper (tested): finds the customer in the persisted run, refuses one who is current /
    reconciled or has no reachable channel, and packages the engine-computed balance/age/step + the
    ready-to-send draft so a caller can never inject a dunning send for a customer who doesn't owe.
    Returns the action `kind` keyed to the engine's compliance-gated channel.
    """
    match = next((c for c in result.worklist if c.customer_id == customer_id), None)
    if match is None:
        raise ValueError(f"customer '{customer_id}' is not in this collections run")
    if match.status == STATUS_RECONCILED or match.oldest_days_overdue <= 0:
        raise ValueError(f"customer '{customer_id}' is current/reconciled — nothing to collect")
    if match.dunning_channel == CHANNEL_NONE or match.dunning_step == 0:
        raise ValueError(
            f"customer '{customer_id}' has no compliant outreach channel — assign a human / mail a statement"
        )
    kind = _KIND_BY_CHANNEL[match.dunning_channel]
    drafts = match.drafts
    params = {
        "customer_id": match.customer_id,
        "customer_name": match.customer_name,
        "channel": match.dunning_channel,
        "dunning_step": match.dunning_step,
        "balance_usd": match.balance_usd,
        "days_overdue": match.oldest_days_overdue,
        "bucket": match.bucket,
        "email_subject": drafts.email_subject,
        "email_body": drafts.email_body,
        "sms_body": drafts.sms_body,
        "call_script": drafts.call_script,
        "run_id": str(run_id) if run_id else (str(result.run_id) if result.run_id else None),
    }
    return kind, params


async def get_latest_result(principal: Principal) -> dict | None:
    async with tenant_session(principal.tenant_id) as session:
        return await runs.get_latest_result(session, agent=AGENT)


async def get_result_by_id(principal: Principal, run_id: uuid.UUID) -> dict | None:
    async with tenant_session(principal.tenant_id) as session:
        return await runs.get_result_by_id(session, run_id=run_id)


async def list_recent_runs(principal: Principal, *, limit: int = 20) -> list[dict]:
    async with tenant_session(principal.tenant_id) as session:
        return await runs.list_runs(session, agent=AGENT, limit=limit)
