"""Domain models for the SEO/GEO Marketing agent (dependency-free, stdlib only)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class Competitor:
    name: str
    domain: str
    domain_rating: int
    keywords_we_miss: list[str]  # the actual keyword gaps; the engine reports the count
    ai_citation_share: float  # share of tracked AI answers citing this competitor (0..1)
    notes: str


@dataclass(frozen=True)
class SitePage:
    page: str
    url: str
    word_count: int
    verifiable_facts: int  # countable, sourceable facts on the page (prices, specs, dates, stats)
    faq_count: int
    is_faq_page: bool  # the 15-30-question FAQ benchmark applies only to FAQ pages
    freshness_days: int  # days since the page content was last updated


@dataclass(frozen=True)
class BlogSource:
    """A long-tail blog opportunity mined from Reddit / YouTube / search."""

    keyword: str
    title: str  # drafted post title (prose; rides into the publish_blog_post proposal)
    monthly_searches: int
    difficulty: int  # 0..100 keyword difficulty
    source: str  # 'reddit' | 'youtube' | 'search'
    source_detail: str  # the actual thread / video / SERP-cluster title it was mined from
    intent: str  # 'transactional' | 'commercial' | 'informational'
    outline: list[str]  # 4-6 drafted H2s
    draft_intro: str  # drafted, answer-front-loaded intro (prose only)


@dataclass(frozen=True)
class CommentThread:
    """A live Reddit/YouTube thread worth an owner-voice comment."""

    platform: str  # 'reddit' | 'youtube'
    thread_title: str
    url: str
    thread_age_days: int
    replies: int
    matched_services: list[str]  # tenant services the thread is actually about
    draft_comment: str  # drafted in the owner's plain-spoken voice (prose only)


@dataclass(frozen=True)
class SeoData:
    as_of: date
    competitors: list[Competitor]
    pages: list[SitePage]
    blog_sources: list[BlogSource]
    comment_threads: list[CommentThread] = field(default_factory=list)
