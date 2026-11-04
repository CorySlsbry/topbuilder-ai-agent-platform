"""Reasoning (narration) layer for the SEO/GEO agent. Numbers in, prose out — never computes."""
from __future__ import annotations

import json

from app.agents._narrate import narrate
from app.agents.seo.analytics import POSTS_PER_WEEK, SeoAnalysis
from app.agents.seo.prompts import SYSTEM_PERSONA
from app.config import Settings


def _analysis_brief(analysis: SeoAnalysis) -> dict:
    s = analysis.weekly_summary
    return {
        "as_of": analysis.as_of.isoformat(),
        "weekly_summary": {
            "gaps_found": s.gaps_found,
            "pages_below_benchmark": s.pages_below_benchmark,
            "posts_planned": s.posts_planned,
            "comments_drafted": s.comments_drafted,
        },
        "competitor_gaps": [
            {
                "competitor": g.competitor,
                "keywords_we_miss": g.keywords_we_miss,
                "ai_citation_share": g.ai_citation_share,
            }
            for g in analysis.competitor_gaps
        ],
        "pages_below_benchmark": [
            {"page": p.page, "score": p.score, "fixes": p.fixes}
            for p in analysis.geo_audit
            if p.status == "below_benchmark"
        ],
        "top_blog_opportunities": [
            {
                "keyword": b.keyword,
                "monthly_searches": b.monthly_searches,
                "difficulty": b.difficulty,
                "source": b.source,
                "opportunity_score": b.opportunity_score,
            }
            for b in analysis.blog_opportunities[:POSTS_PER_WEEK]
        ],
        "comment_threads": [
            {"platform": c.platform, "thread": c.thread_title, "relevance_score": c.relevance_score}
            for c in analysis.comment_opportunities
        ],
    }


def _template_narrative(analysis: SeoAnalysis) -> str:
    s = analysis.weekly_summary
    below = [p for p in analysis.geo_audit if p.status == "below_benchmark"]
    lines = [
        f"This week's GEO review: competitors hold {s.gaps_found} keyword gaps we don't rank for, "
        f"{s.pages_below_benchmark} of {len(analysis.geo_audit)} audited pages sit below the 2026 "
        f"GEO benchmarks, {s.posts_planned} post(s) are drafted for approval, and "
        f"{s.comments_drafted} owner-voice comment(s) are queued.",
        "",
    ]
    if analysis.competitor_gaps:
        top_gap = analysis.competitor_gaps[0]
        lines.append(
            f"- Biggest gap: {top_gap.competitor} ({top_gap.domain}) ranks for "
            f"{top_gap.keywords_we_miss} keywords we miss and appears in "
            f"{top_gap.ai_citation_share:.0%} of tracked AI answers. {top_gap.notes}"
        )
    for p in below:
        lines.append(f"- Fix {p.page} (score {p.score}/100): {' '.join(p.fixes)}")
    for b in analysis.blog_opportunities[: s.posts_planned]:
        lines.append(
            f"- Publish: \"{b.keyword}\" ({b.monthly_searches:,} searches/mo, difficulty "
            f"{b.difficulty}, via {b.source}: {b.source_detail}) — opportunity score "
            f"{b.opportunity_score}."
        )
    for c in analysis.comment_opportunities:
        lines.append(
            f"- Reply on {c.platform}: \"{c.thread_title}\" (relevance {c.relevance_score}/100) — "
            f"draft ready in your voice."
        )
    if analysis.blog_opportunities:
        top = analysis.blog_opportunities[0]
        lines.append("")
        lines.append(
            f"Recommended action: approve the \"{top.keyword}\" post first "
            f"(score {top.opportunity_score} — highest-value move this week), then the page fixes."
        )
    return "\n".join(lines)


def _adapt_provider(text: str, provider: str) -> str:
    """Narration-only provider adaptation (ADR 0003 — figures untouched): rename the flagship
    default to the tenant's field-service system and make sure the system of record is named."""
    if provider and provider != "ServiceTitan":
        text = text.replace("ServiceTitan", provider)
        if provider not in text:
            text += f"\n\nField-service system of record: {provider}."
    return text


async def explain(
    analysis: SeoAnalysis,
    settings: Settings,
    lessons: str = "",
    provider: str = "ServiceTitan",
) -> str:
    # `lessons` = retrieved self-learning memory (past wins/edits). It steers the NARRATION only;
    # the persona below still forbids recomputing any figure, so the numbers stay deterministic.
    # `provider` = the tenant's field-service system display name — wording/metadata only.
    brief = _analysis_brief(analysis)
    template = _adapt_provider(_template_narrative(analysis), provider)
    user_content = (
        "Authoritative analysis (quote, do not recompute):\n```json\n"
        + json.dumps(brief, indent=2)
        + "\n```"
        + (
            "\n\nLessons from past human feedback on this agent — apply where "
            "relevant, but STILL quote every figure above exactly:\n" + lessons
            if lessons
            else ""
        )
        + f"\nThe customer's field-service system of record is {provider} — refer"
        " to it by that name."
        + "\nWrite the executive narrative."
    )
    narrative = await narrate(
        agent="seo",
        settings=settings,
        system=[{"type": "text", "text": SYSTEM_PERSONA, "cache_control": {"type": "ephemeral"}}],
        user_content=user_content,
        brief=brief,
        template=template,
    )
    return _adapt_provider(narrative, provider)
