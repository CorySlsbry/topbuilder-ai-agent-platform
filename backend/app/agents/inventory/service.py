"""Orchestration entry point for the Inventory & Supply Chain agent."""
from __future__ import annotations

import dataclasses
import uuid
from datetime import date, datetime, timezone
from time import perf_counter

from app.agents import _telemetry
from app.agents.inventory import reasoning
from app.agents.inventory.analytics import InventoryAnalysis
from app.agents.inventory.graph import INVENTORY_GRAPH
from app.agents.inventory.proration import (
    ConsumableProrationAnalysis,
    analyze_consumables,
)
from app.agents.inventory.schemas import (
    ConsumableProrationResult,
    InventoryRunResult,
    build_proration_result,
    build_result,
)
from app.config import get_settings
from app.db import tenant_session
from app.integrations.inventory.client import get_inventory_client
from app.integrations.providers.registry import display_name
from app.repositories import runs
from app.repositories import tenant_settings as tenant_settings_repo
from app.security import Principal

AGENT = "inventory"
HORIZON_DAYS = 14
# Coarse, situation-independent retrieval query. The high-value learned signal — CIPHER preferences
# distilled from past human edits — is general (e.g. "lead with the stockout exposure, not the SKU"),
# so a domain-anchored query surfaces it well; case win/loss recall is already agent-scoped. Keeps the
# graph pure (no DB session inside it): the service retrieves, the reason node only narrates.
_LESSON_QUERY = (
    "Inventory advisory narrative: critical reorders, days-to-stockout, stockout exposure, "
    "shrinkage alerts, unbilled materials, vendor arbitrage savings, recommended action."
)


def _situation_brief(analysis: InventoryAnalysis) -> str:
    """A numbers-light description of the SITUATION (drivers/counts) for case retrieval — never the
    authoritative figures (those live only in the deterministic engine, per ADR 0003)."""
    return (
        f"Inventory advisory run; {len(analysis.critical_reorders)} critical reorder(s); "
        f"{len(analysis.shrinkage_alerts)} shrinkage alert(s); "
        f"{len(analysis.unbilled_materials)} unbilled-material item(s); "
        f"{len(analysis.arbitrage)} vendor-arbitrage opportunity(ies)."
    )


def _recommendation_rows(analysis: InventoryAnalysis) -> list[dict]:
    rows: list[dict] = []
    for r in analysis.critical_reorders:
        rows.append({"kind": "reorder", "payload": dataclasses.asdict(r), "confidence": r.confidence, "economic_impact_cents": r.stockout_exposure_cents})
    for s in analysis.shrinkage_alerts:
        rows.append({"kind": "shrinkage", "payload": dataclasses.asdict(s), "confidence": s.confidence, "economic_impact_cents": s.shrinkage_value_cents})
    for u in analysis.unbilled_materials:
        rows.append({"kind": "unbilled", "payload": dataclasses.asdict(u), "confidence": None, "economic_impact_cents": u.unbilled_value_cents})
    for o in analysis.arbitrage:
        rows.append({"kind": "arbitrage", "payload": dataclasses.asdict(o), "confidence": None, "economic_impact_cents": o.annual_savings_cents})
    return rows


def _reasoning_rows(analysis: InventoryAnalysis, reasoning_source: str) -> list[tuple[str, str]]:
    rows = [
        (
            "analyze:summary",
            f"inputs_hash={analysis.inputs_hash}; reorders={len(analysis.critical_reorders)}; "
            f"shrinkage={len(analysis.shrinkage_alerts)}; unbilled={len(analysis.unbilled_materials)}; "
            f"arbitrage={len(analysis.arbitrage)}; reasoning_source={reasoning_source}",
        )
    ]
    rows += [(f"reorder:{r.sku}", r.reasoning) for r in analysis.critical_reorders]
    rows += [(f"shrinkage:{s.technician_id}:{s.sku}", s.reasoning) for s in analysis.shrinkage_alerts]
    rows += [(f"arbitrage:{o.sku}", o.reasoning) for o in analysis.arbitrage]
    return rows


