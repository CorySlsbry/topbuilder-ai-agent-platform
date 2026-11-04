"""Orchestration entry point for the SEO/GEO Marketing agent.

Weekly cadence: analyze competitors, audit pages against the 2026 GEO benchmarks, rank long-tail
blog opportunities mined from Reddit/YouTube/search, and queue owner-voice drafts. Everything is
advisory: drafts become `publish_blog_post` / `post_comment` PROPOSALS through the human-approved
action gate (ADR 0007) — nothing is ever published by this agent.
"""
from __future__ import annotations

import dataclasses
import uuid
from datetime import date, datetime, timezone
from time import perf_counter

from app.agents import _telemetry
from app.agents.seo import analytics
from app.agents.seo.analytics import SeoAnalysis
from app.agents.seo.graph import SEO_GRAPH
from app.agents.seo.schemas import SeoRunResult, build_result
from app.config import get_settings
from app.db import tenant_session
from app.integrations.providers.registry import display_name
from app.integrations.seo_intel.client import get_seo_intel_client
from app.repositories import runs
from app.repositories import tenant_settings as tenant_settings_repo
from app.security import Principal

AGENT = "seo"
HORIZON_DAYS = 7  # weekly review cadence, recorded in the shared horizon_days run column
# Coarse, situation-independent retrieval query. The high-value learned signal — CIPHER preferences
# distilled from past human edits — is general (e.g. "lead with the competitor gap, not the page
# scores"), so a domain-anchored query surfaces it well; case win/loss recall is already
# agent-scoped. Keeps the graph pure (no DB session inside it): the service retrieves, the reason
# node only narrates.
_LESSON_QUERY = (
    "SEO/GEO advisory narrative: competitor keyword gaps, AI-citation share, GEO page audit "
    "fixes, long-tail blog opportunities from Reddit and YouTube, owner-voice comment drafts, "
    "recommended action."
)


def _situation_brief(analysis: SeoAnalysis) -> str:
    """A numbers-light description of the SITUATION (drivers/counts) for case retrieval — never the
    authoritative figures (those live only in the deterministic engine, per ADR 0003)."""
    s = analysis.weekly_summary
    return (
        f"SEO/GEO advisory run; {len(analysis.competitor_gaps)} competitor(s) tracked with "
        f"{s.gaps_found} keyword gap(s); {s.pages_below_benchmark} page(s) below the GEO "
        f"benchmarks; {len(analysis.blog_opportunities)} blog opportunit(ies) "
        f"({s.posts_planned} planned); {s.comments_drafted} comment draft(s)."
    )


def _recommendation_rows(analysis: SeoAnalysis) -> list[dict]:
    rows: list[dict] = []
    for g in analysis.competitor_gaps:
        rows.append(
            {"kind": "competitor_gap", "payload": dataclasses.asdict(g), "confidence": None,
             "economic_impact_cents": None}
        )
    for p in analysis.geo_audit:
        rows.append(
            {"kind": "geo_page_audit", "payload": dataclasses.asdict(p),
             "confidence": round(p.score / 100, 3), "economic_impact_cents": None}
        )
    for b in analysis.blog_opportunities:
        rows.append(
            {"kind": "blog_opportunity", "payload": dataclasses.asdict(b), "confidence": None,
             "economic_impact_cents": None}
        )
    for c in analysis.comment_opportunities:
        rows.append(
            {"kind": "comment_opportunity", "payload": dataclasses.asdict(c),
             "confidence": round(c.relevance_score / 100, 3), "economic_impact_cents": None}
        )
    return rows


def _reasoning_rows(analysis: SeoAnalysis, reasoning_source: str) -> list[tuple[str, str]]:
    s = analysis.weekly_summary
    rows = [
        (
            "analyze:summary",
            f"inputs_hash={analysis.inputs_hash}; gaps_found={s.gaps_found}; "
            f"pages_below_benchmark={s.pages_below_benchmark}; posts_planned={s.posts_planned}; "
            f"comments_drafted={s.comments_drafted}; reasoning_source={reasoning_source}",
        )
    ]
    rows += [
        (
            f"competitor:{g.domain}",
            f"{g.competitor} (DR {g.domain_rating}): {g.keywords_we_miss} keyword gap(s), "
            f"{g.ai_citation_share:.0%} AI-citation share. {g.notes}",
        )
        for g in analysis.competitor_gaps
    ]
    rows += [
        (
            f"audit:{p.url}",
            f"{p.page}: score {p.score}/100 ({p.status}). "
            + (" ".join(p.fixes) or "Meets all benchmarks."),
        )
        for p in analysis.geo_audit
    ]
    rows += [
        (
            f"blog:{b.keyword}",
            f"score {b.opportunity_score}: {b.monthly_searches}/mo, difficulty {b.difficulty}, "
            f"{b.intent} intent via {b.source} ({b.source_detail}).",
        )
        for b in analysis.blog_opportunities
    ]
    rows += [
        (
            f"comment:{c.platform}:{c.url}",
            f"relevance {c.relevance_score}/100: \"{c.thread_title}\" — owner-voice draft queued.",
        )
        for c in analysis.comment_opportunities
    ]
    return rows


