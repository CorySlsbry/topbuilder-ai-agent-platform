"""Pure tests for the app-owned `/v1/sync/emit` producer (ADR 0010).

Emit is a write surface (it seeds the detection inbox), so it carries the runner bar — the same
role gate as triggering a run — and stamps the emitting user into the event payload for the audit
trail. The DB layer is monkeypatched; no infrastructure.
"""
from __future__ import annotations

import inspect
import uuid

import pytest
from fastapi import HTTPException

from app.api import deps, routes_sync
from app.security import Principal


def _principal(role: str = "analyst") -> Principal:
    return Principal(
        tenant_id=uuid.uuid4(), user_id=uuid.uuid4(), email="person1@example.com", role=role
    )


def test_emit_requires_the_runner_bar_not_just_any_principal() -> None:
    dependency = inspect.signature(routes_sync.emit_event).parameters["principal"].default
    assert dependency.dependency is deps.require_runner


async def test_emit_stamps_the_emitting_user_into_the_payload(monkeypatch) -> None:
    captured: dict = {}

    async def fake_enqueue_events(tenant_id, events):
        captured["tenant_id"] = tenant_id
        captured["events"] = events
        return 1

    monkeypatch.setattr(routes_sync.service, "enqueue_events", fake_enqueue_events)
    principal = _principal()
    body = routes_sync.SyncEmitIn(
        entity="attachment", provider_id="blob-77", payload={"file_name": "receipt.jpg"}
    )

    result = await routes_sync.emit_event(body, principal)

    assert result["status"] == "queued"
    assert captured["tenant_id"] == principal.tenant_id
    (event,) = captured["events"]
    assert event.payload["emitted_by"] == str(principal.user_id)
    assert event.payload["file_name"] == "receipt.jpg"  # the caller's payload is preserved
    assert event.natural_key == result["natural_key"]


async def test_emit_rejects_unknown_entities(monkeypatch) -> None:
    async def fake_enqueue_events(tenant_id, events):  # pragma: no cover — must not be reached
        raise AssertionError("unknown entity must be rejected before enqueue")

    monkeypatch.setattr(routes_sync.service, "enqueue_events", fake_enqueue_events)
    body = routes_sync.SyncEmitIn(entity="not-a-thing", provider_id="x-1")

    with pytest.raises(HTTPException) as excinfo:
        await routes_sync.emit_event(body, _principal())
    assert excinfo.value.status_code == 422