async def run_inventory_analysis(
    principal: Principal, *, as_of: date | None = None, force: bool = False
) -> InventoryRunResult:
    settings = get_settings()
    as_of = as_of or date.today()
    client = get_inventory_client(as_of=as_of, settings=settings)
    started = perf_counter()

    # Self-learning READ: pull distilled lessons (preferences + past wins/losses) to steer the
    # NARRATION only (ADR-0003: never the figures). Isolated session + best-effort → '' on any error,
    # which is byte-identical to the pre-learning behavior.
    lessons = ""
    try:
        from app.learning import service as learning

        async with tenant_session(principal.tenant_id) as ls:
            lessons = await learning.retrieve_lessons(
                ls, agent=AGENT, query_text=_LESSON_QUERY, settings=settings
            )
    except Exception:
        lessons = ""

    # Provider resolution (best-effort): which field-service system this tenant runs on
    # (tenant_settings.fsm_provider). Steers NARRATION + the source_system metadata string only —
    # never a figure (ADR 0003). Any failure (missing table/row) -> the ServiceTitan flagship default.
    provider = "ServiceTitan"
    try:
        async with tenant_session(principal.tenant_id) as ps:
            provider = display_name(await tenant_settings_repo.get_fsm_provider(ps))
    except Exception:
        provider = "ServiceTitan"

    telemetry = _telemetry.start_collection()  # per-run narration cost (NULL on template path)
    try:
        state = await INVENTORY_GRAPH.ainvoke(
            {
                "as_of": as_of,
                "settings": settings,
                "client": client,
                "lessons": lessons,
                "provider": provider,
            }
        )
    except Exception as exc:
        duration_ms = int((perf_counter() - started) * 1000)
        async with tenant_session(principal.tenant_id) as session:
            failed_id = uuid.uuid4()
            await runs.create_run(
                session, run_id=failed_id, agent=AGENT, status="failed", horizon_days=HORIZON_DAYS,
                inputs_hash=None, created_by=principal.user_id, duration_ms=duration_ms,
                error=str(exc), result=None,
            )
            await runs.insert_audit(
                session, actor=str(principal.user_id), action="inventory.run.failed",
                target=str(failed_id), detail={"error": str(exc)},
            )
        raise

    analysis: InventoryAnalysis = state["analysis"]
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
                return InventoryRunResult.model_validate(existing)
        await runs.create_run(
            session, run_id=run_id, agent=AGENT, status="succeeded", horizon_days=HORIZON_DAYS,
            inputs_hash=analysis.inputs_hash, created_by=principal.user_id, duration_ms=duration_ms,
            result=result.model_dump(mode="json"), **telemetry.as_run_fields(),
        )
        await runs.add_recommendations(session, run_id=run_id, rows=_recommendation_rows(analysis))
        await runs.add_reasoning(session, run_id=run_id, rows=_reasoning_rows(analysis, reasoning_source))
        await runs.insert_audit(
            session, actor=str(principal.user_id), action="inventory.run", target=str(run_id),
            detail={"inputs_hash": analysis.inputs_hash, "reorders": len(analysis.critical_reorders),
                    "reasoning_source": reasoning_source},
        )

    # Self-learning: record this run as a CASE (outcome 'pending' until feedback labels it). Best-effort
    # + ISOLATED session so a learning failure can never roll back the run we just persisted above.
    try:
        from app.learning import service as learning

        async with tenant_session(principal.tenant_id) as ls:
            await learning.record_case(
                ls,
                agent=AGENT,
                run_id=run_id,
                problem_text=_situation_brief(analysis),
                recommendation_summary=(narrative or "")[:600],
                recommendation_kind="inventory_advisory",
                problem_features={
                    "reorders": len(analysis.critical_reorders),
                    "shrinkage": len(analysis.shrinkage_alerts),
                    "unbilled": len(analysis.unbilled_materials),
                    "arbitrage": len(analysis.arbitrage),
                },
                settings=settings,
            )
    except Exception:
        pass

    return result


PRORATION_AGENT = "inventory_proration"
_PRORATION_LESSON_QUERY = (
    "Inventory consumable proration narrative: spool/coil lot cost allocated across the jobs it served; "
    "per-job material cost; job-costing accuracy correction vs dumping the lot on one job."
)


def _proration_recommendation_rows(analysis: ConsumableProrationAnalysis) -> list[dict]:
    rows: list[dict] = []
    for lot in analysis.lots:
        rows.append(
            {
                "kind": "consumable_proration",
                "payload": {
                    "sku": lot.sku,
                    "name": lot.name,
                    "unit": lot.unit,
                    "method": lot.method,
                    "total_cost_cents": lot.total_cost_cents,
                    "dump_job_id": lot.dump_job_id,
                    "miscost_corrected_cents": lot.miscost_corrected_cents,
                    "allocations": [dataclasses.asdict(a) for a in lot.allocations],
                },
                "confidence": None,
                "economic_impact_cents": lot.miscost_corrected_cents,
            }
        )
    return rows


def _proration_reasoning_rows(analysis: ConsumableProrationAnalysis) -> list[tuple[str, str]]:
    rows = [
        (
            "proration:summary",
            f"inputs_hash={analysis.inputs_hash}; lots={len(analysis.lots)}; "
            f"prorated_cents={analysis.total_prorated_cents}; "
            f"miscost_corrected_cents={analysis.total_miscost_corrected_cents}",
        )
    ]
    rows += [(f"proration:{lot.sku}", lot.reasoning) for lot in analysis.lots]
    return rows


