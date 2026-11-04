"""The outbound email-send transport boundary (ADR 0005), used by the `send_outreach_email` executor.

The decision/compliance brain lives in `app/outreach/compliance.py`; this is only the wire that
delivers an already-approved, already-compliant message. Fixture mode returns a deterministic
confirmation (offline-testable); live mode sends via Resend on the dedicated sending subdomain and
FAILS CLOSED without `RESEND_API_KEY`. `email_send_mode` is read via getattr so this needs no change
if the orchestrator hasn't added the setting yet (defaults to fixture).
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.config import Settings, get_settings


@runtime_checkable
class EmailSendClient(Protocol):
    async def send(
        self,
        *,
        to: str,
        from_email: str,
        from_name: str,
        reply_to: str | None,
        subject: str,
        html: str,
        text: str,
        headers: dict[str, str] | None = None,
    ) -> dict: ...


def get_email_send_client(*, settings: Settings | None = None) -> EmailSendClient:
    settings = settings or get_settings()
    mode = str(getattr(settings, "email_send_mode", "fixture")).lower()
    if mode == "live":
        from app.integrations.email_send.live_client import LiveEmailSendClient

        return LiveEmailSendClient(settings)

    from app.integrations.email_send.fixture_client import FixtureEmailSendClient

    return FixtureEmailSendClient()
