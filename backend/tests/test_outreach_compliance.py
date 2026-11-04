"""Pure oracle tests for the outreach deliverability + compliance engine (`app/outreach/compliance.py`).

The engine is the safety brain for emailing CRM contacts: CAN-SPAM structure, cold-email consent by
jurisdiction (CASL/Canada + GDPR/EU held), suppression, and the new-subdomain warm-up cap. Oracles are
hand-computed (no function's output is used as its own oracle).
"""
from __future__ import annotations

import pytest

from app.outreach import compliance as oc

# A representative consent-required set (CASL Canada + a few GDPR/EU/UK), mirroring the config default.
CONSENT_REQUIRED = {"CA", "GB", "DE", "FR", "IE", "NL", "ES", "IT"}
# Hard country block (Cory's directive 2026-06-24: never email Canada, even with consent).
BLOCKED = {"CA"}


def _complete_message() -> oc.OutreachMessage:
    return oc.OutreachMessage(
        subject="A quick question about your A/R",
        html="<p>Hi</p>",
        text="Hi",
        from_email="outreach@send.topbuilderai.com",
        from_name="Top Builder AI",
        unsubscribe_url="https://topbuilderai.com/u/abc123",
        physical_address="Salisbury Bookkeeping LLC, Eagle Mountain, UT",
    )


class TestCanSpamIssues:
    def test_complete_message_has_no_issues(self) -> None:
        assert oc.can_spam_issues(_complete_message()) == []
        assert oc.is_can_spam_compliant(_complete_message()) is True

    @pytest.mark.parametrize(
        "field,expected",
        [
            ("subject", "missing_subject"),
            ("unsubscribe_url", "missing_unsubscribe"),
            ("physical_address", "missing_physical_address"),
            ("from_email", "missing_from"),
        ],
    )
    def test_each_missing_required_field_is_flagged(self, field: str, expected: str) -> None:
        base = _complete_message()
        kwargs = base.__dict__.copy()
        kwargs[field] = ""  # blank out exactly one required field
        broken = oc.OutreachMessage(**kwargs)
        issues = oc.can_spam_issues(broken)
        assert issues == [expected]
        assert oc.is_can_spam_compliant(broken) is False


class TestConsentDecision:
    def test_blocked_country_held_even_if_opted_in(self) -> None:
        # The hard rule: never email Canada, even an opted-in contact (block overrides consent).
        c = oc.OutreachContact("c1", "person1@example.com", country="CA", consent=True)
        d = oc.consent_decision(
            c, consent_required_countries=CONSENT_REQUIRED, blocked_countries=BLOCKED
        )
        assert d == oc.SendDecision("c1", oc.HOLD, "country_blocked:CA")

    def test_blocked_country_held_when_cold(self) -> None:
        c = oc.OutreachContact("c1b", "person1@example.com", country="ca", consent=False)  # case-insensitive
        d = oc.consent_decision(
            c, consent_required_countries=CONSENT_REQUIRED, blocked_countries=BLOCKED
        )
        assert d == oc.SendDecision("c1b", oc.HOLD, "country_blocked:CA")

    def test_opted_in_us_contact_is_allowed(self) -> None:
        c = oc.OutreachContact("c2", "person2@example.com", country="US", consent=True)
        d = oc.consent_decision(
            c, consent_required_countries=CONSENT_REQUIRED, blocked_countries=BLOCKED
        )
        assert d == oc.SendDecision("c2", oc.ALLOW, "")

    def test_cold_us_contact_is_allowed(self) -> None:
        c = oc.OutreachContact("c3", "person2@example.com", country="US", consent=False)
        d = oc.consent_decision(
            c, consent_required_countries=CONSENT_REQUIRED, blocked_countries=BLOCKED
        )
        assert d.decision == oc.ALLOW and d.reason == ""

    def test_cold_consent_required_country_held_for_casl(self) -> None:
        # A consent-required country that is NOT hard-blocked still gets the CASL/GDPR cold-hold.
        c = oc.OutreachContact("c4", "person3@example.com", country="GB", consent=False)
        d = oc.consent_decision(
            c, consent_required_countries=CONSENT_REQUIRED, blocked_countries=BLOCKED
        )
        assert d == oc.SendDecision("c4", oc.HOLD, "cold_consent_required:GB")

    def test_cold_unknown_jurisdiction_is_held_failsafe(self) -> None:
        c = oc.OutreachContact("c5", "person2@example.com", country=None, consent=False)
        d = oc.consent_decision(
            c, consent_required_countries=CONSENT_REQUIRED, blocked_countries=BLOCKED
        )
        assert d == oc.SendDecision("c5", oc.HOLD, "cold_unknown_jurisdiction")

    def test_unsubscribed_is_held_even_if_opted_in_us(self) -> None:
        c = oc.OutreachContact("c6", "person2@example.com", country="US", consent=True, unsubscribed=True)
        d = oc.consent_decision(
            c, consent_required_countries=CONSENT_REQUIRED, blocked_countries=BLOCKED
        )
        assert d == oc.SendDecision("c6", oc.HOLD, "suppressed_unsubscribed")

    def test_bounced_is_held(self) -> None:
        c = oc.OutreachContact("c7", "person2@example.com", country="US", consent=True, bounced=True)
        d = oc.consent_decision(
            c, consent_required_countries=CONSENT_REQUIRED, blocked_countries=BLOCKED
        )
        assert d == oc.SendDecision("c7", oc.HOLD, "suppressed_bounced")


