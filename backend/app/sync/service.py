"""Orchestration for the event-detection layer (ADR 0010): detect -> enqueue, then drain -> propose.

The planning logic (`parse_entity`, the per-entity handlers, `plan_event`) is pure and unit-tested in
isolation; `enqueue_events` / `drain_tenant` / `poll_tenant` are the thin DB + gate wiring. The drain
runs under the propose-only system principal, so every detected action is left **proposed** for a
human (approve-first); money/legal kinds are `ALWAYS_HITL` in the gate regardless.
"""
from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from app.actions import service as actions_service
from app.actions.schemas import ProposeActionIn
from app.db import tenant_session
from app.repositories import events as events_repo
from app.repositories import sync as sync_repo
from app.sync import cursors as cursor_algebra
from app.sync import normalize, router
from app.sync.models import SOURCE_QUICKBOOKS, SOURCE_SERVICETITAN, InboundEvent
from app.sync.principal import system_principal

MAX_ATTEMPTS = 5
BACKOFF_BASE_SECONDS = 60
# Bounds one poll tick per cursor; the persisted continueFrom resumes the remainder next tick.
MAX_EXPORT_PAGES_PER_TICK = 10


# --- pure planning ---------------------------------------------------------------------------------
def parse_entity(event_type: str) -> str:
    """`accounting.bill.created` -> `bill`. The canonical event_type encodes module.entity.verb."""
    parts = event_type.split(".")
    return parts[1] if len(parts) >= 2 else ""


def _amount_cents(row: dict) -> int:
    if row.get("amount_cents") is not None:
        try:
            return int(row["amount_cents"])
        except (TypeError, ValueError):
            return 0
    # Bill TOTAL fields only — never `balance` (the remaining amount), which would post a partial.
    for key in ("total", "TotalAmt", "amount"):
        value = row.get(key)
        if value is not None:
            try:
                return int(round(float(value) * 100))
            except (TypeError, ValueError):
                continue
    return 0


def _vendor(row: dict) -> str | None:
    value = row.get("vendor") or row.get("vendorName")
    if value:
        return str(value)
    ref = row.get("VendorRef")
    if isinstance(ref, dict):
        return ref.get("name") or ref.get("value")
    return None


def _handle_bill(envelope: dict, natural_key: str) -> ProposeActionIn | None:
    """A vendor bill -> a job-costed A/P draft proposal, only if it ties to a job. No job match ->
    None (advisory / needs-human): the `create_ap_draft` executor requires a `job_ref`, and we never
    guess an allocation."""
    row = envelope.get("row") or {}
    job_ref = envelope.get("job_ref")
    if not job_ref:
        return None
    bill_id = row.get("id") or row.get("Id") or envelope.get("provider_id")
    if not bill_id:
        return None
    return ProposeActionIn(
        agent="documents",  # create_ap_draft's OWNING agent (KIND_OWNER) — must match or inbox/narration disagree
        kind="create_ap_draft",
        params={
            "bill_id": str(bill_id),
            "job_ref": str(job_ref),
            "amount_cents": _amount_cents(row),
            "vendor": _vendor(row),
            "doc_number": row.get("docNumber") or row.get("DocNumber"),
            # Ties the gate idempotency_key to the event so a re-drain never double-proposes.
            "intake_id": natural_key,
        },
    )


# entity -> a pure handler that builds the proposal (or None for advisory). Phase 1 wires bills; other
# entities route to their agent as advisory until their handler is added (Phase 2).
_HANDLERS: dict[str, Callable[[dict, str], ProposeActionIn | None]] = {
    "bill": _handle_bill,
    "purchase": _handle_bill,
}


@dataclass(frozen=True)
class EventPlan:
    outcome: str  # "propose" | "advisory" | "no_route"
    agent: str | None = None
    proposal: ProposeActionIn | None = None
    note: str | None = None


def plan_event(*, source: str, event_type: str, external_id: str | None, payload: dict) -> EventPlan:
    """Pure: a claimed event row -> what the drain should do. `external_id` is the event's natural_key
    (it ties the proposal's idempotency to this exact change)."""
    entity = parse_entity(event_type)
    decision = router.route(source, entity, event_type)
    if decision is None:
        return EventPlan(outcome="no_route", note=f"no route for {source}/{entity}")
    handler = _HANDLERS.get(entity)
    if handler is None:
        return EventPlan(outcome="advisory", agent=decision.agent)
    proposal = handler(payload, external_id or "")
    if proposal is None:
        return EventPlan(outcome="advisory", agent=decision.agent, note="no actionable match (needs human)")
    return EventPlan(outcome="propose", agent=decision.agent, proposal=proposal)


# --- detection (enqueue) ---------------------------------------------------------------------------
def _envelope(event: InboundEvent) -> dict:
    return {
        "entity": event.entity,
        "provider_id": event.provider_id,
        "job_ref": event.job_ref,
        "occurred_at": event.occurred_at,
        "row": event.payload,
    }


