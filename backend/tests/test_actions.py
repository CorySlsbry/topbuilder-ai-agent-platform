"""Unit tests for the action layer (ADR 0007): executors, gating, idempotency keys. No DB, no network."""
from __future__ import annotations

import uuid

import pytest

from app.actions import executors as ex
from app.actions.executors import ActionError
from app.actions.service import _idempotency_key
from app.config import Settings

FIXTURE = Settings(servicetitan_mode="fixture", actions_enabled=True, actions_allowed_kinds="book_appointment")
LIVE = Settings(servicetitan_mode="live", actions_enabled=True, actions_allowed_kinds="book_appointment")


class TestBookAppointmentExecutor:
    async def test_fixture_returns_deterministic_confirmation(self) -> None:
        out = await ex.execute(
            "book_appointment", {"intake_id": "B01", "trade": "hvac", "proposed_date": "2026-06-06"}, FIXTURE
        )
        assert out["external_ref"] == "st-appt-B01"
        assert out["status"] == "booked"
        assert out["mode"] == "fixture"

    async def test_requires_intake_id(self) -> None:
        with pytest.raises(ActionError):
            await ex.execute("book_appointment", {"trade": "hvac"}, FIXTURE)

    async def test_live_write_is_fail_closed(self) -> None:
        # Until the real ST booking write is wired, live mode must refuse rather than pretend.
        with pytest.raises(ActionError):
            await ex.execute("book_appointment", {"intake_id": "B01"}, LIVE)

    async def test_unknown_kind_raises(self) -> None:
        with pytest.raises(ActionError):
            await ex.execute("delete_everything", {}, FIXTURE)


class TestUndoExecutor:
    async def test_book_appointment_is_undoable(self) -> None:
        assert ex.is_undoable("book_appointment") is True
        out = await ex.undo("book_appointment", {"intake_id": "B01"}, {"external_ref": "st-appt-B01"}, FIXTURE)
        assert out["status"] == "canceled"
        assert out["external_ref"] == "st-appt-B01"

    def test_unknown_kind_not_undoable(self) -> None:
        assert ex.is_undoable("delete_everything") is False


class TestGating:
    def test_allowed_kind_is_executable(self) -> None:
        assert ex.is_executable_kind("book_appointment", FIXTURE) is True

    def test_kind_off_allowlist_is_not_executable(self) -> None:
        assert ex.is_executable_kind("book_appointment", Settings(actions_allowed_kinds="something_else")) is False

    def test_unknown_kind_is_not_executable(self) -> None:
        assert ex.is_executable_kind("delete_everything", FIXTURE) is False


class TestIdempotencyKey:
    def test_caller_supplied_key_wins(self) -> None:
        assert _idempotency_key("book_appointment", None, {"intake_id": "B01"}, "my-key") == "my-key"

    def test_derived_from_natural_key(self) -> None:
        rid = uuid.UUID("11111111-1111-1111-1111-111111111111")
        assert _idempotency_key("book_appointment", rid, {"intake_id": "B01"}, None) == f"book_appointment:{rid}:B01"

    def test_derived_hash_is_stable_and_distinct(self) -> None:
        k1 = _idempotency_key("k", None, {"a": 1}, None)
        k2 = _idempotency_key("k", None, {"a": 1}, None)
        k3 = _idempotency_key("k", None, {"a": 2}, None)
        assert k1 == k2
        assert k1 != k3
