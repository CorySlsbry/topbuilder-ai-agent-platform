"""Offline fixture transport: a deterministic synthetic Resend confirmation, no network, no randomness."""
from __future__ import annotations

import hashlib


class FixtureEmailSendClient:
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
    ) -> dict:
        ref = "em-out-" + hashlib.sha1(f"{to}|{subject}".encode("utf-8")).hexdigest()[:12]
        return {"provider": "fixture", "mode": "fixture", "external_ref": ref, "to": to, "status": "sent"}
