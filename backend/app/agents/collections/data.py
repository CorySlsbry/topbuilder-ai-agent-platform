"""Assemble a CollectionsData bundle from a CollectionsClient (DB-free, easy to preview)."""
from __future__ import annotations

from datetime import date

from app.agents.collections.models import CollectionsData
from app.integrations.collections.client import CollectionsClient


async def assemble_collections_data(client: CollectionsClient, *, as_of: date) -> CollectionsData:
    return CollectionsData(
        as_of=as_of,
        invoices=await client.get_open_invoices(),
        promises=await client.get_promises(),
        contacts=await client.get_contacts(),
    )
