"""The reporting fan-out: format an operator report and push it to Slack + email.

Design rules (load-bearing):
  * PURE formatters — `format_slack_message`, `format_email`, `format_digest`, `format_digest_email`
    are network-free and deterministic (oracle-tested). HTML is escaped so a reporter-controlled
    message can't inject markup into the operator's inbox.
  * `notify_operators` NEVER raises to its caller. A Slack outage, a bad email address, an unconfigured
    deployment — all resolve to a status dict, because reporting must not break the thing being
    reported on (a signup, an assistant reply, a bug submission).
  * FAIL CLOSED: no `slack_webhook_url` and no `operator_notify_emails` -> both channels 'skipped'. A
    per-event toggle set False short-circuits to {'status': 'disabled'}.
"""
from __future__ import annotations

import html as _html
import logging

from app.config import Settings
from app.notify import support_kinds

log = logging.getLogger("app.notify")

_SLACK_TIMEOUT_SECONDS = 10.0


# ── pure formatters ───────────────────────────────────────────────────────────────────────────────
def _reporter_line(name: str | None, email: str | None) -> str:
    """A single 'From: <name> <email>' line, degrading to 'anonymous' when neither is known."""
    if name and email:
        return f"{name} <{email}>"
    if email:
        return email
    if name:
        return name
    return "anonymous"


def format_slack_message(
    *, kind: str, name: str | None, email: str | None, message: str | None, source: str
) -> dict:
    """Render a Slack webhook payload (a top-level `text` fallback + rich `blocks`)."""
    label = support_kinds.label(kind)
    emoji = support_kinds.EMOJI.get(kind, "🔔")
    reporter = _reporter_line(name, email)
    body = (message or "").strip() or "(no message)"
    headline = f"{emoji} {label} — Top Builder AI"
    text = f"{headline}\nFrom: {reporter}\n{body}"
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": headline, "emoji": True}},
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*From:*\n{reporter}"},
                {"type": "mrkdwn", "text": f"*Source:*\n{source}"},
            ],
        },
        {"type": "section", "text": {"type": "mrkdwn", "text": body[:2900]}},
    ]
    return {"text": text, "blocks": blocks}


def format_email(
    *, kind: str, name: str | None, email: str | None, message: str | None, source: str
) -> tuple[str, str, str]:
    """Render (subject, html, text) for an operator email. The message body is HTML-escaped."""
    label = support_kinds.label(kind)
    reporter = _reporter_line(name, email)
    body = (message or "").strip() or "(no message)"
    subject = f"[Top Builder AI] {label} — {reporter}"
    text = (
        f"{label}\n"
        f"From: {reporter}\n"
        f"Source: {source}\n\n"
        f"{body}\n"
    )
    html = (
        f"<h2>{_html.escape(label)}</h2>"
        f"<p><strong>From:</strong> {_html.escape(reporter)}<br>"
        f"<strong>Source:</strong> {_html.escape(source)}</p>"
        f"<pre style=\"white-space:pre-wrap;font-family:inherit\">{_html.escape(body)}</pre>"
    )
    return subject, html, text


def _present_kind_lines(counts: dict[str, int]) -> list[str]:
    """One 'Label: N' line per kind with a positive count, in the canonical kind order."""
    order = ("signup", "chatbot", "bug", "feature", "question")
    return [f"{support_kinds.label(k)}: {counts.get(k, 0)}" for k in order if counts.get(k, 0) > 0]


def format_digest(counts: dict[str, int], *, total: int, window_hours: int = 24) -> dict:
    """Render the daily-digest Slack payload from per-kind counts."""
    headline = f"📊 Top Builder AI — {window_hours}h activity digest ({total} total)"
    lines = _present_kind_lines(counts) or ["No new activity"]
    text = headline + "\n" + "\n".join(lines)
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": headline, "emoji": True}},
        {"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(lines)}},
    ]
    return {"text": text, "blocks": blocks}


def format_digest_email(
    counts: dict[str, int], *, total: int, window_hours: int = 24
) -> tuple[str, str, str]:
    """Render (subject, html, text) for the daily-digest email."""
    subject = f"[Top Builder AI] {window_hours}h activity digest — {total} total"
    lines = _present_kind_lines(counts) or ["No new activity"]
    text = subject + "\n\n" + "\n".join(lines) + "\n"
    items = "".join(f"<li>{_html.escape(line)}</li>" for line in lines)
    html = f"<h2>{_html.escape(subject)}</h2><ul>{items}</ul>"
    return subject, html, text


