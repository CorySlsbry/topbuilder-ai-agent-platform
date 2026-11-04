"""Deliverability + compliance engine for outbound outreach (pure, deterministic, ADR 0003-style).

This is the "protect the sending domain and stay legal" brain. It NEVER sends; it only DECIDES. The
send itself is a gated write (the `send_outreach_email` action executor) that re-checks these same
rules before it calls Resend, so a non-compliant or non-consented message can never leave the building.

Three guarantees, all enforced here:
  1. CAN-SPAM  — every message must carry a working unsubscribe + a physical postal address + an
                 honest from/subject, or the WHOLE batch is held (`can_spam_issues`).
  2. CONSENT   — cold (non-consented) contacts in consent-required jurisdictions (CASL/Canada, GDPR/EU,
                 UK) are HELD, never auto-sent; unknown jurisdiction is HELD (fail-safe); US cold B2B is
                 permitted (CAN-SPAM). Opted-in contacts are allowed anywhere. Suppressed/bounced are held.
  3. WARM-UP   — a NEW sending subdomain has a tiny daily cap that ramps with its age, because
                 cold-blasting a fresh domain is the #1 way to get filtered (`warmup_daily_cap`).

Everything is a pure function with hand-computed test oracles (`tests/test_outreach_compliance.py`).
"""
from __future__ import annotations

from dataclasses import dataclass

ALLOW = "allow"
HOLD = "hold"


@dataclass(frozen=True)
class OutreachContact:
    """A CRM contact considered for an outreach send."""

    contact_id: str
    email: str
    country: str | None = None  # ISO-2 (e.g. "US", "CA"); None/"" = unknown
    consent: bool = False  # True = opted-in / prior business relationship
    bounced: bool = False  # previously hard-bounced (suppress)
    unsubscribed: bool = False  # opted out (suppress)


@dataclass(frozen=True)
class OutreachMessage:
    """The composed message. CAN-SPAM requires the unsubscribe + physical address to be present."""

    subject: str
    html: str
    text: str
    from_email: str
    from_name: str
    unsubscribe_url: str | None
    physical_address: str | None


@dataclass(frozen=True)
class SendDecision:
    contact_id: str
    decision: str  # ALLOW | HOLD
    reason: str  # "" when ALLOW; otherwise a stable machine-readable reason code


def can_spam_issues(msg: OutreachMessage) -> list[str]:
    """Return the list of CAN-SPAM problems with a message (empty list = compliant).

    Required on every commercial email: a non-empty subject, a from address, a working unsubscribe
    mechanism, and a physical postal address. We can't detect *deceptive* subjects programmatically,
    so the honesty of the copy is a human responsibility; these are the structural musts.
    """
    issues: list[str] = []
    if not (msg.subject or "").strip():
        issues.append("missing_subject")
    if not (msg.from_email or "").strip():
        issues.append("missing_from")
    if not (msg.unsubscribe_url or "").strip():
        issues.append("missing_unsubscribe")
    if not (msg.physical_address or "").strip():
        issues.append("missing_physical_address")
    return issues


def is_can_spam_compliant(msg: OutreachMessage) -> bool:
    return not can_spam_issues(msg)


def consent_decision(
    contact: OutreachContact,
    *,
    consent_required_countries: set[str],
    blocked_countries: set[str] = frozenset(),
) -> SendDecision:
    """Decide ALLOW/HOLD for one contact on country-block + suppression + consent grounds.

    Order: (1) a HARD country block (e.g. "do not send to Canada") overrides EVERYTHING, including
    consent — a blocked country is never emailed, opted-in or not. Then (2) suppression
    (unsubscribed/bounced). Then (3) opted-in is allowed anywhere not blocked. Then (4) a cold contact
    is allowed only where cold commercial email is permitted (e.g. US under CAN-SPAM); cold in a
    consent-required country (CASL/Canada, GDPR/EU, UK) is HELD, and cold with unknown jurisdiction is
    HELD (fail-safe, we don't guess).
    """
    country = (contact.country or "").strip().upper()
    if country and country in blocked_countries:
        return SendDecision(contact.contact_id, HOLD, f"country_blocked:{country}")
    if contact.unsubscribed:
        return SendDecision(contact.contact_id, HOLD, "suppressed_unsubscribed")
    if contact.bounced:
        return SendDecision(contact.contact_id, HOLD, "suppressed_bounced")
    if contact.consent:
        return SendDecision(contact.contact_id, ALLOW, "")
    if not country:
        return SendDecision(contact.contact_id, HOLD, "cold_unknown_jurisdiction")
    if country in consent_required_countries:
        return SendDecision(contact.contact_id, HOLD, f"cold_consent_required:{country}")
    return SendDecision(contact.contact_id, ALLOW, "")


