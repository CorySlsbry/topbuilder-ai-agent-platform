"""Orchestration entry point for the Documents agent."""
from __future__ import annotations

import dataclasses
import uuid
from datetime import date, datetime, timezone
from time import perf_counter

from app.agents import _telemetry
from app.agents.documents.analytics import DocumentsAnalysis
from app.agents.documents.ap import ApAnalysis
from app.agents.documents.graph import DOCUMENTS_GRAPH
from app.agents.documents.schemas import DocumentsRunResult, build_result
from app.agents.documents.warranty import WarrantyAnalysis
from app.config import get_settings
from app.db import tenant_session
from app.integrations.documents.client import get_documents_client
from app.integrations.providers.registry import display_name
from app.repositories import runs
from app.repositories import tenant_settings as tenant_settings_repo
from app.security import Principal

AGENT = "documents"
HORIZON_DAYS = 1
# Coarse, situation-independent retrieval query. The high-value learned signal — CIPHER preferences
# distilled from past human edits — is general (e.g. "lead with the compliance risk, not the count"),
# so a domain-anchored query surfaces it well; case win/loss recall is already agent-scoped. Keeps the
# graph pure (no DB session inside it): the service retrieves, the reason node only narrates.
_LESSON_QUERY = (
    "Documents advisory brief: document classification + filing, e-signature routing, expiring "
    "insurance COIs, needs-a-human exceptions, recommended action."
)


def _recommendation_rows(
    analysis: DocumentsAnalysis, ap_analysis: ApAnalysis, warranty_analysis: WarrantyAnalysis
) -> list[dict]:
    rows: list[dict] = []
    for f in analysis.filings:
        rows.append({"kind": "document_filing", "payload": dataclasses.asdict(f),
                     "confidence": f.confidence, "economic_impact_cents": f.amount_cents})
    for u in analysis.needs_human:
        rows.append({"kind": "document_needs_human", "payload": dataclasses.asdict(u),
                     "confidence": None, "economic_impact_cents": None})
    # PO/AP-from-email lane (A6): auto-proposed A/P drafts + the bills that need a human.
    for d in ap_analysis.drafts:
        rows.append({"kind": "ap_draft", "payload": dataclasses.asdict(d),
                     "confidence": d.confidence, "economic_impact_cents": d.amount_cents})
    for b in ap_analysis.needs_human:
        rows.append({"kind": "ap_needs_human", "payload": dataclasses.asdict(b),
                     "confidence": None, "economic_impact_cents": b.amount_cents})
    # Warranty-registration lane (A10): ready packets + equipment that needs a human.
    for pkt in warranty_analysis.packets:
        rows.append({"kind": "warranty_packet", "payload": dataclasses.asdict(pkt),
                     "confidence": pkt.confidence, "economic_impact_cents": None})
    for ex in warranty_analysis.needs_human:
        rows.append({"kind": "warranty_needs_human", "payload": dataclasses.asdict(ex),
                     "confidence": None, "economic_impact_cents": None})
    return rows


def _reasoning_rows(
    analysis: DocumentsAnalysis, ap_analysis: ApAnalysis, warranty_analysis: WarrantyAnalysis,
    reasoning_source: str,
) -> list[tuple[str, str]]:
    rows = [
        (
            "analyze:summary",
            f"inputs_hash={analysis.inputs_hash}; processed={analysis.totals.documents_processed}; "
            f"auto_filed={analysis.totals.auto_filed}; needs_signature={analysis.totals.needs_signature}; "
            f"needs_human={analysis.totals.needs_human}; "
            f"ap_auto={ap_analysis.totals.auto_proposed}; ap_needs_human={ap_analysis.totals.needs_human}; "
            f"warranty_packets={warranty_analysis.totals.packets_ready}; "
            f"warranty_needs_human={warranty_analysis.totals.needs_human}; "
            f"reasoning_source={reasoning_source}",
        )
    ]
    rows += [(f"filing:{f.doc_id}", f.reasoning) for f in analysis.filings]
    rows += [(f"needs_human:{u.doc_id}", u.reason) for u in analysis.needs_human]
    rows += [(f"ap_draft:{d.bill_id}", d.reasoning) for d in ap_analysis.drafts]
    rows += [(f"ap_needs_human:{b.bill_id}", b.reason) for b in ap_analysis.needs_human]
    rows += [(f"warranty_packet:{p.equipment_id}", p.reasoning) for p in warranty_analysis.packets]
    rows += [(f"warranty_needs_human:{x.equipment_id}", x.reason) for x in warranty_analysis.needs_human]
    return rows


