"""Live SEO-intel client — fail-closed skeleton (ADR 0005). Selected by SEO_MODE=live.

Each method names its real upstream so going live is mapping work, not design work. Until that
mapping is verified against real accounts, every call raises — this adapter NEVER fabricates
competitor data, audit numbers, or thread intel (same fail-closed posture as the ST adapters).
"""
from __future__ import annotations

from app.agents.seo.models import BlogSource, CommentThread, Competitor, SitePage
from app.config import Settings


class LiveSeoIntelClient:
    def __init__(self, settings: Settings) -> None:
        self._s = settings

    async def get_competitors(self) -> list[Competitor]:
        # Ahrefs/Semrush API: competing-domains + content-gap report -> Competitor
        # (domain_rating, keyword gaps); Peec.ai/Profound for ai_citation_share.
        raise NotImplementedError(
            "Map an SEO API (Ahrefs/Semrush content gap + an AI-citation tracker) -> Competitor."
        )

    async def get_pages(self) -> list[SitePage]:
        # Crawl the tenant's sitemap (word/fact/FAQ counts) + Search Console for freshness.
        raise NotImplementedError(
            "Map a tenant-site crawl + Search Console -> SitePage (facts, FAQs, freshness)."
        )

    async def get_blog_sources(self) -> list[BlogSource]:
        # Reddit search API + YouTube Data API + a keyword API (volume/difficulty); drafts are
        # produced by the narration layer downstream, never invented here.
        raise NotImplementedError(
            "Map Reddit/YouTube/keyword APIs -> BlogSource (volume, difficulty, thread provenance)."
        )

    async def get_comment_threads(self) -> list[CommentThread]:
        # Reddit search API + YouTube Data API filtered to the tenant's service area/topics.
        raise NotImplementedError(
            "Map Reddit/YouTube thread search -> CommentThread (age, replies, matched services)."
        )