async def run_consumable_proration(
    principal: Principal, *, as_of: date | None = None, force: bool = False
) -> ConsumableProrationResult:
    """Prorate partially-consumed consumable lots (spools, copper coils) across the jobs they served,
    instead of dumping the whole lot cost on the single replenish job (Alex's pain). Advisory only —
    the deterministic engine computes; the narration layer only explains (ADR 0003)."""
    settings = get_settings()
    as_of = as_of or date.today()
    client = get_inventory_client(as_of=as_of, settings=settings)
    started = perf_counter()

    lot_inputs = await client.get_consumable_lots()
    analysis = analyze_consumables(lot_inputs, as_of=as_of)

    # Self-learning READ (best-effort, isolated, narration-only — ADR 0003 firewall).
    lessons = ""
    try:
        from app.learning import service as learning

        async with tenant_session(principal.tenant_id) as ls:
            lessons = await learning.retrieve_lessons(
                ls, agent=PRORATION_AGENT, query_text=_PRORATION_LESSON_QUERY, settings=settings
            )
    except Exception:
        lessons = ""

    provider = "ServiceTitan"
    try:
        async with tenant_session(principal.tenant_id) as ps:
            provider = display_name(await tenant_settings_repo.get_fsm_provider(ps))
    except Exception:
        provider = "ServiceTitan"

    telemetry = _telemetry.start_collection()  # proration narration is template-only -> NULL columns
    narrative = await reasoning.explain_proration(analysis, settings, lessons=lessons, provider=provider)
    duration_ms = int((perf_counter() - started) * 1000)
    run_id = uuid.uuid4()
    result = build_proration_result(
        analysis,
        narrative=narrative,
        analysis_timestamp=datetime.now(timezone.utc),
        run_id=run_id,
        source_system=provider,
    )

    async with tenant_session(principal.tenant_id) as session:
        if not force:
            existing = await runs.get_existing_result_by_hash(
                session, agent=PRORATION_AGENT, inputs_hash=analysis.inputs_hash
            )
            if existing is not None:
                return ConsumableProrationResult.model_validate(existing)
        await runs.create_run(
            session, run_id=run_id, agent=PRORATION_AGENT, status="succeeded",
            horizon_days=HORIZON_DAYS, inputs_hash=analysis.inputs_hash,
            created_by=principal.user_id, duration_ms=duration_ms,
            result=result.model_dump(mode="json"), **telemetry.as_run_fields(),
        )
        await runs.add_recommendations(
            session, run_id=run_id, rows=_proration_recommendation_rows(analysis)
        )
        await runs.add_reasoning(session, run_id=run_id, rows=_proration_reasoning_rows(analysis))
        await runs.insert_audit(
            session, actor=str(principal.user_id), action="inventory.proration.run",
            target=str(run_id),
            detail={"inputs_hash": analysis.inputs_hash, "lots": len(analysis.lots),
                    "miscost_corrected_cents": analysis.total_miscost_corrected_cents},
        )

    # Self-learning WRITE (best-effort, isolated).
    try:
        from app.learning import service as learning

        async with tenant_session(principal.tenant_id) as ls:
            await learning.record_case(
                ls,
                agent=PRORATION_AGENT,
                run_id=run_id,
                problem_text=(
                    f"Consumable proration run; {len(analysis.lots)} lot(s); "
                    f"${analysis.total_miscost_corrected_cents / 100:,.0f} job-costing error corrected."
                ),
                recommendation_summary=(narrative or "")[:600],
                recommendation_kind="consumable_proration",
                problem_features={"lots": len(analysis.lots)},
                settings=settings,
            )
    except Exception:
        pass

    return result


async def get_latest_proration_result(principal: Principal) -> dict | None:
    async with tenant_session(principal.tenant_id) as session:
        return await runs.get_latest_result(session, agent=PRORATION_AGENT)


async def get_latest_result(principal: Principal) -> dict | None:
    async with tenant_session(principal.tenant_id) as session:
        return await runs.get_latest_result(session, agent=AGENT)


async def get_result_by_id(principal: Principal, run_id: uuid.UUID) -> dict | None:
    async with tenant_session(principal.tenant_id) as session:
        return await runs.get_result_by_id(session, run_id=run_id)


async def list_recent_runs(principal: Principal, *, limit: int = 20) -> list[dict]:
    async with tenant_session(principal.tenant_id) as session:
        return await runs.list_runs(session, agent=AGENT, limit=limit)
