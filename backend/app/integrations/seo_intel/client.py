"""SEO-intel adapter boundary for the SEO/GEO Marketing agent (fixture now, live APIs when wired).

Live mode sources competitor/keyword data from an SEO API (Ahrefs/Semrush), page audits from the
tenant's own site + Search Console, and thread intel from the Reddit/YouTube data APIs — all behind
this one protocol, so the engine never knows the difference (ADR 0005).
"""
from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from app.agents.seo.models import BlogSource, CommentThread, Competitor, SitePage
from app.config import Settings, get_settings


@runtime_checkable
class SeoIntelClient(Protocol):
    async def get_competitors(self) -> list[Competitor]: ...
    async def get_pages(self) -> list[SitePage]: ...
    async def get_blog_sources(self) -> list[BlogSource]: ...
    async def get_comment_threads(self) -> list[CommentThread]: ...


def get_seo_intel_client(
    *, as_of: date | None = None, settings: Settings | None = None
) -> SeoIntelClient:
    settings = settings or get_settings()
    # SEO_MODE in config.py (fixture | live), read defensively so fixture stays the default even
    # on a Settings build that predates the knob (config.py is platform-owned).
    mode = str(getattr(settings, "seo_mode", "fixture")).lower()
    if mode == "live":
        from app.integrations.seo_intel.live_seo_intel_client import LiveSeoIntelClient

        return LiveSeoIntelClient(settings)

    from app.integrations.seo_intel.fixture_client import FixtureSeoIntelClient

    return FixtureSeoIntelClient()