async def _propose_seo_actions(
    principal: Principal, analysis: SeoAnalysis, run_id: uuid.UUID
) -> None:
    """Queue the week's drafts through the human-approved action gate (ADR 0007): the top
    POSTS_PER_WEEK blog drafts as `publish_blog_post`, every comment draft as `post_comment`.
    Each proposal is best-effort — a gate hiccup never fails the run."""
    from app.actions import service as actions_service
    from app.actions.schemas import ProposeActionIn

    payloads = [
        ProposeActionIn(
            agent=AGENT,
            kind="publish_blog_post",
            run_id=run_id,
            params={
                "keyword": b.keyword,
                "title": b.title,
                "outline": b.outline,
                "draft_intro": b.draft_intro,
            },
        )
        for b in analysis.blog_opportunities[: analytics.POSTS_PER_WEEK]
    ]
    payloads += [
        ProposeActionIn(
            agent=AGENT,
            kind="post_comment",
            run_id=run_id,
            params={
                "platform": c.platform,
                "url": c.url,
                "thread_title": c.thread_title,
                "draft_comment": c.draft_comment,
            },
        )
        for c in analysis.comment_opportunities
    ]
    for payload in payloads:
        try:
            await actions_service.propose_action(principal, payload)
        except Exception:
            continue


async def run_seo_analysis(
    principal: Principal, *, as_of: date | None = None, force: bool = False
) -> SeoRunResult:
    settings = get_settings()
    as_of = as_of or date.today()
    client = get_seo_intel_client(as_of=as_of, settings=settings)
    started = perf_counter()

    # Self-learning READ: pull distilled lessons (preferences + past wins/losses) to steer the
    # NARRATION only (ADR-0003: never the figures). Isolated session + best-effort → '' on any
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
    # (tenant_settings.fsm_provider). Steers NARRATION + audit metadata only — never a figure
    # (ADR 0003). NOTE: SeoRunResult's response shape is a versioned frontend contract (exact key
    # set), so unlike the other agents the provider is NOT added as a result field here; it rides
    # in the narration and the run audit detail instead. Any failure -> the ServiceTitan default.
    provider = "ServiceTitan"
    try:
        async with tenant_session(principal.tenant_id) as ps:
            provider = display_name(await tenant_settings_repo.get_fsm_provider(ps))
    except Exception:
        provider = "ServiceTitan"

    telemetry = _telemetry.start_collection()  # per-run narration cost (NULL on template path)
    try:
        state = await SEO_GRAPH.ainvoke(
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
                session, run_id=failed_id, agent=AGENT, status="failed",
                horizon_days=HORIZON_DAYS, inputs_hash=None, created_by=principal.user_id,
                duration_ms=duration_ms, error=str(exc), result=None,
            )
            await runs.insert_audit(
                session, actor=str(principal.user_id), action="seo.run.failed",
                target=str(failed_id), detail={"error": str(exc)},
            )
        raise

    analysis: SeoAnalysis = state["analysis"]
    narrative: str = state["narrative"]
    reasoning_source: str = state.get("reasoning_source", "template")
    duration_ms = int((perf_counter() - started) * 1000)
    run_id = uuid.uuid4()
    result = build_result(
        analysis, narrative=narrative, analysis_timestamp=datetime.now(timezone.utc), run_id=run_id
    )

    async with tenant_session(principal.tenant_id) as session:
        if not force:
            existing = await runs.get_existing_result_by_hash(
                session, agent=AGENT, inputs_hash=analysis.inputs_hash
            )
            if existing is not None:
                return SeoRunResult.model_validate(existing)
        await runs.create_run(
            session, run_id=run_id, agent=AGENT, status="succeeded", horizon_days=HORIZON_DAYS,
            inputs_hash=analysis.inputs_hash, created_by=principal.user_id,
            duration_ms=duration_ms, result=result.model_dump(mode="json"),
            **telemetry.as_run_fields(),
        )
        await runs.add_recommendations(session, run_id=run_id, rows=_recommendation_rows(analysis))
        await runs.add_reasoning(
            session, run_id=run_id, rows=_reasoning_rows(analysis, reasoning_source)
        )
        await runs.insert_audit(
            session, actor=str(principal.user_id), action="seo.run", target=str(run_id),
            detail={
                "inputs_hash": analysis.inputs_hash,
                "gaps_found": analysis.weekly_summary.gaps_found,
                "pages_below_benchmark": analysis.weekly_summary.pages_below_benchmark,
                "reasoning_source": reasoning_source,
                "source_system": provider,
            },
        )

    # Self-learning: record this run as a CASE (outcome 'pending' until feedback labels it).
    # Best-effort + ISOLATED session so a learning failure can never roll back the run we just
    # persisted above.
    try:
        from app.learning import service as learning

        async with tenant_session(principal.tenant_id) as ls:
            await learning.record_case(
                ls,
                agent=AGENT,
                run_id=run_id,
                problem_text=_situation_brief(analysis),
                recommendation_summary=(narrative or "")[:600],
                recommendation_kind="seo_advisory",
                problem_features={
                    "gaps_found": analysis.weekly_summary.gaps_found,
                    "pages_below_benchmark": analysis.weekly_summary.pages_below_benchmark,
                    "posts_planned": analysis.weekly_summary.posts_planned,
                    "comments_drafted": analysis.weekly_summary.comments_drafted,
                },
                settings=settings,
            )
    except Exception:
        pass

    # Propose the drafts through the action gate (ADR 0007) — best-effort, never fails the run.
    try:
        await _propose_seo_actions(principal, analysis, run_id)
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