# ── transport (impure — best-effort) ────────────────────────────────────────────────────────────────
async def _post_slack(url: str, payload: dict) -> bool:
    """POST the Slack webhook payload. Returns True on a 2xx. Raises on transport error (the caller
    swallows it). Kept tiny + monkeypatchable so the dispatch tests never touch the network."""
    import httpx

    async with httpx.AsyncClient(timeout=_SLACK_TIMEOUT_SECONDS) as client:
        resp = await client.post(url, json=payload)
    return 200 <= resp.status_code < 300


def _toggle_enabled(settings: Settings, kind: str) -> bool:
    return bool(getattr(settings, f"notify_on_{kind}", True))


async def notify_operators(settings: Settings, req: dict) -> dict:
    """Fan a support-request dict out to Slack + email. NEVER raises.

    `req` = {kind, name?, email?, message?, source}. Returns a status dict:
        {status: 'ok'|'disabled'|'invalid_kind', slack: 'sent'|'skipped'|'failed',
         email: 'sent'|'skipped'|'failed', email_count: int}
    """
    kind = str(req.get("kind", ""))
    if not support_kinds.is_kind(kind):
        log.warning("notify_operators: refusing unknown kind %r", kind)
        return {"status": "invalid_kind", "slack": "skipped", "email": "skipped", "email_count": 0}
    if not _toggle_enabled(settings, kind):
        return {"status": "disabled", "slack": "skipped", "email": "skipped", "email_count": 0}

    name = req.get("name")
    email = req.get("email")
    message = req.get("message")
    source = str(req.get("source") or "unknown")

    slack_status = "skipped"
    webhook = getattr(settings, "slack_webhook_url", None)
    if webhook:
        try:
            payload = format_slack_message(
                kind=kind, name=name, email=email, message=message, source=source
            )
            ok = await _post_slack(webhook, payload)
            slack_status = "sent" if ok else "failed"
        except Exception:  # transport/format failure must never propagate (best-effort)
            log.exception("notify_operators: slack post failed")
            slack_status = "failed"

    email_status, email_count = await _send_emails(
        settings,
        recipients=sorted(settings.operator_notify_email_set),
        subject_html_text=format_email(
            kind=kind, name=name, email=email, message=message, source=source
        ),
    )
    return {
        "status": "ok",
        "slack": slack_status,
        "email": email_status,
        "email_count": email_count,
    }


async def _send_emails(
    settings: Settings, *, recipients: list[str], subject_html_text: tuple[str, str, str]
) -> tuple[str, int]:
    """Send one email per operator recipient via the existing email_send client. Best-effort:
    a per-recipient failure is logged and does not abort the rest. Returns (status, count_sent)."""
    if not recipients:
        return "skipped", 0
    subject, html, text = subject_html_text
    try:
        from app.integrations.email_send.client import get_email_send_client

        client = get_email_send_client(settings=settings)
        sent = 0
        for to in recipients:
            try:
                await client.send(
                    to=to,
                    from_email=getattr(settings, "outreach_from_email", "outreach@send.topbuilderai.com"),
                    from_name="Top Builder AI Alerts",
                    reply_to=getattr(settings, "outreach_reply_to", None),
                    subject=subject,
                    html=html,
                    text=text,
                )
                sent += 1
            except Exception:
                log.exception("notify_operators: email send to %s failed", to)
        if sent == 0:
            return "failed", 0
        return "sent", sent
    except Exception:  # client construction failed (e.g. live mode with no key) — never propagate
        log.exception("notify_operators: email transport unavailable")
        return "failed", 0


async def send_digest(settings: Settings, counts: dict[str, int], *, total: int) -> dict:
    """Push ONE daily digest to Slack + email. NEVER raises. Returns the same status shape."""
    slack_status = "skipped"
    webhook = getattr(settings, "slack_webhook_url", None)
    if webhook:
        try:
            ok = await _post_slack(webhook, format_digest(counts, total=total))
            slack_status = "sent" if ok else "failed"
        except Exception:
            log.exception("send_digest: slack post failed")
            slack_status = "failed"

    email_status, email_count = await _send_emails(
        settings,
        recipients=sorted(settings.operator_notify_email_set),
        subject_html_text=format_digest_email(counts, total=total),
    )
    return {"status": "ok", "slack": slack_status, "email": email_status, "email_count": email_count}
