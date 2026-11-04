"""Assemble a SeoData bundle from a SeoIntelClient (DB-free)."""
from __future__ import annotations

from datetime import date

from app.agents.seo.models import SeoData
from app.integrations.seo_intel.client import SeoIntelClient


async def assemble_seo_data(client: SeoIntelClient, *, as_of: date) -> SeoData:
    return SeoData(
        as_of=as_of,
        competitors=await client.get_competitors(),
        pages=await client.get_pages(),
        blog_sources=await client.get_blog_sources(),
        comment_threads=await client.get_comment_threads(),
    )