class TestWarmupDailyCap:
    @pytest.mark.parametrize(
        "age,expected",
        [(-3, 20), (0, 20), (1, 40), (2, 80), (3, 160), (6, 1280), (7, 2000), (30, 2000)],
    )
    def test_ramp_doubles_then_clamps_at_ceiling(self, age: int, expected: int) -> None:
        # start=20, growth=2, ceiling=2000 -> 20,40,80,160,320,640,1280, then clamp at 2000.
        assert oc.warmup_daily_cap(age, start=20, growth=2, ceiling=2000) == expected


class TestSelectSendable:
    def test_noncompliant_message_holds_the_entire_batch(self) -> None:
        bad = oc.OutreachMessage(
            subject="hi", html="x", text="x", from_email="person4@example.com",
            from_name="X", unsubscribe_url=None, physical_address=None,
        )
        contacts = [oc.OutreachContact("a", "person2@example.com", country="US")]
        to_send, held = oc.select_sendable(
            contacts, message=bad, consent_required_countries=CONSENT_REQUIRED, daily_cap=100
        )
        assert to_send == []
        assert held == [
            oc.SendDecision("a", oc.HOLD, "message_noncompliant:missing_unsubscribe,missing_physical_address")
        ]

    def test_mixed_batch_sends_only_permitted_contacts(self) -> None:
        contacts = [
            oc.OutreachContact("us_cold", "person5@example.com", country="US", consent=False),
            oc.OutreachContact("ca_cold", "person6@example.com", country="CA", consent=False),
            oc.OutreachContact("ca_optin", "person7@example.com", country="CA", consent=True),
            oc.OutreachContact("us_unsub", "person8@example.com", country="US", consent=True, unsubscribed=True),
        ]
        to_send, held = oc.select_sendable(
            contacts, message=_complete_message(),
            consent_required_countries=CONSENT_REQUIRED, daily_cap=100, blocked_countries=BLOCKED,
        )
        # Only the US cold contact sends. BOTH Canadians are held by the hard block (even the opted-in
        # one), and the unsubscribed US contact is suppressed.
        assert [d.contact_id for d in to_send] == ["us_cold"]
        assert {d.contact_id: d.reason for d in held} == {
            "ca_cold": "country_blocked:CA",
            "ca_optin": "country_blocked:CA",
            "us_unsub": "suppressed_unsubscribed",
        }

    def test_daily_cap_overflow_is_held(self) -> None:
        contacts = [
            oc.OutreachContact("a", "person2@example.com", country="US", consent=True),
            oc.OutreachContact("b", "person9@example.com", country="US", consent=True),
            oc.OutreachContact("c", "person10@example.com", country="US", consent=True),
        ]
        # cap 2, already sent 1 today -> only 1 more may go; the other two overflow.
        to_send, held = oc.select_sendable(
            contacts, message=_complete_message(),
            consent_required_countries=CONSENT_REQUIRED, daily_cap=2, already_sent_today=1,
        )
        assert [d.contact_id for d in to_send] == ["a"]
        assert [d.reason for d in held] == ["daily_cap_reached", "daily_cap_reached"]
