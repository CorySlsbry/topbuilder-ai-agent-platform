"""Orchestration entry point for the Email agent."""
from __future__ import annotations

import dataclasses
import uuid
from datetime import date, datetime, timezone
from time import perf_counter

from app.agents import _telemetry
from app.agents.email.analytics import EmailAnalysis
from app.agents.email.graph import EMAIL_GRAPH
from app.agents.email.schemas import AppliedRewriteOut, EmailRunResult, build_result
from app.config import get_settings
from app.db import tenant_session
from app.integrations.email_inbox.client import get_email_inbox_client
from app.integrations.providers.registry import display_name
from app.repositories import runs
from app.repositories import tenant_settings as tenant_settings_repo
from app.security import Principal

AGENT = "email"
HORIZON_DAYS = 1
# Coarse, situation-independent retrieval query. The high-value learned signal — CIPHER preferences
# distilled from past human edits — is general (e.g. "shorter reply drafts, lead with the date"), so a
# domain-anchored query surfaces it well; case win/loss recall is already agent-scoped. Keeps the
# graph pure (no DB session inside it): the service retrieves, the reason node only narrates.
_LESSON_QUERY = (
    "Email operations briefing: inbox triage, reply drafts awaiting human review, trash cleanup, "
    "underperforming automated email workflow vs benchmark, proposed sequence rewrite."
)


def apply_overrides_to_result_dict(result: dict, overrides: list[dict]) -> dict:
    """Pure overlay of operator-applied workflow copy onto a run-result dict. Persisted run JSON
    stays the pure engine output; this overlays at READ time (latest + the idempotent same-inputs
    early return) so the dashboard always reflects the CURRENT override."""
    if not overrides or not isinstance(result.get("workflows"), list):
        return result
    by_id = {o["workflow_id"]: o for o in overrides}
    for w in result["workflows"]:
        o = by_id.get(str(w.get("workflow_id")))
        if o is not None:
            w["applied_rewrite"] = {
                "subject": o["subject"], "preview": o["preview"],
                "applied_by": o["updated_by"], "applied_at": str(o["updated_at"]),
            }
    return result


def _recommendation_rows(analysis: EmailAnalysis) -> list[dict]:
    rows: list[dict] = []
    for p in analysis.top_priorities:
        rows.append({"kind": "priority_email", "payload": dataclasses.asdict(p),
                     "confidence": None, "economic_impact_cents": p.value_cents})
    for d in analysis.reply_drafts:
        rows.append({"kind": "reply_draft", "payload": dataclasses.asdict(d),
                     "confidence": d.confidence, "economic_impact_cents": None})
    for t in analysis.trash_queue:
        rows.append({"kind": "trash_candidate", "payload": dataclasses.asdict(t),
                     "confidence": t.confidence, "economic_impact_cents": None})
    for w in analysis.workflows:
        if w.proposed_rewrite is not None:
            rows.append({"kind": "workflow_rewrite", "payload": dataclasses.asdict(w),
                         "confidence": None, "economic_impact_cents": None})
    return rows


def _reasoning_rows(analysis: EmailAnalysis, reasoning_source: str) -> list[tuple[str, str]]:
    t = analysis.totals
    rows = [
        (
            "analyze:summary",
            f"inputs_hash={analysis.inputs_hash}; unread={t.unread_total}; "
            f"needs_reply={t.needs_reply}; fyi={t.fyi}; trash={t.trash_candidates}; "
            f"workflow_reports={t.workflow_reports}; reasoning_source={reasoning_source}",
        )
    ]
    rows += [(f"priority:{p.email_id}", f"score {p.priority_score}: {p.reason}") for p in analysis.top_priorities]
    rows += [
        (f"draft:{d.email_id}", f"requires_human={d.requires_human} conf={d.confidence}")
        for d in analysis.reply_drafts
    ]
    rows += [(f"trash:{i.email_id}", f"{i.category} conf={i.confidence}") for i in analysis.trash_queue]
    rows += [
        (
            f"workflow:{w.workflow_id}",
            f"{w.name}: open {w.open_rate} vs {w.benchmark_open_rate}, reply {w.reply_rate} vs "
            f"{w.benchmark_reply_rate} -> {w.status}",
        )
        for w in analysis.workflows
    ]
    return rows


def _situation_brief(analysis: EmailAnalysis) -> str:
    """A numbers-light description of the SITUATION (drivers/counts) for case retrieval — never the
    authoritative figures (those live only in the deterministic engine, per ADR 0003)."""
    t = analysis.totals
    under = sum(1 for w in analysis.workflows if w.status == "underperforming")
    held = sum(1 for d in analysis.reply_drafts if d.requires_human)
    return (
        f"Email triage run; {t.unread_total} unread; {t.needs_reply} need a reply "
        f"({held} held for a human); {t.trash_candidates} trash candidate(s); "
        f"{under} underperforming workflow(s)."
    )


