"""Deterministic SEO/GEO Marketing engine.

No LLM, no randomness — every score, gap count, and ranking is reproducible (ADR 0003). The
reasoning node narrates these numbers and the drafts; it never recomputes a metric.

The audit thresholds encode the 2026 GEO benchmarks (Ahrefs/Profound-era citation research):
fact density 1/80-200 words, FAQ pages 15-30 questions with 40-80-word answers, <30-day freshness
(~3.2x citation lift), ~2,900-word citable long-form, front-loaded answers (44.2% of citations come
from the first 30% of text), YouTube mention correlation 0.737, Reddit = #1 cited domain, listicles
= 32.5% of AI citations.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import date

from app.agents.seo.models import SeoData, SitePage

# --- 2026 GEO benchmark constants (the audit thresholds) ------------------------------------
FACT_DENSITY_BENCHMARK_PER_200W = 1.0  # 1 verifiable fact per 80-200 words; flag sparser than 1/200
FAQ_MIN_QUESTIONS = 15
FAQ_MAX_QUESTIONS = 30
FAQ_ANSWER_MIN_WORDS = 40
FAQ_ANSWER_MAX_WORDS = 80
FRESHNESS_BENCHMARK_DAYS = 30  # pages updated <30 days ago get ~3.2x more AI citations
FRESHNESS_CITATION_MULTIPLIER = 3.2
CITABLE_WORD_TARGET = 2900  # citable long-form target word count
FRONT_LOAD_FIRST_30PCT_SHARE = 0.442  # 44.2% of AI citations come from the first 30% of text
YOUTUBE_MENTION_CORRELATION = 0.737  # strongest single AI-citation channel signal
LISTICLE_CITATION_SHARE = 0.325  # listicles draw 32.5% of all AI citations
REDDIT_CITED_DOMAIN_RANK = 1  # Reddit = #1 cited domain across LLMs

# --- page-score weights (sum to 100) ---------------------------------------------------------
WEIGHT_FACT_DENSITY = 30
WEIGHT_FAQ = 25
WEIGHT_FRESHNESS = 25
WEIGHT_LENGTH = 20

# --- blog-opportunity scoring (volume x intent x channel / difficulty) -----------------------
INTENT_WEIGHTS = {"transactional": 1.5, "commercial": 1.3, "informational": 1.0}
SOURCE_MULTIPLIERS = {"reddit": 1.2, "youtube": 1.15, "search": 1.0}  # channel-signal flavored
DIFFICULTY_DAMPING = 10  # keeps near-zero-difficulty keywords from exploding the score
POSTS_PER_WEEK = 2  # weekly publishing cadence -> the top-N opportunities become drafts

# --- comment-relevance scoring ----------------------------------------------------------------
RELEVANCE_MATCH_WEIGHT = 0.5
RELEVANCE_FRESHNESS_WEIGHT = 0.3
RELEVANCE_ENGAGEMENT_WEIGHT = 0.2
MATCH_SATURATION = 3  # matched tenant services for a full topical-match score
ENGAGEMENT_SATURATION = 50  # replies for a full engagement score
THREAD_FRESH_DAYS = 7  # a thread this young scores full freshness


# --------------------------------------------------------------------------------------------
# Result types
# --------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class CompetitorGap:
    competitor: str
    domain: str
    domain_rating: int
    keywords_we_miss: int
    ai_citation_share: float
    notes: str


@dataclass(frozen=True)
class GeoPageAudit:
    page: str
    url: str
    word_count: int
    facts_per_200_words: float
    faq_count: int
    freshness_days: int
    score: int  # 0..100, deterministic from the benchmark constants
    status: str  # 'pass' | 'below_benchmark'
    fixes: list[str]


@dataclass(frozen=True)
class BlogOpportunity:
    keyword: str
    title: str
    monthly_searches: int
    difficulty: int
    source: str
    source_detail: str
    intent: str
    opportunity_score: float
    outline: list[str]
    draft_intro: str


@dataclass(frozen=True)
class CommentOpportunity:
    platform: str
    thread_title: str
    url: str
    relevance_score: int  # 0..100
    draft_comment: str


@dataclass(frozen=True)
class WeeklySummary:
    gaps_found: int
    pages_below_benchmark: int
    posts_planned: int
    comments_drafted: int


@dataclass(frozen=True)
class SeoAnalysis:
    as_of: date
    competitor_gaps: list[CompetitorGap]
    geo_audit: list[GeoPageAudit]
    blog_opportunities: list[BlogOpportunity]
    comment_opportunities: list[CommentOpportunity]
    weekly_summary: WeeklySummary
    inputs_hash: str


# --------------------------------------------------------------------------------------------
# Pure primitives
# --------------------------------------------------------------------------------------------
def facts_per_200_words(verifiable_facts: int, word_count: int) -> float:
    return verifiable_facts * 200 / word_count if word_count > 0 else 0.0


def fact_density_subscore(per_200_words: float) -> float:
    return min(1.0, per_200_words / FACT_DENSITY_BENCHMARK_PER_200W)


def faq_subscore(faq_count: int, is_faq_page: bool) -> float:
    if not is_faq_page:
        return 1.0  # the FAQ-question band applies only to FAQ pages
    if faq_count < FAQ_MIN_QUESTIONS:
        return faq_count / FAQ_MIN_QUESTIONS
    if faq_count > FAQ_MAX_QUESTIONS:
        return FAQ_MAX_QUESTIONS / faq_count
    return 1.0


def freshness_subscore(freshness_days: int) -> float:
    if freshness_days <= FRESHNESS_BENCHMARK_DAYS:
        return 1.0
    return FRESHNESS_BENCHMARK_DAYS / freshness_days


def length_subscore(word_count: int) -> float:
    return min(1.0, word_count / CITABLE_WORD_TARGET) if word_count > 0 else 0.0


def page_score(page: SitePage) -> int:
    """Deterministic 0..100 GEO score, a weighted sum of the four benchmark sub-scores."""
    per_200 = facts_per_200_words(page.verifiable_facts, page.word_count)
    raw = (
        WEIGHT_FACT_DENSITY * fact_density_subscore(per_200)
        + WEIGHT_FAQ * faq_subscore(page.faq_count, page.is_faq_page)
        + WEIGHT_FRESHNESS * freshness_subscore(page.freshness_days)
        + WEIGHT_LENGTH * length_subscore(page.word_count)
    )
    return round(raw)


def opportunity_score(monthly_searches: int, difficulty: int, intent: str, source: str) -> float:
    """volume x intent-weight x channel-multiplier / damped difficulty, rounded to 1 decimal."""
    weight = INTENT_WEIGHTS.get(intent, 1.0)
    multiplier = SOURCE_MULTIPLIERS.get(source, 1.0)
    return round(monthly_searches * weight * multiplier / (difficulty + DIFFICULTY_DAMPING), 1)


def comment_relevance_score(matched_services: int, thread_age_days: int, replies: int) -> int:
    """0..100 relevance: topical match (0.5) + thread freshness (0.3) + engagement (0.2)."""
    match = min(1.0, matched_services / MATCH_SATURATION)
    fresh = 1.0 if thread_age_days <= THREAD_FRESH_DAYS else THREAD_FRESH_DAYS / thread_age_days
    engagement = min(1.0, replies / ENGAGEMENT_SATURATION)
    return round(
        100
        * (
            RELEVANCE_MATCH_WEIGHT * match
            + RELEVANCE_FRESHNESS_WEIGHT * fresh
            + RELEVANCE_ENGAGEMENT_WEIGHT * engagement
        )
    )


def _page_fixes(page: SitePage, per_200: float) -> list[str]:
    """The deterministic fix list — one entry per failed 2026 GEO benchmark check."""
    fixes: list[str] = []
    if per_200 < FACT_DENSITY_BENCHMARK_PER_200W:
        needed = max(0, math.ceil(page.word_count / 200) - page.verifiable_facts)
        fixes.append(
            f"Fact density {per_200:.2f}/200 words is below the 1-per-200 benchmark — add "
            f"{needed} verifiable facts (prices, specs, dates), front-loaded into the first 30% "
            f"of the page (44.2% of AI citations come from there)."
        )
    if page.is_faq_page and not (FAQ_MIN_QUESTIONS <= page.faq_count <= FAQ_MAX_QUESTIONS):
        fixes.append(
            f"FAQ has {page.faq_count} questions vs the {FAQ_MIN_QUESTIONS}-{FAQ_MAX_QUESTIONS} "
            f"benchmark — expand with {FAQ_ANSWER_MIN_WORDS}-{FAQ_ANSWER_MAX_WORDS}-word answers, "
            f"no accordions."
        )
    if page.freshness_days > FRESHNESS_BENCHMARK_DAYS:
        fixes.append(
            f"Last updated {page.freshness_days} days ago vs the <{FRESHNESS_BENCHMARK_DAYS}-day "
            f"freshness benchmark — refresh for the ~{FRESHNESS_CITATION_MULTIPLIER}x AI-citation "
            f"multiplier."
        )
    return fixes


def _audit_page(page: SitePage) -> GeoPageAudit:
    per_200 = facts_per_200_words(page.verifiable_facts, page.word_count)
    fixes = _page_fixes(page, per_200)
    return GeoPageAudit(
        page=page.page,
        url=page.url,
        word_count=page.word_count,
        facts_per_200_words=round(per_200, 2),
        faq_count=page.faq_count,
        freshness_days=page.freshness_days,
        score=page_score(page),
        status="below_benchmark" if fixes else "pass",
        fixes=fixes,
    )


# --------------------------------------------------------------------------------------------
# Engine
# --------------------------------------------------------------------------------------------
def analyze(data: SeoData) -> SeoAnalysis:
    gaps = [
        CompetitorGap(
            competitor=c.name,
            domain=c.domain,
            domain_rating=c.domain_rating,
            keywords_we_miss=len(c.keywords_we_miss),
            ai_citation_share=c.ai_citation_share,
            notes=c.notes,
        )
        for c in data.competitors
    ]
    gaps.sort(key=lambda g: (g.keywords_we_miss, g.ai_citation_share), reverse=True)

    audit = [_audit_page(p) for p in data.pages]
    audit.sort(key=lambda a: (a.score, a.page))  # worst first — the fix list reads top-down

    blogs = [
        BlogOpportunity(
            keyword=s.keyword,
            title=s.title,
            monthly_searches=s.monthly_searches,
            difficulty=s.difficulty,
            source=s.source,
            source_detail=s.source_detail,
            intent=s.intent,
            opportunity_score=opportunity_score(
                s.monthly_searches, s.difficulty, s.intent, s.source
            ),
            outline=list(s.outline),
            draft_intro=s.draft_intro,
        )
        for s in data.blog_sources
    ]
    blogs.sort(key=lambda b: (-b.opportunity_score, b.keyword))

    comments = [
        CommentOpportunity(
            platform=t.platform,
            thread_title=t.thread_title,
            url=t.url,
            relevance_score=comment_relevance_score(
                len(t.matched_services), t.thread_age_days, t.replies
            ),
            draft_comment=t.draft_comment,
        )
        for t in data.comment_threads
    ]
    comments.sort(key=lambda c: (-c.relevance_score, c.thread_title))

    summary = WeeklySummary(
        gaps_found=sum(g.keywords_we_miss for g in gaps),
        pages_below_benchmark=sum(1 for a in audit if a.status == "below_benchmark"),
        posts_planned=min(POSTS_PER_WEEK, len(blogs)),
        comments_drafted=len(comments),
    )

    return SeoAnalysis(
        as_of=data.as_of,
        competitor_gaps=gaps,
        geo_audit=audit,
        blog_opportunities=blogs,
        comment_opportunities=comments,
        weekly_summary=summary,
        inputs_hash=_hash_inputs(data),
    )


def _hash_inputs(data: SeoData) -> str:
    payload = {
        "as_of": data.as_of.isoformat(),
        "competitors": sorted((asdict(c) for c in data.competitors), key=lambda r: r["domain"]),
        "pages": sorted((asdict(p) for p in data.pages), key=lambda r: r["url"]),
        "blog_sources": sorted((asdict(b) for b in data.blog_sources), key=lambda r: r["keyword"]),
        "comment_threads": sorted(
            (asdict(t) for t in data.comment_threads), key=lambda r: r["url"]
        ),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
