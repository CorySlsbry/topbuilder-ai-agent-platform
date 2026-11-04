"""Pure tests for the tripwire order-capture service (app/tripwires/service.py).

No DB, no network: persistence is faked by monkeypatching the service's `_record_order` /
`_mark_crm_synced` seams, Slack by patching `_post_slack`, CRM by patching the crm_sync module.
Covers the load-bearing guarantees:
  * a valid checkout.session.completed inserts ONCE and fires Slack + CRM;
  * a duplicate stripe_session_id (repo returns None) skips ALL side effects;
  * an unknown product_key is rejected (logged) and never inserted;
  * a Slack/CRM failure never loses the order or raises to the caller;
  * the Slack formatter oracle (product label + $ amount + buyer).
"""
from __future__ import annotations

import uuid

import pytest

from app.config import Settings
from app.tripwires import service


def _event(
    *,
    session_id: str = "cs_test_123",
    product_key: str | None = "xray",
    email: str | None = "buyer@example.com",
    name: str | None = "Sam Buyer",
    amount_total: int = 9700,
    metadata_on: str = "session",
) -> dict:
    obj: dict = {
        "id": session_id,
        "object": "checkout.session",
        "payment_intent": "pi_test_456",
        "amount_total": amount_total,
        "currency": "usd",
        "customer_details": {"email": email, "name": name},
        "metadata": {},
    }
    if product_key is not None:
        if metadata_on == "session":
            obj["metadata"] = {"product_key": product_key}
        elif metadata_on == "payment_link":
            obj["payment_link"] = {"id": "plink_1", "metadata": {"product_key": product_key}}
    return {"id": "evt_test_1", "type": "checkout.session.completed", "data": {"object": obj}}


@pytest.fixture()
def settings() -> Settings:
    return Settings(
        slack_webhook_url="https://hooks.slack.example/T/x", tripwire_slack_enabled=True
    )


