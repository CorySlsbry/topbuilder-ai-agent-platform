"""Pure oracle test for the daily-digest formatter.

`format_digest` rolls the last-24h support requests (already fetched + counted by kind) into ONE
Slack payload + one (subject, html, text) email. The oracle: a mixed set of 6 requests across 3 kinds
must render a per-kind count line for every present kind, the total, and a headline that marks it as a
digest so an operator doesn't confuse it with a single live alert.
"""
from __future__ import annotations

from app.notify import notifier


def _counts() -> dict[str, int]:
    # 3 bugs, 2 signups, 1 feature = 6 total; chatbot/question absent.
    return {"bug": 3, "signup": 2, "feature": 1, "chatbot": 0, "question": 0}


class TestFormatDigest:
    def test_slack_digest_lists_every_present_kind_and_total(self) -> None:
        payload = notifier.format_digest(_counts(), total=6, window_hours=24)
        flat = payload["text"] + " " + str(payload["blocks"])
        assert "digest" in flat.lower()
        assert "6" in flat  # total
        # Present kinds carry their count; both count and label appear.
        assert "3" in flat and "Bug report" in flat
        assert "2" in flat and "New signup" in flat
        assert "1" in flat and "Feature request" in flat

    def test_email_digest_subject_marks_it_a_digest_with_the_total(self) -> None:
        subject, html, text = notifier.format_digest_email(_counts(), total=6, window_hours=24)
        assert "digest" in subject.lower()
        assert "6" in subject or "6" in text
        assert "Bug report" in text and "3" in text

    def test_zero_activity_digest_still_renders(self) -> None:
        empty = {k: 0 for k in ("signup", "chatbot", "bug", "feature", "question")}
        payload = notifier.format_digest(empty, total=0, window_hours=24)
        assert "0" in payload["text"] + str(payload["blocks"])
