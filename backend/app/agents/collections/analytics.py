"""Deterministic A/R Collections engine: bucket -> status -> dunning step (ADR 0003).

No LLM, no randomness, integer cents. Ingests open invoices (+ promises-to-pay + contact prefs) and
produces a per-customer COLLECTIONS WORKLIST that reproduces the client's manual Outstanding-A/R Google
Sheet: aging bucket, balance, days overdue, workflow status, owner, next-action, promise-to-pay, and a
recommended dunning step (email / SMS / call) that escalates by age. The reasoning node narrates these;
it never decides them.

Aging buckets (match the sheet + QBO AgedReceivables): Current / 1-30 / 31-60 / 61-90 / 91-120 / 121+,
measured in days past the invoice DUE date (A/R aging is due-date based, accrual).

Dunning escalation by the oldest-overdue invoice's age (CPA-sane, the documented sheet workflow):
  step 1  friendly reminder (email)            — 1-30 days
  step 2  second notice (email + SMS)           — 31-60 days
  step 3  firm notice + call                    — 61-90 days
  step 4  final demand (call)                   — 91-120 days
  step 5  write-off / send-to-collections call  — 121+ days
A customer who is fully current (nothing past due) gets NO dunning step (reconciled -> skipped).
A live promise-to-pay (a future-dated commitment that covers the balance) parks the customer in
"Expecting money" and suppresses escalation until the promise date passes.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date

from app.agents.collections.models import (
    CollectionsData,
    ContactPreference,
    OpenInvoice,
    PromiseToPay,
)

# --------------------------------------------------------------------------------------------
# Aging buckets + dunning ladder
# --------------------------------------------------------------------------------------------
BUCKET_CURRENT = "current"
BUCKET_1_30 = "1-30"
BUCKET_31_60 = "31-60"
BUCKET_61_90 = "61-90"
BUCKET_91_120 = "91-120"
BUCKET_121_PLUS = "121+"
BUCKET_ORDER: tuple[str, ...] = (
    BUCKET_CURRENT,
    BUCKET_1_30,
    BUCKET_31_60,
    BUCKET_61_90,
    BUCKET_91_120,
    BUCKET_121_PLUS,
)

# Workflow band (the sheet's left-hand status column).
STATUS_RECONCILED = "reconciled"  # nothing past due
STATUS_EXPECTING_MONEY = "expecting_money"  # live promise-to-pay covers the balance
STATUS_STALLED_OUR_COURT = "stalled_our_court"  # we owe an action (recently overdue, no promise)
STATUS_STALLED_OTHER_COURT = "stalled_other_court"  # disputed — waiting on the customer
STATUS_ACTION_REQUIRED = "action_required"  # owner must act now (mid-age, no promise)
STATUS_WRITE_OFF_OR_COLLECTIONS = "write_off_or_collections"  # 121+ — reserve / send to collections

# Dunning channels.
CHANNEL_NONE = "none"
CHANNEL_EMAIL = "email"
CHANNEL_SMS = "sms"
CHANNEL_CALL = "call"


def aging_bucket(days_overdue: int) -> str:
    """Map days past due to an aging bucket. <=0 (not yet due) is Current."""
    if days_overdue <= 0:
        return BUCKET_CURRENT
    if days_overdue <= 30:
        return BUCKET_1_30
    if days_overdue <= 60:
        return BUCKET_31_60
    if days_overdue <= 90:
        return BUCKET_61_90
    if days_overdue <= 120:
        return BUCKET_91_120
    return BUCKET_121_PLUS


def days_overdue(due: date, as_of: date) -> int:
    """Days past the due date as of `as_of`. Negative/zero means not yet due."""
    return (as_of - due).days


@dataclass(frozen=True)
class DunningStep:
    step: int  # 0 = no action (reconciled); 1..5 escalating
    channel: str  # email | sms | call | none
    label: str  # human-readable step name


# step -> (channel, label). step 2 escalates to email+SMS; we record the primary channel as SMS
# (so the worklist surfaces the most-urgent channel) but the drafts cover both (see drafts.py).
_DUNNING_LADDER: dict[int, DunningStep] = {
    0: DunningStep(0, CHANNEL_NONE, "no action — reconciled"),
    1: DunningStep(1, CHANNEL_EMAIL, "1st reminder"),
    2: DunningStep(2, CHANNEL_SMS, "2nd notice"),
    3: DunningStep(3, CHANNEL_CALL, "firm notice + call"),
    4: DunningStep(4, CHANNEL_CALL, "final demand"),
    5: DunningStep(5, CHANNEL_CALL, "write-off / collections"),
}

_BUCKET_TO_STEP: dict[str, int] = {
    BUCKET_CURRENT: 0,
    BUCKET_1_30: 1,
    BUCKET_31_60: 2,
    BUCKET_61_90: 3,
    BUCKET_91_120: 4,
    BUCKET_121_PLUS: 5,
}


def dunning_step_for_bucket(bucket: str) -> DunningStep:
    return _DUNNING_LADDER[_BUCKET_TO_STEP[bucket]]


def downgrade_for_compliance(step: DunningStep, contact: ContactPreference | None) -> DunningStep:
    """Honor TCPA / do-not-call before recommending a channel (compliance, not a figure).

    - do_not_call -> never recommend a CALL; fall back to email.
    - SMS requires prior express consent (sms_opt_in); without it, fall back to email.
    A missing email with a blocked channel yields CHANNEL_NONE (needs a human / mailed letter).
    """
    if step.channel == CHANNEL_NONE:
        return step
    channel = step.channel
    has_phone = bool(contact and contact.phone)
    can_call = has_phone and not (contact and contact.do_not_call)
    can_sms = has_phone and bool(contact and contact.sms_opt_in)
    has_email = bool(contact and contact.email)

    if channel == CHANNEL_CALL and not can_call:
        channel = CHANNEL_EMAIL if has_email else CHANNEL_NONE
    elif channel == CHANNEL_SMS and not can_sms:
        channel = CHANNEL_EMAIL if has_email else CHANNEL_NONE
    elif channel == CHANNEL_EMAIL and not has_email:
        channel = CHANNEL_NONE
    if channel == step.channel:
        return step
    return DunningStep(step.step, channel, step.label)


# --------------------------------------------------------------------------------------------
# Result types
# --------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class WorklistInvoice:
    invoice_id: str
    doc_number: str | None
    balance_cents: int
    days_overdue: int
    bucket: str


@dataclass(frozen=True)
class WorklistCustomer:
    customer_id: str
    customer_name: str
    customer_segment: str
    balance_cents: int
    oldest_days_overdue: int
    bucket: str  # the customer's worst (oldest) bucket
    status: str  # workflow band
    owner: str  # who works the row
    next_action: str  # the recommended next step in words
    dunning_step: int
    dunning_channel: str
    promise_date: date | None
    promise_amount_cents: int | None
    invoices: list[WorklistInvoice]
    bucket_balances_cents: dict[str, int]  # per-bucket split of THIS customer's balance


@dataclass(frozen=True)
class CollectionsTotals:
    customers: int
    open_balance_cents: int
    overdue_balance_cents: int  # balance that is past due (not Current)
    current_balance_cents: int
    pct_current: float  # current / open * 100 (0 when no balance)
    pct_over_30: float  # (open - current - 1to30)/open ... per CPA "over 30" = 31+ days
    bucket_balances_cents: dict[str, int]  # portfolio aging ladder
    at_risk_balance_cents: int  # 91+ days — reserve / write-off candidate (CPA flag)
    customers_needing_action: int  # not reconciled and not parked on a promise


@dataclass(frozen=True)
class CollectionsAnalysis:
    as_of: date
    worklist: list[WorklistCustomer]
    totals: CollectionsTotals
    inputs_hash: str


# --------------------------------------------------------------------------------------------
# Owner assignment (mirrors the sheet's owner column, deterministic)
# --------------------------------------------------------------------------------------------
# The real sheet routes by workflow band; we assign a deterministic owner per status so the worklist
# is actionable. Names are roles, not the client's real staff (configurable at onboarding).
_OWNER_BY_STATUS: dict[str, str] = {
    STATUS_RECONCILED: "—",
    STATUS_EXPECTING_MONEY: "AR Clerk",
    STATUS_STALLED_OUR_COURT: "AR Clerk",
    STATUS_STALLED_OTHER_COURT: "Account Manager",
    STATUS_ACTION_REQUIRED: "Collections Lead",
    STATUS_WRITE_OFF_OR_COLLECTIONS: "Controller",
}


def _round_pct(n: int, d: int) -> float:
    return round((n / d) * 100, 2) if d else 0.0


# --------------------------------------------------------------------------------------------
# Engine
# --------------------------------------------------------------------------------------------
def _promise_for(customer_id: str, promises: list[PromiseToPay]) -> PromiseToPay | None:
    """The latest-recorded promise for a customer (the sheet keeps the most recent commitment)."""
    matches = [p for p in promises if p.customer_id == customer_id]
    return max(matches, key=lambda p: p.recorded_at) if matches else None


def _classify_status(
    *,
    oldest_overdue: int,
    bucket: str,
    in_dispute: bool,
    promise: PromiseToPay | None,
    balance_cents: int,
    as_of: date,
) -> str:
    if oldest_overdue <= 0:
        return STATUS_RECONCILED
    if (
        promise is not None
        and promise.promised_date >= as_of
        and promise.promised_amount_cents >= balance_cents
    ):
        return STATUS_EXPECTING_MONEY
    if in_dispute:
        return STATUS_STALLED_OTHER_COURT
    if bucket == BUCKET_121_PLUS:
        return STATUS_WRITE_OFF_OR_COLLECTIONS
    if bucket in (BUCKET_61_90, BUCKET_91_120):
        return STATUS_ACTION_REQUIRED
    return STATUS_STALLED_OUR_COURT  # 1-60 days, no promise — routine follow-up in our court


def _next_action_text(
    status: str,
    step: DunningStep,
    promise: PromiseToPay | None,
    *,
    balance_cents: int,
    as_of: date,
) -> str:
    if status == STATUS_RECONCILED:
        return "No action — balance is current."
    if status == STATUS_EXPECTING_MONEY and promise is not None:
        return (
            f"Awaiting promised payment by {promise.promised_date.isoformat()} "
            f"(${promise.promised_amount_cents / 100:,.0f}). Confirm receipt, then follow up if missed."
        )
    if status == STATUS_STALLED_OTHER_COURT:
        return "Disputed — waiting on the customer. Escalate to the account manager to resolve."
    # A PARTIAL promise (a future commitment that doesn't cover the full balance) does not park the
    # customer in EXPECTING_MONEY, so we still dun — but acknowledge the partial so the desk doesn't
    # read as chasing someone who just committed. Pure text; no figure recomputed.
    partial = ""
    if (
        promise is not None
        and promise.promised_date >= as_of
        and 0 < promise.promised_amount_cents < balance_cents
    ):
        remainder = balance_cents - promise.promised_amount_cents
        partial = (
            f"Partial promise of ${promise.promised_amount_cents / 100:,.0f} on file "
            f"(by {promise.promised_date.isoformat()}); pursue the ${remainder / 100:,.0f} remainder. "
        )
    if step.channel == CHANNEL_NONE:
        return f"{partial}{step.label}: no reachable contact channel — mail a statement / assign a human."
    verb = {CHANNEL_EMAIL: "Email", CHANNEL_SMS: "Text", CHANNEL_CALL: "Call"}[step.channel]
    return f"{partial}{verb} the {step.label} (step {step.step})."


def analyze(data: CollectionsData) -> CollectionsAnalysis:
    by_customer: dict[str, list[OpenInvoice]] = {}
    for inv in data.invoices:
        by_customer.setdefault(inv.customer_id, []).append(inv)
    contacts = {c.customer_id: c for c in data.contacts}

    worklist: list[WorklistCustomer] = []
    portfolio_buckets: dict[str, int] = {b: 0 for b in BUCKET_ORDER}

    for customer_id, invoices in by_customer.items():
        invoices_sorted = sorted(invoices, key=lambda i: i.due)
        name = invoices_sorted[0].customer_name
        segment = invoices_sorted[0].customer_segment
        in_dispute = any(i.in_dispute for i in invoices_sorted)
        balance = sum(i.balance_cents for i in invoices_sorted)

        cust_buckets: dict[str, int] = {b: 0 for b in BUCKET_ORDER}
        wl_invoices: list[WorklistInvoice] = []
        oldest = 0
        for inv in invoices_sorted:
            od = days_overdue(inv.due, data.as_of)
            b = aging_bucket(od)
            cust_buckets[b] += inv.balance_cents
            portfolio_buckets[b] += inv.balance_cents
            oldest = max(oldest, od)
            wl_invoices.append(
                WorklistInvoice(
                    invoice_id=inv.id,
                    doc_number=inv.doc_number,
                    balance_cents=inv.balance_cents,
                    days_overdue=od,
                    bucket=b,
                )
            )

        worst_bucket = aging_bucket(oldest)
        promise = _promise_for(customer_id, data.promises)
        status = _classify_status(
            oldest_overdue=oldest,
            bucket=worst_bucket,
            in_dispute=in_dispute,
            promise=promise,
            balance_cents=balance,
            as_of=data.as_of,
        )
        raw_step = (
            DunningStep(0, CHANNEL_NONE, "no action — promise pending")
            if status == STATUS_EXPECTING_MONEY
            else dunning_step_for_bucket(worst_bucket)
        )
        step = downgrade_for_compliance(raw_step, contacts.get(customer_id))
        next_action = _next_action_text(
            status, step, promise, balance_cents=balance, as_of=data.as_of
        )

        worklist.append(
            WorklistCustomer(
                customer_id=customer_id,
                customer_name=name,
                customer_segment=segment,
                balance_cents=balance,
                oldest_days_overdue=oldest,
                bucket=worst_bucket,
                status=status,
                owner=_OWNER_BY_STATUS[status],
                next_action=next_action,
                dunning_step=step.step,
                dunning_channel=step.channel,
                promise_date=promise.promised_date if promise else None,
                promise_amount_cents=promise.promised_amount_cents if promise else None,
                invoices=wl_invoices,
                bucket_balances_cents=cust_buckets,
            )
        )

    # Worst-first: oldest overdue, then largest balance — exactly how a collections desk works the list.
    worklist.sort(key=lambda c: (c.oldest_days_overdue, c.balance_cents), reverse=True)

    open_balance = sum(c.balance_cents for c in worklist)
    current_balance = portfolio_buckets[BUCKET_CURRENT]
    overdue_balance = open_balance - current_balance
    over_30 = (
        portfolio_buckets[BUCKET_31_60]
        + portfolio_buckets[BUCKET_61_90]
        + portfolio_buckets[BUCKET_91_120]
        + portfolio_buckets[BUCKET_121_PLUS]
    )
    at_risk = portfolio_buckets[BUCKET_91_120] + portfolio_buckets[BUCKET_121_PLUS]
    needing_action = sum(
        1 for c in worklist if c.status not in (STATUS_RECONCILED, STATUS_EXPECTING_MONEY)
    )

    totals = CollectionsTotals(
        customers=len(worklist),
        open_balance_cents=open_balance,
        overdue_balance_cents=overdue_balance,
        current_balance_cents=current_balance,
        pct_current=_round_pct(current_balance, open_balance),
        pct_over_30=_round_pct(over_30, open_balance),
        bucket_balances_cents=portfolio_buckets,
        at_risk_balance_cents=at_risk,
        customers_needing_action=needing_action,
    )
    return CollectionsAnalysis(
        as_of=data.as_of,
        worklist=worklist,
        totals=totals,
        inputs_hash=_hash_inputs(data),
    )


def _hash_inputs(data: CollectionsData) -> str:
    payload = {
        "as_of": data.as_of.isoformat(),
        "invoices": sorted(
            (
                {**asdict(i), "issued": i.issued.isoformat(), "due": i.due.isoformat()}
                for i in data.invoices
            ),
            key=lambda r: r["id"],
        ),
        "promises": sorted(
            (
                {
                    **asdict(p),
                    "promised_date": p.promised_date.isoformat(),
                    "recorded_at": p.recorded_at.isoformat(),
                }
                for p in data.promises
            ),
            key=lambda r: (r["customer_id"], r["recorded_at"]),
        ),
        "contacts": sorted((asdict(c) for c in data.contacts), key=lambda r: r["customer_id"]),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
