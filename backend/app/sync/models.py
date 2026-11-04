"""Canonical contract for the event-detection layer (ADR 0010).

`InboundEvent` is the one normalized shape every detection source (ST /export row, QBO CDC row, a
ServiceTitan or QuickBooks webhook payload, or an in-house emit) collapses to before it hits the
inbox. `RouteDecision` is the pure routing verdict the drain worker acts on. Both are frozen so they
behave as values in the pure tests.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Detection sources (the `source` column on event_queue).
SOURCE_SERVICETITAN = "servicetitan"
SOURCE_QUICKBOOKS = "quickbooks"
SOURCE_INAPP = "inapp"


def build_natural_key(source: str, entity: str, provider_id: str, modified_at: str | None) -> str:
    """The dedupe key written to `event_queue.external_id` (NON-NULL by construction).

    Embedding the `modifiedOn`/`LastUpdatedTime` watermark means an unchanged item re-seen (a poll
    overlap or ServiceTitan `includeRecentChanges` repeat) collapses to the same key, while an edited
    item (new watermark) is a genuinely new event. The existing partial-unique index
    (tenant_id, source, external_id) WHERE external_id IS NOT NULL then makes enqueue idempotent.
    """
    return f"{source}:{entity}:{provider_id}:{modified_at or 'na'}"


@dataclass(frozen=True)
class InboundEvent:
    """One normalized new/changed item, ready to enqueue."""

    source: str
    entity: str  # canonical lowercase, e.g. "bill", "invoice", "payment", "po_receipt", "attachment"
    event_type: str  # canonical dotted, e.g. "accounting.bill.created"
    provider_id: str  # the raw provider id (ST id / QBO Id)
    natural_key: str  # source:entity:provider_id:modified_at — written as external_id (non-null)
    external_modified_at: str | None = None  # the source's modifiedOn / MetaData.LastUpdatedTime
    occurred_at: str | None = None  # when the change happened, if distinct from modified_at
    job_ref: str | None = None  # resolved job/project reference if derivable
    payload: dict = field(default_factory=dict)

    @classmethod
    def of(
        cls,
        *,
        source: str,
        entity: str,
        event_type: str,
        provider_id: str,
        modified_at: str | None = None,
        occurred_at: str | None = None,
        job_ref: str | None = None,
        payload: dict | None = None,
    ) -> "InboundEvent":
        """Build an event, computing the natural key. `provider_id` must be a stable, non-empty id."""
        if not provider_id:
            raise ValueError("InboundEvent requires a non-empty provider_id for idempotent dedupe")
        return cls(
            source=source,
            entity=entity,
            event_type=event_type,
            provider_id=str(provider_id),
            natural_key=build_natural_key(source, entity, str(provider_id), modified_at),
            external_modified_at=modified_at,
            occurred_at=occurred_at or modified_at,
            job_ref=job_ref,
            payload=payload or {},
        )


@dataclass(frozen=True)
class RouteDecision:
    """Where a normalized event goes. `action_kind is None` means advisory-only (no write proposed)."""

    agent: str
    action_kind: str | None = None

    @property
    def advisory_only(self) -> bool:
        return self.action_kind is None
