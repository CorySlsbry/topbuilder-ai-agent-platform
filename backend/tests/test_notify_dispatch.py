"""Pure tests for `notify_operators` — the fan-out that pushes an operator report to Slack + email.

Load-bearing invariants (reporting must NEVER break the thing being reported on):
  1. fail-closed config: no Slack webhook + no operator emails -> both channels 'skipped', no raise;
  2. the email channel uses the existing email_send client (fixture mode = offline) and reports 'sent';
  3. a per-event toggle set False short-circuits to {'status': 'disabled'} without touching a channel;
  4. a Slack transport error is swallowed -> {'slack': 'failed'} (best-effort), never propagates;
  5. an invalid kind is refused (defensive) without sending anything.

Slack is stubbed so no network is touched; the email path runs against the real FIXTURE client.
"""
from __future__ import annotations

from app.config import Settings
from app.notify import notifier


def _settings(**over) -> Settings:
    base = dict(
        env="dev",
        slack_webhook_url=None,
        operator_notify_emails="",
        email_send_mode="fixture",
        notify_on_signup=True,
        notify_on_chatbot=True,
        notify_on_bug=True,
        notify_on_feature=True,
        notify_on_question=True,
    )
    base.update(over)
    return Settings(**base)


_REQ = {"kind": "bug", "name": "Sam", "email": "person1@example.com",
        "message": "blank screen", "source": "in_app"}


class TestFailClosedConfig:
    async def test_nothing_configured_skips_both_channels_and_never_raises(self) -> None:
        result = await notifier.notify_operators(_settings(), dict(_REQ))
        assert result["slack"] == "skipped"
        assert result["email"] == "skipped"
        assert result["status"] == "ok"


class TestEmailChannel:
    async def test_email_sends_to_each_operator_via_the_fixture_client(self) -> None:
        result = await notifier.notify_operators(
            _settings(operator_notify_emails="person2@example.com, person3@example.com"),
            dict(_REQ),
        )
        assert result["email"] == "sent"
        assert result["email_count"] == 2
        assert result["slack"] == "skipped"


class TestSlackChannel:
    async def test_slack_posts_when_configured(self, monkeypatch) -> None:
        sent: list[tuple[str, dict]] = []

        async def fake_post(url: str, payload: dict) -> bool:
            sent.append((url, payload))
            return True

        monkeypatch.setattr(notifier, "_post_slack", fake_post)
        result = await notifier.notify_operators(
            _settings(slack_webhook_url="https://hooks.slack.example/T/B/X"),
            dict(_REQ),
        )
        assert result["slack"] == "sent"
        assert len(sent) == 1 and sent[0][0] == "https://hooks.slack.example/T/B/X"
        assert "blocks" in sent[0][1]

    async def test_slack_transport_failure_is_swallowed(self, monkeypatch) -> None:
        async def boom(url: str, payload: dict) -> bool:
            raise RuntimeError("connection reset")

        monkeypatch.setattr(notifier, "_post_slack", boom)
        result = await notifier.notify_operators(
            _settings(slack_webhook_url="https://hooks.slack.example/T/B/X"),
            dict(_REQ),
        )
        assert result["slack"] == "failed"
        assert result["status"] == "ok"  # the caller is never told the report failed


class TestPerEventToggle:
    async def test_toggle_off_disables_that_kind_without_touching_a_channel(self, monkeypatch) -> None:
        called = {"slack": False}

        async def fake_post(url: str, payload: dict) -> bool:
            called["slack"] = True
            return True

        monkeypatch.setattr(notifier, "_post_slack", fake_post)
        result = await notifier.notify_operators(
            _settings(
                slack_webhook_url="https://hooks.slack.example/T/B/X",
                operator_notify_emails="person2@example.com",
                notify_on_bug=False,
            ),
            dict(_REQ),  # kind == 'bug'
        )
        assert result["status"] == "disabled"
        assert called["slack"] is False


class TestInvalidKind:
    async def test_unknown_kind_is_refused_and_sends_nothing(self, monkeypatch) -> None:
        called = {"slack": False}

        async def fake_post(url: str, payload: dict) -> bool:
            called["slack"] = True
            return True

        monkeypatch.setattr(notifier, "_post_slack", fake_post)
        result = await notifier.notify_operators(
            _settings(slack_webhook_url="https://hooks.slack.example/T/B/X"),
            {**_REQ, "kind": "malware"},
        )
        assert result["status"] == "invalid_kind"
        assert called["slack"] is False