async def _propose_actions(
    principal: Principal, run_id: uuid.UUID, analysis: EmailAnalysis, result: EmailRunResult
) -> None:
    """Best-effort: route the agent's writes through the action gate (ADR 0007), mirroring how the
    field-ops quote proposes `create_estimate`. A proposal failure (kind not registered yet, actions
    disabled, DB hiccup) must NEVER break the run — each proposal is independently swallowed."""
    try:
        from app.actions import service as actions_service
        from app.actions.schemas import ProposeActionIn
    except Exception:
        return

    async def _propose(kind: str, params: dict) -> None:
        try:
            await actions_service.propose_action(
                principal, ProposeActionIn(agent=AGENT, kind=kind, params=params, run_id=run_id)
            )
        except Exception:
            pass

    if result.trash_queue:
        await _propose(
            "delete_emails",
            {
                "email_ids": [t.email_id for t in result.trash_queue],
                "subjects": [t.subject for t in result.trash_queue],
            },
        )

    address_by_id = {d.email_id: d.from_address for d in analysis.reply_drafts}
    for draft in result.reply_drafts:  # the FINAL (possibly polished) wording the human reviewed
        if draft.requires_human:
            continue
        await _propose(
            "send_email_reply",
            {
                "email_id": draft.email_id,
                "to_name": draft.from_name,
                "to_address": address_by_id.get(draft.email_id, ""),
                "draft_subject": draft.draft_subject,
                "draft_body": draft.draft_body,
            },
        )

    for w in result.workflows:
        if w.status == "underperforming" and w.proposed_rewrite is not None:
            await _propose(
                "rewrite_workflow",
                {
                    "workflow_id": w.workflow_id,
                    "name": w.name,
                    "subject": w.proposed_rewrite.subject,
                    "preview": w.proposed_rewrite.preview,
                    "rationale": w.proposed_rewrite.rationale,
                },
            )


async def run_email_analysis(
    principal: Principal, *, as_of: date | None = None, force: bool = False
) -> EmailRunResult:
    settings = get_settings()
    as_of = as_of or date.today()
    client = get_email_inbox_client(as_of=as_of, settings=settings)
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

    telemetry = _telemetry.start_collection()  # narration + draft-polish cost (NULL on template path)
    try:
        state = await EMAIL_GRAPH.ainvoke(
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
                session, actor=str(principal.user_id), action="email.run.failed",
                target=str(failed_id), detail={"error": str(exc)},
            )
        raise

    analysis: EmailAnalysis = state["analysis"]
    narrative: str = state["narrative"]
    polished: dict = state.get("polished") or {}
    reasoning_source: str = state.get("reasoning_source", "template")
    duration_ms = int((perf_counter() - started) * 1000)
    run_id = uuid.uuid4()
    result = build_result(
        analysis, narrative=narrative, analysis_timestamp=datetime.now(timezone.utc),
        run_id=run_id, polished=polished, source_system=provider,
    )

    # Operator-applied workflow copy (via the assistant's update_email_workflow tool) overlays what
    # we RETURN so the dashboard shows what is actually running — the persisted run JSON stays the
    # pure engine output. Best-effort + isolated session; figures untouched (ADR 0003).
    overrides: list[dict] = []
    try:
        from app.repositories import assistant as assistant_repo

        async with tenant_session(principal.tenant_id) as ovs:
            overrides = await assistant_repo.list_email_overrides(ovs)
    except Exception:
        overrides = []

    async with tenant_session(principal.tenant_id) as session:
        if not force:
            existing = await runs.get_existing_result_by_hash(
                session, agent=AGENT, inputs_hash=analysis.inputs_hash
            )
            if existing is not None:
                merged = apply_overrides_to_result_dict(existing, overrides)
                return EmailRunResult.model_validate(merged)
        await runs.create_run(
            session, run_id=run_id, agent=AGENT, status="succeeded", horizon_days=HORIZON_DAYS,
            inputs_hash=analysis.inputs_hash, created_by=principal.user_id, duration_ms=duration_ms,
            result=result.model_dump(mode="json"), **telemetry.as_run_fields(),
        )
        await runs.add_recommendations(session, run_id=run_id, rows=_recommendation_rows(analysis))
        await runs.add_reasoning(session, run_id=run_id, rows=_reasoning_rows(analysis, reasoning_source))
        await runs.insert_audit(
            session, actor=str(principal.user_id), action="email.run", target=str(run_id),
            detail={"inputs_hash": analysis.inputs_hash, "unread": analysis.totals.unread_total,
                    "needs_reply": analysis.totals.needs_reply, "reasoning_source": reasoning_source},
        )

    # Read-time overlay on the returned copy only (the run above was persisted pure).
    if overrides:
        by_id = {o["workflow_id"]: o for o in overrides}
        for w in result.workflows:
            o = by_id.get(w.workflow_id)
            if o is not None:
                w.applied_rewrite = AppliedRewriteOut(
                    subject=o["subject"], preview=o["preview"],
                    applied_by=o["updated_by"], applied_at=str(o["updated_at"]),
                )

    # Best-effort: propose the writes (delete trash / send ready replies / rewrite the underperforming
    # workflow) through the action gate AFTER the run is persisted. Failures are swallowed per call.
    try:
        await _propose_actions(principal, run_id, analysis, result)
    except Exception:
        pass

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
                recommendation_kind="email_advisory",
                problem_features={
                    "unread": analysis.totals.unread_total,
                    "needs_reply": analysis.totals.needs_reply,
                    "trash": analysis.totals.trash_candidates,
                    "underperforming": sum(
                        1 for w in analysis.workflows if w.status == "underperforming"
                    ),
                },
                settings=settings,
            )
    except Exception:
        pass

    return result


async def get_latest_result(principal: Principal) -> dict | None:
    async with tenant_session(principal.tenant_id) as session:
        result = await runs.get_latest_result(session, agent=AGENT)
        if result is not None:
            try:
                from app.repositories import assistant as assistant_repo

                result = apply_overrides_to_result_dict(
                    result, await assistant_repo.list_email_overrides(session)
                )
            except Exception:
                pass
        return result


async def get_result_by_id(principal: Principal, run_id: uuid.UUID) -> dict | None:
    async with tenant_session(principal.tenant_id) as session:
        return await runs.get_result_by_id(session, run_id=run_id)


async def list_recent_runs(principal: Principal, *, limit: int = 20) -> list[dict]:
    async with tenant_session(principal.tenant_id) as session:
        return await runs.list_runs(session, agent=AGENT, limit=limit)
