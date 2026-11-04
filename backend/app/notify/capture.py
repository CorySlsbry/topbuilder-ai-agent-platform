"""The single best-effort capture entry point used by the routes AND the wiring points.

`capture_support_request` writes one operator-global row (via db.operator_session) and fires the
Slack/email fan-out, then stamps notified_at. It NEVER raises — every caller (a signup backfill, an
assistant reply, a bug form) is on a hot host path and must not be broken by a reporting failure. The
whole thing is wrapped so even a DB outage degrades to a logged no-op.
"""
from __future__ import annotations

import asyncio
import logging

from app.config import get_settings
from app.notify import notifier, support_kinds

log = logging.getLogger("app.notify")

# Strong refs to in-flight fire-and-forget captures so the event loop can't GC a task mid-run
# (asyncio only holds a weak ref to scheduled tasks). Discarded on completion via a done-callback.
_background_tasks: set[asyncio.Task] = set()


def schedule_capture(**kwargs) -> None:
    """Fire ``capture_support_request`` OFF the hot path so reporting-transport latency (a hung Slack
    webhook, a slow email provider) can NEVER add to the user-facing response — the answer is already
    computed; notification is fire-and-forget. Best-effort: the task runs on the running loop, its
    result is discarded, and capture itself never raises. Degrades to a logged no-op if there is no
    running loop (e.g. a synchronous context)."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        log.debug("schedule_capture: no running event loop; dropping kind=%s", kwargs.get("kind"))
        return
    task = loop.create_task(capture_support_request(**kwargs))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def capture_support_request(
    *,
    kind: str,
    name: str | None = None,
    email: str | None = None,
    message: str | None = None,
    source: str = "in_app",
    meta: dict | None = None,
    notify: bool = True,
) -> dict | None:
    """Persist a support_request + (optionally) notify operators. Returns the row, or None on any
    failure. Best-effort by contract: callers on a host path should still `try/except` around this."""
    if not support_kinds.is_kind(kind):
        log.warning("capture_support_request: unknown kind %r — dropping", kind)
        return None
    settings = get_settings()
    row: dict | None = None
    try:
        from app.db import operator_session
        from app.repositories import support as support_repo

        async with operator_session() as session:
            row = await support_repo.create_support_request(
                session, kind=kind, name=name, email=email, message=message,
                source=source, meta=meta,
            )
    except Exception:
        log.exception("capture_support_request: persist failed (kind=%s)", kind)
        row = None

    if notify:
        try:
            result = await notifier.notify_operators(
                settings,
                {"kind": kind, "name": name, "email": email, "message": message, "source": source},
            )
            if row is not None and result.get("status") == "ok" and (
                result.get("slack") == "sent" or result.get("email") == "sent"
            ):
                try:
                    from app.db import operator_session
                    from app.repositories import support as support_repo

                    async with operator_session() as session:
                        await support_repo.mark_notified(session, row["id"])
                except Exception:
                    log.exception("capture_support_request: mark_notified failed")
        except Exception:
            log.exception("capture_support_request: notify failed (kind=%s)", kind)
    return row