async def enqueue_events(tenant_id: uuid.UUID, events: list[InboundEvent]) -> int:
    """Insert normalized events into the inbox (dedupe by the non-null natural key). Returns the
    number newly inserted (duplicates collapse)."""
    inserted = 0
    async with tenant_session(tenant_id) as session:
        for event in events:
            ok = await events_repo.enqueue_event(
                session,
                source=event.source,
                event_type=event.event_type,
                external_id=event.natural_key,
                payload=_envelope(event),
            )
            inserted += 1 if ok else 0
    return inserted


def _default_st_client():
    from app.config import get_settings
    from app.integrations.servicetitan.export_client import ServiceTitanExportClient

    return ServiceTitanExportClient(get_settings())


def _default_qbo_client():
    from app.config import get_settings
    from app.integrations.quickbooks.cdc_client import QuickBooksCdcClient

    return QuickBooksCdcClient(get_settings())


async def _enqueue_and_advance(
    tenant_id: uuid.UUID,
    events: list[InboundEvent],
    *,
    source: str,
    entity: str,
    cursor_token: str | None,
    now: dt.datetime,
) -> int:
    """ONE transaction: enqueue the batch, THEN advance the cursor — the ADR-0010 §4 invariant. A
    crash before commit leaves the old cursor, so the next tick re-pulls (dedupe collapses the
    overlap); the cursor can never advance past rows that were not durably enqueued."""
    inserted = 0
    async with tenant_session(tenant_id) as session:
        for event in events:
            ok = await events_repo.enqueue_event(
                session,
                source=event.source,
                event_type=event.event_type,
                external_id=event.natural_key,
                payload=_envelope(event),
            )
            inserted += 1 if ok else 0
        await sync_repo.upsert_cursor(
            session, source=source, entity=entity, cursor_token=cursor_token, status="ok", now=now
        )
    return inserted


async def _poll_servicetitan(
    tenant_id: uuid.UUID, client, entity: str, cursor_token: str | None, now: dt.datetime
) -> dict:
    """Pull the ST `/export` change-feed for one entity, page by page. Each page is enqueued and the
    cursor advanced to that page's `continueFrom` before the next fetch (page-granular resume)."""
    from app.integrations.servicetitan import export_client as st_export

    module = st_export.export_module_for(entity)
    if module is None:
        raise RuntimeError(f"no ServiceTitan export feed mapped for entity '{entity}'")
    pages = enqueued = skipped = 0
    token, has_more = cursor_token, True
    while has_more and pages < MAX_EXPORT_PAGES_PER_TICK:
        rows, token, has_more = await client.fetch_export_page(module, entity, token)
        events: list[InboundEvent] = []
        for row in rows:
            try:
                events.append(normalize.normalize_st_export_row(entity, row))
            except ValueError:
                skipped += 1  # a row with no id cannot be deduped — counted, never guessed
        enqueued += await _enqueue_and_advance(
            tenant_id, events, source=SOURCE_SERVICETITAN, entity=entity, cursor_token=token, now=now
        )
        pages += 1
    return {"source": SOURCE_SERVICETITAN, "entity": entity, "status": "ok", "pages": pages,
            "enqueued": enqueued, "skipped_no_id": skipped, "has_more": has_more}


async def _poll_quickbooks(
    tenant_id: uuid.UUID, client, entity: str, cursor_token: str | None, now: dt.datetime
) -> dict:
    """Pull QBO CDC for one entity; the cursor is a monotonic `LastUpdatedTime` watermark (never
    rewinds on an overlap re-sweep), advanced only after the batch is enqueued."""
    from app.integrations.quickbooks import cdc_client as qbo_cdc

    qbo_name = qbo_cdc.qbo_entity_for(entity)
    if qbo_name is None:
        raise RuntimeError(f"no QuickBooks CDC entity mapped for '{entity}'")
    rows = await client.fetch_cdc([qbo_name], changed_since=cursor_token)
    events: list[InboundEvent] = []
    seen: list[str] = []
    for name, row in rows:
        try:
            event = normalize.normalize_qbo_row(name, row)
        except ValueError:
            continue  # a CDC row with no/empty Id can't be deduped — skip it, never abort the batch
        if event is None:
            continue
        events.append(event)
        if event.external_modified_at:
            seen.append(event.external_modified_at)
    new_token = cursor_algebra.advance_watermark(cursor_token, seen)
    enqueued = await _enqueue_and_advance(
        tenant_id, events, source=SOURCE_QUICKBOOKS, entity=entity, cursor_token=new_token, now=now
    )
    return {"source": SOURCE_QUICKBOOKS, "entity": entity, "status": "ok", "enqueued": enqueued}


