"""Assemble an InboxData bundle from an EmailInboxClient (DB-free)."""
from __future__ import annotations

from datetime import date

from app.agents.email.models import InboxData
from app.integrations.email_inbox.client import EmailInboxClient


async def assemble_inbox_data(client: EmailInboxClient, *, as_of: date) -> InboxData:
    return InboxData(
        as_of=as_of,
        emails=await client.get_emails(as_of),
        workflows=await client.get_workflows(),
    )
