"""Domain models for the A/R Collections agent (dependency-free, stdlib only).

Models the client's real Outstanding-A/R Google Sheet (Summit Heat Pumps; Alex discovery call
2026-06-16, ``docs/ALEX_DISCOVERY_2026-06-16.md`` screen 1): per-customer open balance, the workflow
band ("Expecting money" / "Stalled – in our court" / ...), the aging buckets
(Current / 1-30 / 31-60 / 61-90 / 91-120 / 121+), Net Amount, Created Date, an owner, dated notes, and
a promise-to-pay. Money is carried as integer **cents** (ADR 0003); dollars only at the API boundary.

The aging/AR data is read from an adapter (fixture now; fail-closed QBO/ServiceTitan live skeleton):
open invoices with a balance + age feed the engine, which reproduces the buckets and the worklist.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass(frozen=True)
class OpenInvoice:
    """One open (unpaid / partially-paid) invoice, the grain QBO AgedReceivableDetail returns."""

    id: str
    customer_id: str
    customer_name: str
    balance_cents: int  # remaining balance owed (NET amount), integer cents
    issued: date  # invoice/created date
    due: date  # payment due date — days overdue is measured from here
    doc_number: str | None = None
    customer_segment: str = "residential"  # residential | commercial | government
    in_dispute: bool = False  # flagged "stalled – in other court" (their dispute, not ours)


@dataclass(frozen=True)
class PromiseToPay:
    """A recorded commitment from the customer to pay by a date (sheet's dated-notes workflow)."""

    customer_id: str
    promised_date: date
    promised_amount_cents: int
    recorded_at: datetime
    note: str | None = None


@dataclass(frozen=True)
class ContactPreference:
    """How a customer may be contacted — drives the dunning channel + TCPA/CAN-SPAM compliance."""

    customer_id: str
    email: str | None = None
    phone: str | None = None
    sms_opt_in: bool = False  # TCPA: no autodialed/recorded SMS or calls without prior consent
    do_not_call: bool = False  # honored before any call/SMS step is recommended


@dataclass(frozen=True)
class CollectionsData:
    as_of: date
    invoices: list[OpenInvoice]
    promises: list[PromiseToPay] = field(default_factory=list)
    contacts: list[ContactPreference] = field(default_factory=list)