def _situation_brief(analysis: DocumentsAnalysis) -> str:
    """A numbers-light description of the SITUATION (drivers/counts) for case retrieval — never the
    authoritative figures (those live only in the deterministic engine, per ADR 0003)."""
    t = analysis.totals
    return (
        f"Documents advisory run; {t.documents_processed} document(s) processed; "
        f"{t.auto_filed} auto-filed; {t.needs_signature} need an e-signature; "
        f"{t.expiring_soon} expiring COI(s); {t.needs_human} needs-a-human exception(s)."
    )


async def run_documents_analysis(
    principal: Principal, *, as_of: date | None = None, force: bool = False
) -> DocumentsRunResult:
    settings = get_settings()
    as_of = as_of or date.today()
    client = get_documents_client(as_of=as_of, settings=settings)
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
        state = await DOCUMENTS_GRAPH.ainvoke(
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
                session, actor=str(principal.user_id), action="documents.run.failed",
                target=str(failed_id), detail={"error": str(exc)},
            )
        raise

    analysis: DocumentsAnalysis = state["analysis"]
    ap_analysis: ApAnalysis = state["ap_analysis"]
    warranty_analysis: WarrantyAnalysis = state["warranty_analysis"]
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
        ap_analysis=ap_analysis,
        warranty_analysis=warranty_analysis,
    )

    async with tenant_session(principal.tenant_id) as session:
        if not force:
            existing = await runs.get_existing_result_by_hash(
                session, agent=AGENT, inputs_hash=analysis.inputs_hash
            )
            if existing is not None:
                return DocumentsRunResult.model_validate(existing)
        await runs.create_run(
            session, run_id=run_id, agent=AGENT, status="succeeded", horizon_days=HORIZON_DAYS,
            inputs_hash=analysis.inputs_hash, created_by=principal.user_id, duration_ms=duration_ms,
            result=result.model_dump(mode="json"), **telemetry.as_run_fields(),
        )
        await runs.add_recommendations(
            session, run_id=run_id,
            rows=_recommendation_rows(analysis, ap_analysis, warranty_analysis),
        )
        await runs.add_reasoning(
            session, run_id=run_id,
            rows=_reasoning_rows(analysis, ap_analysis, warranty_analysis, reasoning_source),
        )
        await runs.insert_audit(
            session, actor=str(principal.user_id), action="documents.run", target=str(run_id),
            detail={"inputs_hash": analysis.inputs_hash, "processed": analysis.totals.documents_processed,
                    "auto_filed": analysis.totals.auto_filed, "reasoning_source": reasoning_source},
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
                recommendation_kind="documents_advisory",
                problem_features={
                    "processed": analysis.totals.documents_processed,
                    "auto_filed": analysis.totals.auto_filed,
                    "needs_human": analysis.totals.needs_human,
                },
                settings=settings,
            )
    except Exception:
        pass

    return result


async def get_latest_result(principal: Principal) -> dict | None:
    async with tenant_session(principal.tenant_id) as session:
        return await runs.get_latest_result(session, agent=AGENT)


async def get_result_by_id(principal: Principal, run_id: uuid.UUID) -> dict | None:
    async with tenant_session(principal.tenant_id) as session:
        return await runs.get_result_by_id(session, run_id=run_id)


async def list_recent_runs(principal: Principal, *, limit: int = 20) -> list[dict]:
    async with tenant_session(principal.tenant_id) as session:
        return await runs.list_runs(session, agent=AGENT, limit=limit)
