"""Live transport: send via the Resend API on the dedicated sending subdomain.

Fails closed without RESEND_API_KEY (never silently no-ops a send). The message is already approved by
the action gate and already CAN-SPAM/consent-checked by `app/outreach/compliance.py`; this only POSTs it.
One-click List-Unsubscribe headers are passed through so inbox providers show a native unsubscribe.
"""
from __future__ import annotations

from app.config import Settings

RESEND_SEND_URL = "https://api.resend.com/emails"


class LiveEmailSendClient:
    def __init__(self, settings: Settings) -> None:
        self._key = getattr(settings, "resend_api_key", None)

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
        if not self._key:
            raise RuntimeError(
                "email_send_mode=live but RESEND_API_KEY is not set — refusing to send (fail closed)."
            )
        import httpx

        payload: dict = {
            "from": f"{from_name} <{from_email}>" if from_name else from_email,
            "to": [to],
            "subject": subject,
        }
        if html:
            payload["html"] = html
        if text:
            payload["text"] = text
        if reply_to:
            payload["reply_to"] = reply_to
        if headers:
            payload["headers"] = headers
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                RESEND_SEND_URL,
                headers={"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"},
                json=payload,
            )
        if resp.status_code >= 300:
            raise RuntimeError(f"Resend send failed ({resp.status_code}): {resp.text[:300]}")
        data = resp.json()
        return {
            "provider": "resend",
            "mode": "live",
            "external_ref": data.get("id"),
            "to": to,
            "status": "sent",
        }
