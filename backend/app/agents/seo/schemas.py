"""API-facing schemas (spec-shaped) + mapper for the SEO/GEO Marketing agent.

The frontend is built against EXACTLY these field names — change nothing without versioning.
(`title` on a blog opportunity is intentionally internal: it rides in the publish_blog_post
action params and the recommendation payload, not the run response.)
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.agents.seo.analytics import SeoAnalysis


class CompetitorGapOut(BaseModel):
    competitor: str
    domain: str
    domain_rating: int
    keywords_we_miss: int
    ai_citation_share: float
    notes: str


class GeoPageAuditOut(BaseModel):
    page: str
    url: str
    word_count: int
    facts_per_200_words: float
    faq_count: int
    freshness_days: int
    score: int
    status: str  # 'pass' | 'below_benchmark'
    fixes: list[str]


class BlogOpportunityOut(BaseModel):
    keyword: str
    monthly_searches: int
    difficulty: int
    source: str
    source_detail: str
    intent: str
    opportunity_score: float
    outline: list[str]
    draft_intro: str


class CommentOpportunityOut(BaseModel):
    platform: str
    thread_title: str
    url: str
    relevance_score: int
    draft_comment: str


class WeeklySummaryOut(BaseModel):
    gaps_found: int
    pages_below_benchmark: int
    posts_planned: int
    comments_drafted: int


class SeoRunResult(BaseModel):
    run_id: uuid.UUID | None = None
    agent: str = "seo"
    analysis_timestamp: datetime
    competitor_gaps: list[CompetitorGapOut]
    geo_audit: list[GeoPageAuditOut]
    blog_opportunities: list[BlogOpportunityOut]
    comment_opportunities: list[CommentOpportunityOut]
    weekly_summary: WeeklySummaryOut
    narration: str
    reasoning_logs: list[str] = Field(default_factory=list)
    inputs_hash: str


def build_result(
    analysis: SeoAnalysis,
    *,
    narrative: str,
    analysis_timestamp: datetime,
    run_id: uuid.UUID | None = None,
) -> SeoRunResult:
    gaps = [CompetitorGapOut(**vars(g)) for g in analysis.competitor_gaps]
    audit = [GeoPageAuditOut(**vars(p)) for p in analysis.geo_audit]
    blogs = [
        BlogOpportunityOut(
            keyword=b.keyword,
            monthly_searches=b.monthly_searches,
            difficulty=b.difficulty,
            source=b.source,
            source_detail=b.source_detail,
            intent=b.intent,
            opportunity_score=b.opportunity_score,
            outline=b.outline,
            draft_intro=b.draft_intro,
        )
        for b in analysis.blog_opportunities
    ]
    comments = [CommentOpportunityOut(**vars(c)) for c in analysis.comment_opportunities]
    summary = WeeklySummaryOut(**vars(analysis.weekly_summary))
    return SeoRunResult(
        run_id=run_id,
        analysis_timestamp=analysis_timestamp,
        competitor_gaps=gaps,
        geo_audit=audit,
        blog_opportunities=blogs,
        comment_opportunities=comments,
        weekly_summary=summary,
        narration=narrative,
        inputs_hash=analysis.inputs_hash,
    )