@pytest.fixture()
def seams(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Fake every impure seam; record calls."""
    calls: dict = {"record": [], "slack": [], "crm": [], "mark": []}
    order_id = uuid.uuid4()

    async def fake_record(**kwargs):
        calls["record"].append(kwargs)
        return {"id": order_id, **kwargs}

    async def fake_post_slack(url, payload):
        calls["slack"].append((url, payload))
        return True

    async def fake_crm(settings, **kwargs):
        calls["crm"].append(kwargs)
        return True

    async def fake_mark(order_id):
        calls["mark"].append(order_id)

    monkeypatch.setattr(service, "_record_order", fake_record)
    monkeypatch.setattr(service, "_post_slack", fake_post_slack)
    monkeypatch.setattr(service.crm_sync, "sync_buyer", fake_crm)
    monkeypatch.setattr(service, "_mark_crm_synced", fake_mark)
    calls["order_id"] = order_id
    return calls


class TestSlackFormatter:
    def test_oracle_xray(self) -> None:
        payload = service.format_tripwire_slack("xray", "buyer@example.com", "Sam Buyer", 9700)
        assert isinstance(payload, dict)
        text = payload["text"]
        assert "Margin Leakage X-Ray" in text
        assert "$97" in text
        assert "Sam Buyer" in text and "buyer@example.com" in text
        assert payload.get("blocks")  # rich message, not just a bare string

    def test_oracle_scorecard_amount(self) -> None:
        payload = service.format_tripwire_slack("scorecard_trial", "person1@example.com", None, 2700)
        assert "$27" in payload["text"]
        assert service.PRODUCTS["scorecard_trial"]["label"] in payload["text"]

    def test_non_whole_dollar_amounts_keep_cents(self) -> None:
        payload = service.format_tripwire_slack("xray", "person1@example.com", None, 9750)
        assert "$97.50" in payload["text"]

    def test_unknown_key_degrades_to_the_key(self) -> None:
        # The formatter is total: it never raises on an unexpected key (defense in depth; the
        # handler has already validated). It falls back to the raw key as the label.
        payload = service.format_tripwire_slack("mystery", "person1@example.com", None, 100)
        assert "mystery" in payload["text"]


class TestHandleCheckoutCompleted:
    async def test_valid_event_inserts_once_and_fires_side_effects(
        self, settings: Settings, seams: dict
    ) -> None:
        result = await service.handle_checkout_completed(_event(), settings)
        assert result["status"] == "recorded"
        assert len(seams["record"]) == 1
        rec = seams["record"][0]
        assert rec["product_key"] == "xray"
        assert rec["stripe_session_id"] == "cs_test_123"
        assert rec["stripe_payment_intent"] == "pi_test_456"
        assert rec["stripe_event_id"] == "evt_test_1"
        assert rec["email"] == "buyer@example.com"
        assert rec["amount_cents"] == 9700
        assert len(seams["slack"]) == 1
        assert len(seams["crm"]) == 1
        assert seams["mark"] == [seams["order_id"]]  # crm ok -> crm_synced_at stamped

    async def test_duplicate_session_skips_all_side_effects(
        self, settings: Settings, seams: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def dup_record(**kwargs):
            seams["record"].append(kwargs)
            return None  # ON CONFLICT DO NOTHING -> no row

        monkeypatch.setattr(service, "_record_order", dup_record)
        result = await service.handle_checkout_completed(_event(), settings)
        assert result["status"] == "duplicate"
        assert len(seams["record"]) == 1
        assert seams["slack"] == []
        assert seams["crm"] == []
        assert seams["mark"] == []

    async def test_unknown_product_key_is_rejected_not_inserted(
        self, settings: Settings, seams: dict
    ) -> None:
        result = await service.handle_checkout_completed(
            _event(product_key="free_money"), settings
        )
        assert result["status"] == "rejected"
        assert seams["record"] == []
        assert seams["slack"] == []

    async def test_missing_product_key_is_rejected(self, settings: Settings, seams: dict) -> None:
        result = await service.handle_checkout_completed(_event(product_key=None), settings)
        assert result["status"] == "rejected"
        assert seams["record"] == []

    async def test_product_key_falls_back_to_payment_link_metadata(
        self, settings: Settings, seams: dict
    ) -> None:
        result = await service.handle_checkout_completed(
            _event(product_key="collections_sprint", metadata_on="payment_link"), settings
        )
        assert result["status"] == "recorded"
        assert seams["record"][0]["product_key"] == "collections_sprint"

    async def test_missing_session_id_is_rejected(self, settings: Settings, seams: dict) -> None:
        event = _event()
        del event["data"]["object"]["id"]
        result = await service.handle_checkout_completed(event, settings)
        assert result["status"] == "rejected"
        assert seams["record"] == []

    async def test_slack_failure_never_loses_the_order(
        self, settings: Settings, seams: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def boom(url, payload):
            raise RuntimeError("slack down")

        monkeypatch.setattr(service, "_post_slack", boom)
        result = await service.handle_checkout_completed(_event(), settings)
        assert result["status"] == "recorded"  # no exception escaped
        assert len(seams["record"]) == 1
        assert result["slack"] == "failed"
        assert len(seams["crm"]) == 1  # CRM still attempted after a Slack failure

    async def test_crm_failure_never_loses_the_order(
        self, settings: Settings, seams: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def boom(settings, **kwargs):
            raise RuntimeError("crm down")

        monkeypatch.setattr(service.crm_sync, "sync_buyer", boom)
        result = await service.handle_checkout_completed(_event(), settings)
        assert result["status"] == "recorded"
        assert result["crm"] == "failed"
        assert seams["mark"] == []  # not stamped when the sync failed

    async def test_slack_disabled_toggle_skips_slack(
        self, seams: dict
    ) -> None:
        settings = Settings(
            slack_webhook_url="https://hooks.slack.example/T/x", tripwire_slack_enabled=False
        )
        result = await service.handle_checkout_completed(_event(), settings)
        assert result["status"] == "recorded"
        assert seams["slack"] == []
        assert result["slack"] == "skipped"

    async def test_no_webhook_url_skips_slack(self, seams: dict) -> None:
        settings = Settings(slack_webhook_url=None)
        result = await service.handle_checkout_completed(_event(), settings)
        assert result["status"] == "recorded"
        assert seams["slack"] == []

    async def test_persist_failure_returns_error_without_raising(
        self, settings: Settings, seams: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def boom(**kwargs):
            raise RuntimeError("db down")

        monkeypatch.setattr(service, "_record_order", boom)
        result = await service.handle_checkout_completed(_event(), settings)
        assert result["status"] == "error"
        assert seams["slack"] == []  # no alert for an order we could not record
