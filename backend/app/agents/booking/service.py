"""Orchestration entry point for the 24/7 Booking agent.

Runs the LangGraph agent (compute, no DB) then persists atomically inside a single tenant-scoped
transaction. Bookings are persisted as PROPOSED recommendations — never written back to ServiceTitan
(ADR 0006). Compute and persistence are separated so a compute failure is recorded in its own
transaction rather than rolled back with everything else.
"""
from __future__ import annotations

import dataclasses
import uuid
from datetime import date, datetime, time, timezone
from time import perf_counter

from app.agents import _telemetry
from app.agents.booking.analytics import BookingAnalysis
from app.agents.booking.graph import BOOKING_GRAPH
from app.agents.booking.schemas import BookingRunResult, build_result
from app.config import get_settings
from app.db import tenant_session
from app.integrations.booking_intake.client import get_booking_intake_client
from app.integrations.providers.registry import display_name
from app.repositories import runs
from app.repositories import tenant_settings as tenant_settings_repo
from app.security import Principal

AGENT = "booking"
# Booking is batch-of-intakes, not horizon-forecast; we record the intake lookback window in the
# shared `horizon_days` column for run bookkeeping.
LOOKBACK_DAYS = 7
# Coarse, situation-independent retrieval query. The high-value learned signal — CIPHER preferences
# distilled from past human edits — is general (e.g. "lead with the after-hours recovery, then the
# emergency queue"), so a domain-anchored query surfaces it well; case win/loss recall is already
# agent-scoped. Keeps the graph pure (no DB session inside it): the service retrieves, the reason node
# only narrates.
_LESSON_QUERY = (
    "Booking advisory narrative: inbound intake qualification, proposed bookings, after-hours "
    "revenue recovery, emergency queue, needs-a-dispatcher handoffs, recommended action."
)
# A representative after-hours wall-clock for the demo: stable within a day so idempotency dedups
# same-day reruns (qualification/value never depend on the clock — `after_hours` is per-intake).
DEMO_HOUR = 19


def _default_as_of() -> datetime:
    return datetime.combine(date.today(), time(hour=DEMO_HOUR))


def _recommendation_rows(analysis: BookingAnalysis) -> list[dict]:
    rows: list[dict] = []
    for b in analysis.proposed_bookings:
        rows.append(
            {
                "kind": "proposed_booking",
                "payload": dataclasses.asdict(b),
                "confidence": b.confidence,
                "economic_impact_cents": b.estimated_value_cents,
            }
        )
    for u in analysis.unbooked:
        rows.append(
            {
                "kind": "unbooked",
                "payload": dataclasses.asdict(u),
                "confidence": None,
                "economic_impact_cents": None,
            }
        )
    return rows


def _reasoning_rows(analysis: BookingAnalysis, reasoning_source: str) -> list[tuple[str, str]]:
    rows = [
        (
            "analyze:summary",
            f"inputs_hash={analysis.inputs_hash}; intakes={analysis.totals.intakes_received}; "
            f"qualified={analysis.totals.qualified}; proposed={analysis.totals.proposed_bookings}; "
            f"after_hours_captured={analysis.totals.after_hours_captured}; "
            f"reasoning_source={reasoning_source}",
        )
    ]
    rows += [(f"booking:{b.intake_id}", b.reasoning) for b in analysis.proposed_bookings]
    rows += [(f"unbooked:{u.intake_id}", u.reason) for u in analysis.unbooked]
    return rows


def _situation_brief(analysis: BookingAnalysis) -> str:
    """A numbers-light description of the SITUATION (drivers/counts) for case retrieval — never the
    authoritative figures (those live only in the deterministic engine, per ADR 0006)."""
    t = analysis.totals
    no_slot = sum(1 for u in analysis.unbooked if "availability" in u.reason.lower())
    return (
        f"Booking advisory run; {t.intakes_received} inbound intake(s), {t.qualified} qualified, "
        f"{t.proposed_bookings} proposed booking(s) ({t.after_hours_captured} after-hours); "
        f"{no_slot} qualified intake(s) needing a dispatcher (no open slot)."
    )


async def run_booking_analysis(
    principal: Principal, *, as_of: datetime | None = None, force: bool = False
) -> BookingRunResult:
    settings = get_settings()
    as_of = as_of or _default_as_of()
    client = get_booking_intake_client(as_of=as_of, settings=settings)
    started = perf_counter()

    # Self-learning READ: pull distilled lessons (preferences + past wins/losses) to steer the
    # NARRATION only (ADR-0006/0003: never the figures). Isolated session + best-effort → '' on any
    # error, which is byte-identical to the pre-learning behavior.
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

    # Per-run LLM telemetry (narration cost; NULL on the template path). See _telemetry.
    telemetry = _telemetry.start_collection()
    try:
        state = await BOOKING_GRAPH.ainvoke(
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
                session, run_id=failed_id, agent=AGENT, status="failed", horizon_days=LOOKBACK_DAYS,
                inputs_hash=None, created_by=principal.user_id, duration_ms=duration_ms,
                error=str(exc), result=None,
            )
            await runs.insert_audit(
                session, actor=str(principal.user_id), action="booking.run.failed",
                target=str(failed_id), detail={"error": str(exc)},
            )
        raise

    analysis: BookingAnalysis = state["analysis"]
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
                return BookingRunResult.model_validate(existing)
        await runs.create_run(
            session, run_id=run_id, agent=AGENT, status="succeeded", horizon_days=LOOKBACK_DAYS,
            inputs_hash=analysis.inputs_hash, created_by=principal.user_id, duration_ms=duration_ms,
            result=result.model_dump(mode="json"), **telemetry.as_run_fields(),
        )
        await runs.add_recommendations(session, run_id=run_id, rows=_recommendation_rows(analysis))
        await runs.add_reasoning(session, run_id=run_id, rows=_reasoning_rows(analysis, reasoning_source))
        await runs.insert_audit(
            session, actor=str(principal.user_id), action="booking.run", target=str(run_id),
            detail={
                "inputs_hash": analysis.inputs_hash,
                "intakes": analysis.totals.intakes_received,
                "proposed_bookings": analysis.totals.proposed_bookings,
                "reasoning_source": reasoning_source,
            },
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
                recommendation_kind="booking_advisory",
                problem_features={
                    "intakes": analysis.totals.intakes_received,
                    "qualified": analysis.totals.qualified,
                    "proposed_bookings": analysis.totals.proposed_bookings,
                    "after_hours_captured": analysis.totals.after_hours_captured,
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
