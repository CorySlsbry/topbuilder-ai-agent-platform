"""Pure tests for `poll_tenant` (ADR 0010) — the change-feed poll loop, with stub clients and the
DB layer monkeypatched to an in-memory call log.

The load-bearing invariants under test:
  1. advance-after-enqueue: the cursor is written AFTER every row of its batch is enqueued (§4);
  2. creds absent (fail-closed client) -> that cursor records `error` (token unchanged) and the loop
     CONTINUES to the next cursor — never crashes the cron;
  3. cadence: a not-due cursor is skipped without touching any client;
  4. the QBO watermark advances monotonically to the max LastUpdatedTime seen.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import uuid

import pytest

from app.sync import service

TENANT = uuid.uuid4()
NOW = dt.datetime(2026, 6, 30, 12, 0, 0, tzinfo=dt.timezone.utc)


@contextlib.asynccontextmanager
async def _fake_tenant_session(tenant_id):
    yield object()


class _Log:
    """Ordered record of enqueue/cursor calls so ordering invariants are assertable."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def cursor_writes(self) -> list[tuple]:
        return [c for c in self.calls if c[0] == "cursor"]

    def enqueues(self) -> list[tuple]:
        return [c for c in self.calls if c[0] == "enqueue"]


@pytest.fixture()
def log(monkeypatch) -> _Log:
    record = _Log()

    async def fake_enqueue_event(session, *, source, event_type, external_id, payload):
        record.calls.append(("enqueue", source, external_id))
        return True

    async def fake_upsert_cursor(session, *, source, entity, cursor_token, status, now,
                                 error=None, cadence_seconds=None):
        record.calls.append(("cursor", source, entity, cursor_token, status, error))

    async def fake_mark_cursor_error(session, *, source, entity, now, error):
        # The error path preserves the DB token (never rewinds) — record a sentinel to prove it.
        record.calls.append(("cursor", source, entity, "<preserved>", "error", error))

    monkeypatch.setattr(service, "tenant_session", _fake_tenant_session)
    monkeypatch.setattr(service.events_repo, "enqueue_event", fake_enqueue_event)
    monkeypatch.setattr(service.sync_repo, "upsert_cursor", fake_upsert_cursor)
    monkeypatch.setattr(service.sync_repo, "mark_cursor_error", fake_mark_cursor_error)
    return record


def _cursors(monkeypatch, rows: list[dict]) -> None:
    async def fake_list_cursors(session):
        return rows

    monkeypatch.setattr(service.sync_repo, "list_cursors", fake_list_cursors)


def _cursor_row(source: str, entity: str, *, token: str | None = None,
                last_run_at: dt.datetime | None = None, cadence: int = 900) -> dict:
    return {"source": source, "entity": entity, "cursor_token": token,
            "cadence_seconds": cadence, "last_run_at": last_run_at, "last_status": "idle"}


class StubExportClient:
    """Deterministic ST /export stub: yields the configured pages in order."""

    def __init__(self, pages: list[tuple[list[dict], str | None, bool]]) -> None:
        self._pages = list(pages)
        self.requests: list[tuple[str, str, str | None]] = []

    async def fetch_export_page(self, module, entity, continue_from):
        self.requests.append((module, entity, continue_from))
        return self._pages.pop(0)


class StubCdcClient:
    def __init__(self, rows: list[tuple[str, dict]]) -> None:
        self._rows = rows
        self.requests: list[tuple[list[str], str | None]] = []

    async def fetch_cdc(self, entities=None, changed_since=None):
        self.requests.append((list(entities or []), changed_since))
        return self._rows


class FailClosedClient:
    """Mimics the real clients' credential gate (ADR 0005)."""

    async def fetch_export_page(self, module, entity, continue_from):
        raise RuntimeError("ServiceTitan live mode requires: SERVICETITAN_CLIENT_ID")

    async def fetch_cdc(self, entities=None, changed_since=None):
        raise RuntimeError("QuickBooks mode requires: QUICKBOOKS_REALM_ID")


