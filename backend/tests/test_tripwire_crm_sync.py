"""Pure tests for the best-effort Salisbury-CRM sync (app/tripwires/crm_sync.py).

NO live CRM connection: the pure parts (name splitting, tag naming) are oracle-tested, and the
fail-closed gates (dsn unset, no buyer email) are proven to skip WITHOUT ever dialing asyncpg.
"""
from __future__ import annotations

import pytest

from app.config import Settings
from app.tripwires import crm_sync


class TestSplitName:
    def test_first_last(self) -> None:
        assert crm_sync.split_name("Sam Buyer") == ("Sam", "Buyer")

    def test_splits_on_first_space_only(self) -> None:
        assert crm_sync.split_name("Mary Jo Kopechne") == ("Mary", "Jo Kopechne")

    def test_single_token(self) -> None:
        assert crm_sync.split_name("Cher") == ("Cher", None)

    def test_none_and_blank(self) -> None:
        assert crm_sync.split_name(None) == (None, None)
        assert crm_sync.split_name("   ") == (None, None)

    def test_strips_whitespace(self) -> None:
        assert crm_sync.split_name("  Sam   Buyer  ") == ("Sam", "Buyer")


class TestTagNames:
    def test_oracle(self) -> None:
        assert crm_sync.tag_names("xray") == ["topbuilderai", "tripwire-xray-buyer"]

    def test_collections_sprint(self) -> None:
        assert crm_sync.tag_names("collections_sprint") == [
            "topbuilderai",
            "tripwire-collections_sprint-buyer",
        ]


class TestFailClosedGates:
    @pytest.fixture(autouse=True)
    def _no_network(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Any asyncpg.connect attempt in these tests is a test failure."""
        import asyncpg

        def _forbidden(*args, **kwargs):
            raise AssertionError("crm_sync must not dial the CRM in this test")

        monkeypatch.setattr(asyncpg, "connect", _forbidden)

    async def test_skips_when_dsn_unset(self) -> None:
        settings = Settings(crm_sync_db_url=None)
        ok = await crm_sync.sync_buyer(
            settings, email="person1@example.com", name="A B", product_key="xray", amount_cents=9700
        )
        assert ok is False

    async def test_skips_when_no_email(self) -> None:
        settings = Settings(crm_sync_db_url="postgresql://u:p@crm.example:5432/crm")
        ok = await crm_sync.sync_buyer(
            settings, email=None, name="A B", product_key="xray", amount_cents=9700
        )
        assert ok is False

    async def test_connect_failure_is_swallowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import asyncpg

        async def _down(*args, **kwargs):
            raise OSError("no route to host")

        monkeypatch.setattr(asyncpg, "connect", _down)
        settings = Settings(crm_sync_db_url="postgresql://u:p@crm.example:5432/crm")
        ok = await crm_sync.sync_buyer(
            settings, email="person1@example.com", name="A B", product_key="xray", amount_cents=9700
        )
        assert ok is False  # best-effort: never raises
