"""Domain models for the Email agent (dependency-free, stdlib only).

An `EmailMessage` is the structured record of one unread inbox email (the connector/extraction layer
— Gmail/Microsoft 365 when live — hands us these fields, exactly like the Documents agent's OCR layer
hands it a typed `Document`). A `WorkflowStats` row is the raw send/open/reply counters for one
automated outbound sequence (review request, estimate follow-up, booking confirmation). The engine
classifies, prioritizes, drafts, and benchmarks; it never sends — sends/deletes flow through the
human-approved action gate (ADR 0007).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class EmailMessage:
    id: str
    from_name: str
    from_address: str
    subject: str
    body_excerpt: str
    age_hours: float
    category_hint: str | None = None  # needs_reply | fyi | workflow_report | promo | spam | newsletter
    intent: str | None = None         # bid_request | estimate_question | schedule_request | ...
    customer_name: str | None = None  # name as extracted from the email body/signature
    customer_tier: str | None = None  # commercial | residential
    value_cents: int | None = None    # extracted $ (bids, estimates, invoices)
    job_type: str | None = None
    requested_date: str | None = None
    sentiment: str | None = None      # angry | neutral
    topic: str | None = None          # legal | insurance | ...


@dataclass(frozen=True)
class WorkflowStats:
    id: str
    name: str
    emails_sent: int
    opens: int
    replies: int
    booked_jobs: int


@dataclass(frozen=True)
class InboxData:
    as_of: date
    emails: list[EmailMessage]
    workflows: list[WorkflowStats] = field(default_factory=list)
