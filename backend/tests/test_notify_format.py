"""Pure oracle tests for the operator-notification FORMATTERS.

`format_slack_message` and `format_email` are deterministic, network-free renderers: given an event
kind + who/what, they produce the Slack block payload and the (subject, html, text) email tuple. These
are what an operator actually reads, so they are pinned with hand-computed oracles: the kind label and
the reporter's email must always be visible so a report is never anonymous, HTML must be escaped so a
message can't inject markup into the operator's inbox, and the text fallback must carry the message.
"""
from __future__ import annotations

from app.notify import notifier


class TestFormatSlackMessage:
    def test_carries_kind_label_email_and_message(self) -> None:
        msg = notifier.format_slack_message(
            kind="bug",
            name="Sam Summit",
            email="person1@example.com",
            message="The dispatch board is blank after login",
            source="in_app",
        )
        # A Slack webhook payload always needs a top-level `text` fallback (notifications/screen
        # readers) plus the rich `blocks`. All the load-bearing facts appear in the fallback text.
        assert isinstance(msg["blocks"], list) and msg["blocks"]
        flat = msg["text"] + " " + str(msg["blocks"])
        assert "Bug" in flat  # human label for the kind
        assert "person1@example.com" in flat
        assert "The dispatch board is blank after login" in flat
        assert "Sam Summit" in flat

    def test_each_kind_has_a_distinct_human_label(self) -> None:
        labels = {
            k: notifier.format_slack_message(
                kind=k, name=None, email=None, message="x", source="in_app"
            )["text"]
            for k in ("signup", "chatbot", "bug", "feature", "question")
        }
        # No two kinds collapse to the same headline text (an operator can tell them apart).
        assert len({v.split("\n")[0] for v in labels.values()}) == 5

    def test_missing_name_and_email_render_without_crashing(self) -> None:
        msg = notifier.format_slack_message(
            kind="question", name=None, email=None, message="How do I connect QuickBooks?",
            source="in_app",
        )
        assert "How do I connect QuickBooks?" in msg["text"] + str(msg["blocks"])
        assert "anonymous" in (msg["text"] + str(msg["blocks"])).lower()


class TestFormatEmail:
    def test_subject_and_body_contain_kind_and_reporter_email(self) -> None:
        subject, html, text = notifier.format_email(
            kind="feature",
            name="Alex",
            email="person2@example.com",
            message="Please add a 13-week cash flow export",
            source="in_app",
        )
        assert "Feature" in subject
        assert "person2@example.com" in text and "person2@example.com" in html
        assert "Please add a 13-week cash flow export" in text
        assert "Please add a 13-week cash flow export" in html

    def test_html_escapes_the_message_body(self) -> None:
        # A reporter-controlled message must never inject raw markup into the operator's HTML email.
        _subject, html, _text = notifier.format_email(
            kind="bug", name="x", email="person3@example.com",
            message="<script>alert(1)</script>", source="in_app",
        )
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html

    def test_subject_differs_per_kind(self) -> None:
        subjects = {
            k: notifier.format_email(kind=k, name=None, email=None, message="x", source="in_app")[0]
            for k in ("signup", "chatbot", "bug", "feature", "question")
        }
        assert len(set(subjects.values())) == 5
