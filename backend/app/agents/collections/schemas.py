"""API-facing schemas (spec-shaped) + mapper for the A/R Collections agent.

Every dollar figure derives from the deterministic engine's *cents* (ADR 0003); this layer formats to
dollars and rolls up. The headline metric — ``overdue_balance_usd`` and ``at_risk_balance_usd`` — is
the past-due A/R the agent is working (the >$400K pain) and the 91+ reserve/write-off candidate.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.agents.collections.analytics import BUCKET_ORDER, CollectionsAnalysis
from app.agents.collections.drafts import DunningDrafts, build_drafts


def _usd(cents: int) -> float:
    return round(cents / 100, 2)


def _buckets_usd(buckets: dict[str, int]) -> dict[str, float]:
    return {b: _usd(buckets.get(b, 0)) for b in BUCKET_ORDER}


class WorklistInvoiceOut(BaseModel):
    invoice_id: str
    doc_number: str | None
    balance_usd: float
    days_overdue: int
    bucket: str


class DunningDraftsOut(BaseModel):
    step: int
    channel: str
    email_subject: str | None
    email_body: str | None
    sms_body: str | None
    call_script: str | None


class WorklistCustomerOut(BaseModel):
    customer_id: str
    customer_name: str
    customer_segment: str
    balance_usd: float
    oldest_days_overdue: int
    bucket: str
    status: str
    owner: str
    next_action: str
    dunning_step: int
    dunning_channel: str
    promise_date: date | None
    promise_amount_usd: float | None
    bucket_balances_usd: dict[str, float]
    invoices: list[WorklistInvoiceOut]
    drafts: DunningDraftsOut


class CollectionsTotalsOut(BaseModel):
    customers: int
    open_balance_usd: float
    overdue_balance_usd: float
    current_balance_usd: float
    pct_current: float
    pct_over_30: float
    bucket_balances_usd: dict[str, float]
    at_risk_balance_usd: float
    customers_needing_action: int


class CollectionsRunResult(BaseModel):
    run_id: uuid.UUID | None = None
    agent: str = "collections"
    source_system: str = "QuickBooks"  # AR is reconciled in QBO (per docs/QBO_DATA_MAP §2)
    analysis_timestamp: datetime
    as_of: date
    worklist: list[WorklistCustomerOut]
    totals: CollectionsTotalsOut
    reasoning_logs: str
    inputs_hash: str


def _drafts_out(d: DunningDrafts) -> DunningDraftsOut:
    return DunningDraftsOut(
        step=d.step, channel=d.channel, email_subject=d.email_subject,
        email_body=d.email_body, sms_body=d.sms_body, call_script=d.call_script,
    )


def build_result(
    analysis: CollectionsAnalysis,
    *,
    narrative: str,
    analysis_timestamp: datetime,
    run_id: uuid.UUID | None = None,
    source_system: str = "QuickBooks",
) -> CollectionsRunResult:
    worklist = [
        WorklistCustomerOut(
            customer_id=c.customer_id,
            customer_name=c.customer_name,
            customer_segment=c.customer_segment,
            balance_usd=_usd(c.balance_cents),
            oldest_days_overdue=c.oldest_days_overdue,
            bucket=c.bucket,
            status=c.status,
            owner=c.owner,
            next_action=c.next_action,
            dunning_step=c.dunning_step,
            dunning_channel=c.dunning_channel,
            promise_date=c.promise_date,
            promise_amount_usd=_usd(c.promise_amount_cents) if c.promise_amount_cents is not None else None,
            bucket_balances_usd=_buckets_usd(c.bucket_balances_cents),
            invoices=[
                WorklistInvoiceOut(
                    invoice_id=i.invoice_id, doc_number=i.doc_number,
                    balance_usd=_usd(i.balance_cents), days_overdue=i.days_overdue, bucket=i.bucket,
                )
                for i in c.invoices
            ],
            drafts=_drafts_out(build_drafts(c)),
        )
        for c in analysis.worklist
    ]
    t = analysis.totals
    totals = CollectionsTotalsOut(
        customers=t.customers,
        open_balance_usd=_usd(t.open_balance_cents),
        overdue_balance_usd=_usd(t.overdue_balance_cents),
        current_balance_usd=_usd(t.current_balance_cents),
        pct_current=t.pct_current,
        pct_over_30=t.pct_over_30,
        bucket_balances_usd=_buckets_usd(t.bucket_balances_cents),
        at_risk_balance_usd=_usd(t.at_risk_balance_cents),
        customers_needing_action=t.customers_needing_action,
    )
    return CollectionsRunResult(
        run_id=run_id,
        source_system=source_system,
        analysis_timestamp=analysis_timestamp,
        as_of=analysis.as_of,
        worklist=worklist,
        totals=totals,
        reasoning_logs=narrative,
        inputs_hash=analysis.inputs_hash,
    )
