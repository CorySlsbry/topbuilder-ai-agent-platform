"""Live email-inbox client — skeleton (ADR 0005). Selected by EMAIL_MODE=live.

In production the mailbox is read via the tenant's mail provider (Gmail API / Microsoft Graph,
OAuth tokens from the credential vault) and an extraction step (LLM or provider rules) populates the
typed `EmailMessage` fields (intent, value, sentiment, tier) — mirroring the Documents agent's OCR
layer. Workflow stats come from the outbound automation provider's reporting API. FAIL-CLOSED: this
skeleton never fabricates inbox data — every method raises until verified against a real tenant,
mirroring the other live-client skeletons. All writes (send/delete/rewrite) stay behind the action
gate and are NOT part of this read-only surface.
"""
from __future__ import annotations

from datetime import date

from app.agents.email.models import EmailMessage, WorkflowStats
from app.config import Settings


class LiveEmailInboxClient:
    def __init__(self, settings: Settings) -> None:
        self._s = settings

    async def get_emails(self, as_of: date) -> list[EmailMessage]:
        # Gmail API users.messages.list (q="is:unread") / MS Graph /me/mailFolders/inbox/messages
        # -> extraction (intent, value_cents, sentiment, customer_tier) -> EmailMessage.
        raise NotImplementedError(
            "Map the tenant mailbox (Gmail/Microsoft Graph, vault OAuth) + extraction -> EmailMessage."
        )

    async def get_workflows(self) -> list[WorkflowStats]:
        # Outbound-automation reporting (sends/opens/replies/booked per sequence) -> WorkflowStats.
        raise NotImplementedError("Map the automation provider's sequence reporting -> WorkflowStats.")