class TestAdvanceAfterEnqueue:
    async def test_cursor_advances_only_after_the_page_is_enqueued(self, monkeypatch, log) -> None:
        _cursors(monkeypatch, [_cursor_row("servicetitan", "bill")])
        rows = [{"id": 1, "modifiedOn": "2026-06-30T10:00:00Z"},
                {"id": 2, "modifiedOn": "2026-06-30T10:05:00Z"}]
        st = StubExportClient([(rows, "tok-2", False)])

        result = await service.poll_tenant(TENANT, now=NOW, st_client=st)

        assert result["polled"] == 1
        # Both rows enqueued FIRST, then exactly one cursor write carrying the page's new token.
        assert [c[0] for c in log.calls] == ["enqueue", "enqueue", "cursor"]
        assert log.cursor_writes() == [("cursor", "servicetitan", "bill", "tok-2", "ok", None)]
        # The feed was asked from the persisted token (None = from origin).
        assert st.requests == [("accounting", "bill", None)]

    async def test_multi_page_advances_per_page(self, monkeypatch, log) -> None:
        _cursors(monkeypatch, [_cursor_row("servicetitan", "invoice", token="tok-0")])
        st = StubExportClient([
            ([{"id": 10, "modifiedOn": "2026-06-30T09:00:00Z"}], "tok-1", True),
            ([{"id": 11, "modifiedOn": "2026-06-30T09:30:00Z"}], "tok-2", False),
        ])

        result = await service.poll_tenant(TENANT, now=NOW, st_client=st)

        assert result["polled"] == 1
        # enqueue -> cursor(tok-1) -> enqueue -> cursor(tok-2): page-granular gap-free resume.
        assert [c[0] for c in log.calls] == ["enqueue", "cursor", "enqueue", "cursor"]
        assert [c[3] for c in log.cursor_writes()] == ["tok-1", "tok-2"]
        assert st.requests == [("accounting", "invoice", "tok-0"), ("accounting", "invoice", "tok-1")]


class TestCredsAbsentContinues:
    async def test_failed_cursor_records_error_and_the_loop_continues(self, monkeypatch, log) -> None:
        _cursors(monkeypatch, [
            _cursor_row("servicetitan", "bill", token="tok-st"),
            _cursor_row("quickbooks", "attachment"),
        ])
        qbo = StubCdcClient([("Attachable", {"Id": "9", "MetaData": {"LastUpdatedTime": "2026-06-30T08:00:00Z"}})])

        result = await service.poll_tenant(TENANT, now=NOW, st_client=FailClosedClient(), qbo_client=qbo)

        # ST cursor -> error with a clear message, token PRESERVED (never rewound); QBO polled fine.
        writes = log.cursor_writes()
        assert writes[0][1:] == ("servicetitan", "bill", "<preserved>", "error",
                                 "ServiceTitan live mode requires: SERVICETITAN_CLIENT_ID")
        assert writes[1][1:5] == ("quickbooks", "attachment", "2026-06-30T08:00:00Z", "ok")
        assert result["polled"] == 1
        assert [c["status"] for c in result["cursors"]] == ["error", "ok"]

    async def test_no_cursors_is_the_fixture_posture_noop(self, monkeypatch, log) -> None:
        _cursors(monkeypatch, [])
        result = await service.poll_tenant(TENANT, now=NOW)
        assert result["polled"] == 0
        assert "credentials" in result["note"]
        assert log.calls == []


class TestCadence:
    async def test_not_due_cursor_is_skipped_without_touching_the_client(self, monkeypatch, log) -> None:
        fresh = NOW - dt.timedelta(seconds=300)
        _cursors(monkeypatch, [_cursor_row("servicetitan", "bill", last_run_at=fresh, cadence=900)])
        st = StubExportClient([])  # popping would raise if it were ever called

        result = await service.poll_tenant(TENANT, now=NOW, st_client=st)

        assert result["polled"] == 0
        assert st.requests == []
        assert log.calls == []


class TestQuickBooksWatermark:
    async def test_watermark_advances_to_max_seen_after_enqueue(self, monkeypatch, log) -> None:
        _cursors(monkeypatch, [_cursor_row("quickbooks", "bill", token="2026-06-29T00:00:00Z")])
        qbo = StubCdcClient([
            ("Bill", {"Id": "1", "MetaData": {"LastUpdatedTime": "2026-06-30T07:00:00Z"}}),
            ("Bill", {"Id": "2", "MetaData": {"LastUpdatedTime": "2026-06-30T09:00:00Z"}}),
            ("Bill", {"Id": "3", "MetaData": {"LastUpdatedTime": "2026-06-30T08:00:00Z"}}),
        ])

        result = await service.poll_tenant(TENANT, now=NOW, qbo_client=qbo)

        assert result["polled"] == 1
        assert [c[0] for c in log.calls] == ["enqueue", "enqueue", "enqueue", "cursor"]
        assert log.cursor_writes() == [
            ("cursor", "quickbooks", "bill", "2026-06-30T09:00:00Z", "ok", None)
        ]
        # The poll asked CDC for the canonical entity's QBO name from the persisted watermark.
        assert qbo.requests == [(["Bill"], "2026-06-29T00:00:00Z")]
