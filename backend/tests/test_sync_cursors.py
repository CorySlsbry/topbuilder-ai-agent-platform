"""Pure tests for cursor cadence + watermark algebra (ADR 0010)."""
from __future__ import annotations

import datetime as dt

from app.sync import cursors

_NOW = dt.datetime(2026, 6, 27, 12, 0, 0, tzinfo=dt.timezone.utc)


def test_never_run_cursor_is_due():
    assert cursors.is_due(None, 900, _NOW) is True


def test_cursor_not_due_before_cadence_elapses():
    last = _NOW - dt.timedelta(seconds=300)
    assert cursors.is_due(last, 900, _NOW) is False


def test_cursor_due_once_cadence_elapses():
    last = _NOW - dt.timedelta(seconds=901)
    assert cursors.is_due(last, 900, _NOW) is True


def test_watermark_advances_to_the_latest_seen():
    result = cursors.advance_watermark(
        "2026-06-27T09:00:00Z",
        ["2026-06-27T09:30:00Z", "2026-06-27T10:15:00Z", "2026-06-27T09:45:00Z"],
    )
    assert result == "2026-06-27T10:15:00Z"


def test_watermark_never_moves_backward():
    # An overlap re-sweep that only re-sees older rows must not rewind the cursor.
    result = cursors.advance_watermark(
        "2026-06-27T10:15:00Z", ["2026-06-27T09:00:00Z", "2026-06-27T09:59:00Z"]
    )
    assert result == "2026-06-27T10:15:00Z"


def test_watermark_handles_mixed_offsets_by_instant_not_string():
    # 10:30-07:00 (= 17:30Z) is later than 18:00Z is false; compare by instant, not lexically.
    result = cursors.advance_watermark(None, ["2026-06-27T18:00:00Z", "2026-06-27T10:30:00-07:00"])
    assert result == "2026-06-27T18:00:00Z"


def test_empty_batch_keeps_current():
    assert cursors.advance_watermark("2026-06-27T10:00:00Z", []) == "2026-06-27T10:00:00Z"
    assert cursors.advance_watermark(None, []) is None
