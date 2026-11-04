"""The email-inbox adapter boundary for the Email agent (read-only; ADR 0005).

The Email agent owns the *decision* brain, not the mailbox. The mail provider (Gmail / Microsoft 365
when live) hands us structured `EmailMessage` records — an extraction step populates the typed fields
(value, intent, sentiment), exactly like the Documents agent's OCR layer — plus per-sequence
`WorkflowStats` from the outbound automation. Replying, deleting, and rewriting a workflow are WRITES
that flow through the action gate (ADR 0007), never through this client.

NOTE: `email_mode` is read via getattr so this adapter needs no change to the orchestrator-owned
`app/config.py`; until the orchestrator adds `email_mode: str = "fixture"` to Settings, the factory
safely defaults to the fixture client.
"""
from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from app.agents.email.models import EmailMessage, WorkflowStats
from app.config import Settings, get_settings


@runtime_checkable
class EmailInboxClient(Protocol):
    async def get_emails(self, as_of: date) -> list[EmailMessage]: ...
    async def get_workflows(self) -> list[WorkflowStats]: ...


def get_email_inbox_client(
    *, as_of: date | None = None, settings: Settings | None = None
) -> EmailInboxClient:
    settings = settings or get_settings()
    mode = str(getattr(settings, "email_mode", "fixture")).lower()
    if mode == "live":
        from app.integrations.email_inbox.live_client import LiveEmailInboxClient

        return LiveEmailInboxClient(settings)

    from app.integrations.email_inbox.fixture_client import FixtureEmailInboxClient

    return FixtureEmailInboxClient()
