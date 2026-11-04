"""Fixture-backed SEO-intel client (a static weekly intel snapshot for the demo tenant).

The drafts (titles, outlines, intros, comments) ARE the deterministic template output for
fixture/DISABLE_LLM mode — authored once, byte-stable, in the owner's plain-spoken voice.
"""
from __future__ import annotations

import json
import pathlib

from app.agents.seo.models import BlogSource, CommentThread, Competitor, SitePage

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"


def _load(name: str) -> list[dict]:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


class FixtureSeoIntelClient:
    async def get_competitors(self) -> list[Competitor]:
        return [Competitor(**row) for row in _load("competitors.json")]

    async def get_pages(self) -> list[SitePage]:
        return [SitePage(**row) for row in _load("site_pages.json")]

    async def get_blog_sources(self) -> list[BlogSource]:
        return [BlogSource(**row) for row in _load("blog_sources.json")]

    async def get_comment_threads(self) -> list[CommentThread]:
        return [CommentThread(**row) for row in _load("comment_threads.json")]
