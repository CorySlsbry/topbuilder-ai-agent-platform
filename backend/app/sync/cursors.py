"""Pure cursor algebra for the poll backbone (ADR 0010).

A `sync_cursor` row is due when its cadence has elapsed; its watermark advances monotonically so a
re-pulled overlap window (which the dedupe layer collapses) can never rewind detection. The opaque
ServiceTitan `continueFrom` / QBO `changedSince` tokens are stored verbatim by the service; the only
algebra worth unit-testing lives here.
"""
from __future__ import annotations

import datetime as dt


def is_due(last_run_at: dt.datetime | None, cadence_seconds: int, now: dt.datetime) -> bool:
    """A cursor is due if it has never run, or its cadence has elapsed since the last run."""
    if last_run_at is None:
        return True
    return (now - last_run_at).total_seconds() >= cadence_seconds


def _parse(ts: str) -> dt.datetime:
    s = ts.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    parsed = dt.datetime.fromisoformat(s)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed


def advance_watermark(current: str | None, seen: list[str]) -> str | None:
    """The monotonic high-water mark: the latest `modifiedOn` across the current cursor + this batch.

    Never moves backward, so re-sweeping an overlap window (the crash/clock-skew backstop) cannot
    rewind the cursor and skip records. Returns the original string of the maximum timestamp.
    """
    candidates = [s for s in [current, *seen] if s]
    if not candidates:
        return current
    return max(candidates, key=_parse)