def authoritative_send_decision(
    resolved: dict | None,
    *,
    contact_id: str,
    email: str,
    suppressed: bool,
    consent_required_countries: set[str],
    blocked_countries: set[str] = frozenset(),
) -> SendDecision:
    """Decide ALLOW/HOLD from SERVER-RESOLVED facts only (the param-trust fix, pure).

    ``resolved`` is the outreach_contacts row (or None). Proposer-supplied consent/country/
    suppression flags never reach this function: an unresolvable contact is HELD (fail-safe — we
    don't guess jurisdiction or consent), a suppression-list hit is HELD regardless of the contact
    record, and everything else runs through the same consent_decision the batch path uses.
    """
    if suppressed:
        return SendDecision(contact_id, HOLD, "suppressed_listed")
    if resolved is None:
        return SendDecision(contact_id, HOLD, "contact_unresolved")
    contact = OutreachContact(
        contact_id=contact_id,
        email=email,
        country=resolved.get("country"),
        consent=bool(resolved.get("consent", False)),
        bounced=bool(resolved.get("bounced", False)),
        unsubscribed=bool(resolved.get("unsubscribed", False)),
    )
    return consent_decision(
        contact,
        consent_required_countries=consent_required_countries,
        blocked_countries=blocked_countries,
    )


def warmup_daily_cap(domain_age_days: int, *, start: int, growth: int, ceiling: int) -> int:
    """The max sends allowed today given the sending subdomain's age, ramping start*growth^age to a ceiling.

    Day 0 of a brand-new subdomain sends only `start`; it grows each day and is clamped at `ceiling`.
    A negative age is treated as day 0. This is what stops a fresh subdomain from being cold-blasted
    into a spam-folder reputation it can't recover from.
    """
    age = max(0, domain_age_days)
    cap = start * (growth**age)
    return min(cap, ceiling)


def select_sendable(
    contacts: list[OutreachContact],
    *,
    message: OutreachMessage,
    consent_required_countries: set[str],
    daily_cap: int,
    already_sent_today: int = 0,
    blocked_countries: set[str] = frozenset(),
) -> tuple[list[SendDecision], list[SendDecision]]:
    """Split a batch into (to_send, held), enforcing message-compliance, consent, and the daily cap.

    If the MESSAGE itself is not CAN-SPAM compliant, the entire batch is held (we never send a
    non-compliant message to anyone). Otherwise each contact is run through `consent_decision`, and
    allowed contacts are admitted up to the remaining daily budget (`daily_cap - already_sent_today`);
    the overflow is held as `daily_cap_reached`. Order of `contacts` is preserved (send the most
    important/engaged first by ordering the input).
    """
    issues = can_spam_issues(message)
    if issues:
        reason = "message_noncompliant:" + ",".join(issues)
        return [], [SendDecision(c.contact_id, HOLD, reason) for c in contacts]

    remaining = max(0, daily_cap - max(0, already_sent_today))
    to_send: list[SendDecision] = []
    held: list[SendDecision] = []
    for c in contacts:
        decision = consent_decision(
            c,
            consent_required_countries=consent_required_countries,
            blocked_countries=blocked_countries,
        )
        if decision.decision != ALLOW:
            held.append(decision)
            continue
        if len(to_send) < remaining:
            to_send.append(decision)
        else:
            held.append(SendDecision(c.contact_id, HOLD, "daily_cap_reached"))
    return to_send, held
