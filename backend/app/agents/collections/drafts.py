"""Deterministic dunning DRAFTS for the Collections agent (ADR 0003 — figures quoted, never computed).

Given a `WorklistCustomer` (already computed by the engine), produce a ready-to-send email, SMS, and a
phone CALL SCRIPT for its recommended dunning step. The LLM reasoning layer MAY later polish the tone,
but it must quote these figures (balance, days overdue, promise-to-pay) exactly — they originate here
from the deterministic engine's cents, formatted to dollars only for display.

Compliance is baked into the copy: every SMS carries a STOP opt-out (TCPA) and every email an
unsubscribe + physical-address line (CAN-SPAM); the call script opens with the mini-Miranda and honors
quiet hours (8am–9pm local, FDCPA-style) — the channel itself was already compliance-gated by the
engine's `downgrade_for_compliance`, so a do-not-call / no-consent customer never reaches the call/SMS
draft.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.agents.collections.analytics import (
    CHANNEL_CALL,
    CHANNEL_EMAIL,
    CHANNEL_SMS,
    WorklistCustomer,
)

# Tokenized so onboarding swaps the real company identity in (kept generic — platform-agnostic).
COMPANY_NAME = "{company_name}"
COMPANY_ADDRESS = "{company_address}"
PAY_LINK = "{pay_link}"


def _usd(cents: int) -> str:
    return f"${cents / 100:,.2f}"


@dataclass(frozen=True)
class DunningDrafts:
    customer_id: str
    step: int
    channel: str
    email_subject: str | None
    email_body: str | None
    sms_body: str | None
    call_script: str | None


def _balance_phrase(c: WorklistCustomer) -> str:
    if c.oldest_days_overdue <= 0:
        return f"a balance of {_usd(c.balance_cents)}"
    return f"a past-due balance of {_usd(c.balance_cents)}, {c.oldest_days_overdue} days overdue"


def _promise_phrase(c: WorklistCustomer) -> str | None:
    if c.promise_date is None or c.promise_amount_cents is None:
        return None
    return (
        f"We have your commitment to pay {_usd(c.promise_amount_cents)} by "
        f"{c.promise_date.isoformat()}."
    )


def _email(c: WorklistCustomer) -> tuple[str, str]:
    tone = {
        1: ("Friendly reminder", "a quick reminder that"),
        2: ("Second notice — payment past due", "our records show that"),
        3: ("Important: account past due", "this is a firm notice that"),
        4: ("FINAL NOTICE before collections", "this is our final notice that"),
        5: ("Account referred for collections", "your account is being referred for collections;"),
    }
    subject_lead, body_lead = tone.get(c.dunning_step, tone[1])
    subject = f"{subject_lead} — {COMPANY_NAME} account {_usd(c.balance_cents)}"
    promise = _promise_phrase(c)
    lines = [
        f"Dear {c.customer_name},",
        "",
        f"This is {body_lead} your account with {COMPANY_NAME} carries {_balance_phrase(c)}.",
    ]
    if promise:
        lines += ["", promise]
    if c.dunning_step >= 4:
        lines += [
            "",
            "To avoid further action, please remit payment immediately or contact us to arrange terms.",
        ]
    else:
        lines += ["", f"You can pay securely here: {PAY_LINK}, or reply to arrange payment."]
    lines += [
        "",
        "If you have already paid, please disregard this notice and accept our thanks.",
        "",
        f"{COMPANY_NAME}",
        COMPANY_ADDRESS,
        "Reply STOP/unsubscribe to opt out of payment reminders.",  # CAN-SPAM
    ]
    return subject, "\n".join(lines)


def _sms(c: WorklistCustomer) -> str:
    base = (
        f"{COMPANY_NAME}: account {_balance_phrase(c)}. "
        f"Pay: {PAY_LINK}"
    )
    return f"{base} Reply STOP to opt out."  # TCPA opt-out


def _call_script(c: WorklistCustomer) -> str:
    promise = _promise_phrase(c)
    lines = [
        "CALL SCRIPT (observe quiet hours: 8am–9pm in the customer's local time; honor do-not-call).",
        "",
        f"Hi, may I speak with {c.customer_name}? This is [agent] calling on behalf of {COMPANY_NAME}.",
        "This is an attempt to collect a debt; any information obtained will be used for that purpose.",
        "",
        f"Our records show {_balance_phrase(c)} on your account.",
    ]
    if promise:
        lines += [promise + " Can you confirm that payment is still on track?"]
    elif c.dunning_step >= 4:
        lines += [
            "This account is at final notice. Can we take payment today, or set a firm payment date?",
        ]
    else:
        lines += ["Are you able to take care of this today, or set a date you can pay by?"]
    lines += [
        "",
        "[If they commit to a date/amount: capture it as a promise-to-pay.]",
        "[If they dispute the charge: mark the account disputed and route to the account manager.]",
        "Thank you for your time.",
    ]
    return "\n".join(lines)


def build_drafts(c: WorklistCustomer) -> DunningDrafts:
    """Build the drafts for a customer's recommended channel. Reconciled/none -> no drafts."""
    if c.dunning_channel not in (CHANNEL_EMAIL, CHANNEL_SMS, CHANNEL_CALL) or c.dunning_step == 0:
        return DunningDrafts(
            customer_id=c.customer_id, step=c.dunning_step, channel=c.dunning_channel,
            email_subject=None, email_body=None, sms_body=None, call_script=None,
        )
    # An email is always drafted (the universal fallback); SMS and call scripts are added as the
    # recommended channel escalates. Step 2 (email+SMS) yields both; calls add the script too.
    subject, body = _email(c)
    sms = _sms(c) if c.dunning_channel in (CHANNEL_SMS, CHANNEL_CALL) else None
    call = _call_script(c) if c.dunning_channel == CHANNEL_CALL else None
    return DunningDrafts(
        customer_id=c.customer_id,
        step=c.dunning_step,
        channel=c.dunning_channel,
        email_subject=subject,
        email_body=body,
        sms_body=sms,
        call_script=call,
    )