async def poll_tenant(
    tenant_id: uuid.UUID, *, now: dt.datetime | None = None, st_client=None, qbo_client=None
) -> dict:
    """Detect new ServiceTitan/QuickBooks items via the change-feed and enqueue them.

    Iterates the tenant's due `sync_cursor` rows and pulls the matching feed (ST `/export` /
    QBO CDC). Both clients FAIL CLOSED without connected credentials (ADR 0005): the failure is
    recorded on that cursor (`last_status='error'`) and the loop continues — a tenant without creds
    (the fixture/demo posture, which seeds no cursors) polls nothing and never crashes the cron.
    `st_client`/`qbo_client` are injectable for tests; defaults build from Settings.
    """
    from app.config import get_settings

    settings = get_settings()
    now = now or dt.datetime.now(dt.timezone.utc)
    async with tenant_session(tenant_id) as session:
        cursor_rows = await sync_repo.list_cursors(session)
    if not cursor_rows:
        return {"tenant": str(tenant_id), "polled": 0,
                "note": "no sync cursors configured — live change-feed polling requires connected "
                        "ServiceTitan/QuickBooks credentials"}
    polled = 0
    results: list[dict] = []
    for cur in cursor_rows:
        if not cursor_algebra.is_due(cur.get("last_run_at"), int(cur.get("cadence_seconds") or 900), now):
            continue
        source, entity = cur["source"], cur["entity"]
        try:
            if source == SOURCE_SERVICETITAN:
                if st_client is None:
                    # Only auto-build (and only in live mode): fixture posture must never make a live
                    # API call even if creds happen to be set. An injected client is the caller's call.
                    if settings.servicetitan_mode.lower() != "live":
                        raise RuntimeError("servicetitan_mode is not 'live' — change-feed polling is fixture-gated")
                    st_client = _default_st_client()  # cached across this tenant's cursors this tick
                results.append(await _poll_servicetitan(tenant_id, st_client, entity, cur.get("cursor_token"), now))
            elif source == SOURCE_QUICKBOOKS:
                if qbo_client is None:
                    if settings.accounting_mode.lower() != "live":
                        raise RuntimeError("accounting_mode is not 'live' — QBO CDC polling is fixture-gated")
                    qbo_client = _default_qbo_client()
                results.append(await _poll_quickbooks(tenant_id, qbo_client, entity, cur.get("cursor_token"), now))
            else:
                raise RuntimeError(f"unknown detection source '{source}'")
            polled += 1
        except Exception as exc:  # noqa: BLE001 — creds absent / feed down: record + continue, never crash
            # Mark the cursor errored WITHOUT rewinding its token: for ServiceTitan, _enqueue_and_advance
            # has already committed page-granular advances (pages 1..k) before a mid-tick failure, and
            # writing the stale tick-start token here would re-pull + re-propose those pages next tick.
            async with tenant_session(tenant_id) as session:
                await sync_repo.mark_cursor_error(session, source=source, entity=entity, now=now, error=str(exc))
            results.append({"source": source, "entity": entity, "status": "error", "error": str(exc)})
    return {"tenant": str(tenant_id), "polled": polled, "cursors": results}


# --- drain (route -> propose) ----------------------------------------------------------------------
async def drain_tenant(tenant_id: uuid.UUID, *, limit: int = 50, now: dt.datetime | None = None) -> dict:
    """Claim due events for one tenant, route each, and PROPOSE through the gate (system principal =
    propose-only). A poison event is retried with backoff and dead-lettered past the ceiling, never
    blocking its siblings."""
    now = now or dt.datetime.now(dt.timezone.utc)
    async with tenant_session(tenant_id) as session:
        claimed = await sync_repo.claim_for_processing(session, limit=limit, now=now)

    principal = system_principal(tenant_id)
    counts = {"claimed": len(claimed), "proposed": 0, "advisory": 0, "no_route": 0, "failed": 0}
    for row in claimed:
        try:
            plan = plan_event(
                source=row["source"],
                event_type=row["event_type"],
                external_id=row.get("external_id"),
                payload=row["payload"],
            )
            if plan.outcome == "propose" and plan.proposal is not None:
                await actions_service.propose_action(principal, plan.proposal)
                counts["proposed"] += 1
            elif plan.outcome == "no_route":
                counts["no_route"] += 1
            else:
                counts["advisory"] += 1
            async with tenant_session(tenant_id) as session:
                await sync_repo.complete_event(session, event_id=row["id"])
        except Exception as exc:  # noqa: BLE001 — one poison event must not stop the batch
            counts["failed"] += 1
            await _on_failure(tenant_id, row, exc, now)
    return counts


async def _on_failure(tenant_id: uuid.UUID, row: dict, exc: Exception, now: dt.datetime) -> None:
    attempts = int(row.get("retry_count") or 0)  # already incremented at claim
    async with tenant_session(tenant_id) as session:
        if attempts >= MAX_ATTEMPTS:
            await sync_repo.dead_letter_event(
                session,
                event_id=row["id"],
                source=row["source"],
                event_type=row["event_type"],
                external_id=row.get("external_id"),
                payload=row.get("payload") or {},
                attempts=attempts,
                error=str(exc),
            )
        else:
            await sync_repo.retry_event(
                session,
                event_id=row["id"],
                error=str(exc),
                backoff_seconds=BACKOFF_BASE_SECONDS * attempts,
                now=now,
            )
