"""Oracle + property tests for the deterministic A/R Collections engine (PURE, no DB).

Every asserted figure is an INDEPENDENT hand-computed oracle. Money is carried as integer **cents** in
the inputs; the engine keeps cents, so cent oracles are exact (no float division). The ``_scenario()``
mirrors the client's real Outstanding-A/R Google Sheet (Summit Heat Pumps; Alex discovery call
2026-06-16): real customer names, the workflow band, the aging buckets, and balances summing to >$400K.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.agents.collections import analytics as a
from app.agents.collections.drafts import build_drafts
from app.agents.collections.models import (
    CollectionsData,
    ContactPreference,
    OpenInvoice,
    PromiseToPay,
)

AS_OF = date(2026, 6, 15)


def _due_days_ago(n: int) -> date:
    """An invoice whose due date is `n` days before AS_OF (n>0 = overdue, n<0 = not yet due)."""
    return AS_OF - timedelta(days=n)


# --------------------------------------------------------------------------------------------
# 1. Pure primitives — aging bucket + days overdue
# --------------------------------------------------------------------------------------------
class TestAgingBucket:
    @pytest.mark.parametrize(
        "days, bucket",
        [
            (-10, a.BUCKET_CURRENT),
            (0, a.BUCKET_CURRENT),
            (1, a.BUCKET_1_30),
            (30, a.BUCKET_1_30),
            (31, a.BUCKET_31_60),
            (47, a.BUCKET_31_60),  # the demo "47-days-overdue -> 31-60" oracle
            (60, a.BUCKET_31_60),
            (61, a.BUCKET_61_90),
            (90, a.BUCKET_61_90),
            (91, a.BUCKET_91_120),
            (120, a.BUCKET_91_120),
            (121, a.BUCKET_121_PLUS),
            (400, a.BUCKET_121_PLUS),
        ],
    )
    def test_boundaries(self, days: int, bucket: str) -> None:
        assert a.aging_bucket(days) == bucket

    @given(st.integers(min_value=-1000, max_value=2000))
    def test_always_a_known_bucket(self, days: int) -> None:
        assert a.aging_bucket(days) in a.BUCKET_ORDER

    def test_days_overdue_sign(self) -> None:
        assert a.days_overdue(_due_days_ago(47), AS_OF) == 47
        assert a.days_overdue(_due_days_ago(-10), AS_OF) == -10
        assert a.days_overdue(AS_OF, AS_OF) == 0


class TestDunningLadder:
    @pytest.mark.parametrize(
        "bucket, step, channel",
        [
            (a.BUCKET_CURRENT, 0, a.CHANNEL_NONE),
            (a.BUCKET_1_30, 1, a.CHANNEL_EMAIL),
            (a.BUCKET_31_60, 2, a.CHANNEL_SMS),
            (a.BUCKET_61_90, 3, a.CHANNEL_CALL),
            (a.BUCKET_91_120, 4, a.CHANNEL_CALL),
            (a.BUCKET_121_PLUS, 5, a.CHANNEL_CALL),
        ],
    )
    def test_escalates_by_bucket(self, bucket: str, step: int, channel: str) -> None:
        s = a.dunning_step_for_bucket(bucket)
        assert (s.step, s.channel) == (step, channel)


class TestComplianceDowngrade:
    """TCPA / do-not-call gating happens BEFORE a channel is ever recommended."""

    def test_call_downgrades_to_email_when_do_not_call(self) -> None:
        step = a.dunning_step_for_bucket(a.BUCKET_61_90)  # call
        contact = ContactPreference("c", email="person1@example.com", phone="+1555", do_not_call=True)
        assert a.downgrade_for_compliance(step, contact).channel == a.CHANNEL_EMAIL

    def test_sms_downgrades_to_email_without_opt_in(self) -> None:
        step = a.dunning_step_for_bucket(a.BUCKET_31_60)  # sms
        contact = ContactPreference("c", email="person1@example.com", phone="+1555", sms_opt_in=False)
        assert a.downgrade_for_compliance(step, contact).channel == a.CHANNEL_EMAIL

    def test_sms_allowed_with_opt_in(self) -> None:
        step = a.dunning_step_for_bucket(a.BUCKET_31_60)
        contact = ContactPreference("c", email="person1@example.com", phone="+1555", sms_opt_in=True)
        assert a.downgrade_for_compliance(step, contact).channel == a.CHANNEL_SMS

    def test_no_reachable_channel_yields_none(self) -> None:
        step = a.dunning_step_for_bucket(a.BUCKET_61_90)  # call
        contact = ContactPreference("c", email=None, phone="+1555", do_not_call=True)
        assert a.downgrade_for_compliance(step, contact).channel == a.CHANNEL_NONE

    def test_missing_contact_blocks_all_channels(self) -> None:
        step = a.dunning_step_for_bucket(a.BUCKET_1_30)  # email
        assert a.downgrade_for_compliance(step, None).channel == a.CHANNEL_NONE


# --------------------------------------------------------------------------------------------
# 2. Scenario — mirrors the real sheet (names + a >$400K portfolio across the workflow band)
#   c1 National Dispatch Group   $120,000  due 47d ago  -> 31-60, stalled_our_court, step 2
#   c2 Saint Matthias Anglican   $125,000  due 130d ago -> 121+,  write_off_or_collections, step 5
#   c3 EB Renovations            $ 48,000  due 75d ago  -> 61-90, action_required, step 3
#   c4 Jolly Boys Cannabis       $ 40,000  due 20d ago  -> 1-30,  expecting_money (promise covers)
#   c5 Sam Campbell             $ 30,000  due 10d ahead -> current, reconciled, step 0
#   c6 Lindsey Davidson          $ 60,000  due 95d ago  -> 91-120, stalled_other_court (disputed)
#   open = 120+125+48+40+30+60 = $423,000  (>$400K, the documented pain)
# --------------------------------------------------------------------------------------------
def _scenario() -> CollectionsData:
    invoices = [
        OpenInvoice("I1", "c1", "National Dispatch Group", 12_000_000,
                    issued=_due_days_ago(77), due=_due_days_ago(47),
                    doc_number="1001", customer_segment="commercial"),
        OpenInvoice("I2", "c2", "Saint Matthias Anglican Church", 12_500_000,
                    issued=_due_days_ago(160), due=_due_days_ago(130),
                    doc_number="1002", customer_segment="commercial"),
        OpenInvoice("I3", "c3", "EB Renovations", 4_800_000,
                    issued=_due_days_ago(105), due=_due_days_ago(75),
                    doc_number="1003", customer_segment="commercial"),
        OpenInvoice("I4", "c4", "Jolly Boys Cannabis", 4_000_000,
                    issued=_due_days_ago(50), due=_due_days_ago(20),
                    doc_number="1004", customer_segment="commercial"),
        OpenInvoice("I5", "c5", "Sam Campbell", 3_000_000,
                    issued=_due_days_ago(20), due=_due_days_ago(-10),
                    doc_number="1005", customer_segment="residential"),
        OpenInvoice("I6", "c6", "Lindsey Davidson van Gerven", 6_000_000,
                    issued=_due_days_ago(125), due=_due_days_ago(95),
                    doc_number="1006", customer_segment="residential", in_dispute=True),
    ]
    promises = [
        PromiseToPay("c4", promised_date=date(2026, 6, 20), promised_amount_cents=4_000_000,
                     recorded_at=datetime(2026, 6, 12, tzinfo=timezone.utc), note="will pay Friday"),
    ]
    contacts = [
        ContactPreference("c1", email="person2@example.com", phone="+15551110001", sms_opt_in=True),
        ContactPreference("c2", email="person3@example.com", phone="+15551110002", sms_opt_in=False),
        ContactPreference("c3", email="person4@example.com", phone="+15551110003", sms_opt_in=True, do_not_call=True),
        ContactPreference("c4", email="person5@example.com", phone="+15551110004", sms_opt_in=True),
        ContactPreference("c5", email="sam@example.com", phone="+15551110005"),
        ContactPreference("c6", email="lindsey@example.com", phone="+15551110006"),
    ]
    return CollectionsData(as_of=AS_OF, invoices=invoices, promises=promises, contacts=contacts)


def _cust(analysis: a.CollectionsAnalysis, customer_id: str) -> a.WorklistCustomer:
    return next(c for c in analysis.worklist if c.customer_id == customer_id)


class TestWorklistBucketingAndStatus:
    def test_national_dispatch_47_days_is_31_60_step_2(self) -> None:
        c = _cust(a.analyze(_scenario()), "c1")
        assert (c.oldest_days_overdue, c.bucket) == (47, a.BUCKET_31_60)
        assert c.status == a.STATUS_STALLED_OUR_COURT
        # sms-opt-in contact keeps step 2's SMS channel
        assert (c.dunning_step, c.dunning_channel) == (2, a.CHANNEL_SMS)
        assert c.balance_cents == 12_000_000

    def test_saint_matthias_121_plus_write_off(self) -> None:
        c = _cust(a.analyze(_scenario()), "c2")
        assert c.bucket == a.BUCKET_121_PLUS
        assert c.status == a.STATUS_WRITE_OFF_OR_COLLECTIONS
        assert c.dunning_step == 5
        assert c.owner == "Controller"

    def test_eb_reno_61_90_action_required_dnc_downgrades_call_to_email(self) -> None:
        c = _cust(a.analyze(_scenario()), "c3")
        assert c.bucket == a.BUCKET_61_90
        assert c.status == a.STATUS_ACTION_REQUIRED
        assert c.dunning_step == 3  # the step (severity) is unchanged...
        assert c.dunning_channel == a.CHANNEL_EMAIL  # ...but the call is downgraded (do_not_call)

    def test_jolly_boys_promise_parks_in_expecting_money(self) -> None:
        c = _cust(a.analyze(_scenario()), "c4")
        assert c.oldest_days_overdue == 20  # still overdue...
        assert c.status == a.STATUS_EXPECTING_MONEY  # ...but a covering promise parks escalation
        assert c.dunning_step == 0
        assert c.promise_date == date(2026, 6, 20)
        assert c.promise_amount_cents == 4_000_000

    def test_dale_campbell_not_yet_due_is_reconciled(self) -> None:
        c = _cust(a.analyze(_scenario()), "c5")
        assert c.bucket == a.BUCKET_CURRENT
        assert c.status == a.STATUS_RECONCILED
        assert (c.dunning_step, c.dunning_channel) == (0, a.CHANNEL_NONE)

    def test_disputed_invoice_is_stalled_other_court(self) -> None:
        c = _cust(a.analyze(_scenario()), "c6")
        assert c.status == a.STATUS_STALLED_OTHER_COURT
        assert c.owner == "Account Manager"


class TestWorklistOrderingAndTotals:
    def test_worklist_sorted_oldest_first(self) -> None:
        worklist = a.analyze(_scenario()).worklist
        ages = [c.oldest_days_overdue for c in worklist]
        assert ages == sorted(ages, reverse=True)
        assert worklist[0].customer_id == "c2"  # 130 days, the oldest

    def test_portfolio_open_balance_over_400k(self) -> None:
        t = a.analyze(_scenario()).totals
        assert t.open_balance_cents == 42_300_000  # $423,000
        assert t.customers == 6

    def test_bucket_ladder_oracle(self) -> None:
        t = a.analyze(_scenario()).totals
        assert t.bucket_balances_cents == {
            a.BUCKET_CURRENT: 3_000_000,    # Sam (not yet due)
            a.BUCKET_1_30: 4_000_000,       # Jolly Boys (20d)
            a.BUCKET_31_60: 12_000_000,     # National Dispatch (47d)
            a.BUCKET_61_90: 4_800_000,      # EB Reno (75d)
            a.BUCKET_91_120: 6_000_000,     # Lindsey (95d)
            a.BUCKET_121_PLUS: 12_500_000,  # Saint Matthias (130d)
        }

    def test_pct_current_and_over_30_oracles(self) -> None:
        t = a.analyze(_scenario()).totals
        # current 3,000,000 / 42,300,000 = 7.09%
        assert t.pct_current == pytest.approx(7.09, abs=0.01)
        # over-30 = 31-60 + 61-90 + 91-120 + 121+ = 12,000,000+4,800,000+6,000,000+12,500,000 = 35,300,000
        # 35,300,000 / 42,300,000 = 83.45%
        assert t.pct_over_30 == pytest.approx(83.45, abs=0.01)

    def test_at_risk_is_91_plus(self) -> None:
        t = a.analyze(_scenario()).totals
        # 91-120 (6,000,000) + 121+ (12,500,000) = 18,500,000
        assert t.at_risk_balance_cents == 18_500_000

    def test_overdue_excludes_current(self) -> None:
        t = a.analyze(_scenario()).totals
        assert t.overdue_balance_cents == t.open_balance_cents - t.current_balance_cents
        assert t.overdue_balance_cents == 39_300_000

    def test_customers_needing_action_excludes_reconciled_and_promised(self) -> None:
        t = a.analyze(_scenario()).totals
        # 6 customers - Sam (reconciled) - Jolly Boys (expecting_money) = 4
        assert t.customers_needing_action == 4


class TestInvariants:
    def test_bucket_balances_sum_to_open(self) -> None:
        t = a.analyze(_scenario()).totals
        assert sum(t.bucket_balances_cents.values()) == t.open_balance_cents

    def test_per_customer_buckets_sum_to_customer_balance(self) -> None:
        for c in a.analyze(_scenario()).worklist:
            assert sum(c.bucket_balances_cents.values()) == c.balance_cents

    def test_inputs_hash_stable_and_hex(self) -> None:
        h1 = a.analyze(_scenario()).inputs_hash
        h2 = a.analyze(_scenario()).inputs_hash
        assert h1 == h2
        assert len(h1) == 64 and all(ch in "0123456789abcdef" for ch in h1)

    def test_empty_portfolio_is_zero_not_divide_by_zero(self) -> None:
        res = a.analyze(CollectionsData(as_of=AS_OF, invoices=[]))
        assert res.totals.open_balance_cents == 0
        assert res.totals.pct_current == 0.0
        assert res.totals.customers == 0

    @given(st.integers(min_value=1, max_value=50_000_00), st.integers(min_value=-30, max_value=400))
    def test_single_invoice_balance_equals_input(self, cents: int, age: int) -> None:
        inv = OpenInvoice("X", "c", "Cust", cents, issued=_due_days_ago(age + 30), due=_due_days_ago(age))
        res = a.analyze(CollectionsData(as_of=AS_OF, invoices=[inv]))
        assert res.totals.open_balance_cents == cents
        assert _cust(res, "c").balance_cents == cents


# --------------------------------------------------------------------------------------------
# 3. Dunning drafts — quote the real figures, carry compliance opt-outs
# --------------------------------------------------------------------------------------------
class TestDunningDrafts:
    def test_email_quotes_exact_balance_and_age(self) -> None:
        c = _cust(a.analyze(_scenario()), "c1")  # $120,000, 47 days
        d = build_drafts(c)
        assert d.email_body is not None
        assert "$120,000.00" in d.email_body
        assert "47 days overdue" in d.email_body

    def test_sms_present_for_step2_and_carries_stop_optout(self) -> None:
        c = _cust(a.analyze(_scenario()), "c1")  # step 2, sms
        d = build_drafts(c)
        assert d.channel == a.CHANNEL_SMS
        assert d.sms_body is not None and "Reply STOP" in d.sms_body
        assert "$120,000.00" in d.sms_body

    def test_email_carries_can_spam_optout(self) -> None:
        c = _cust(a.analyze(_scenario()), "c2")  # 121+, email exists
        d = build_drafts(c)
        assert d.email_body is not None
        assert "opt out" in d.email_body.lower()

    def test_call_script_has_mini_miranda_when_channel_is_call(self) -> None:
        # Saint Matthias: 121+ step 5, contact has no do_not_call -> channel stays call
        c = _cust(a.analyze(_scenario()), "c2")
        assert c.dunning_channel == a.CHANNEL_CALL
        d = build_drafts(c)
        assert d.call_script is not None
        assert "attempt to collect a debt" in d.call_script
        assert "quiet hours" in d.call_script.lower()

    def test_reconciled_customer_has_no_drafts(self) -> None:
        c = _cust(a.analyze(_scenario()), "c5")  # reconciled
        d = build_drafts(c)
        assert d.email_body is None and d.sms_body is None and d.call_script is None

    def test_promise_customer_draft_mentions_promise(self) -> None:
        # Jolly Boys parks on a promise -> channel none -> no drafts, but the worklist next_action carries it
        c = _cust(a.analyze(_scenario()), "c4")
        assert "2026-06-20" in c.next_action
