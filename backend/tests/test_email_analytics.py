"""Unit tests for the deterministic email-triage engine.

Hand-computed oracle (12 emails, 4 workflows):
  needs_reply 4 (E1,E2,E3,E4) · fyi 2 (E5,E6) · trash 4 (E7 promo-hint, E8 promo-kw, E9 newsletter-kw,
  E10 spam-kw) · workflow_report 2 (E11 hint, E12 kw).
  Priority (value_usd*0.01 + min(age,72)*1.5 + 40 if commercial):
    E2 = 0 + 72*1.5         = 108.0   (age 100h capped at 72)
    E1 = 5000*0.01 + 10*1.5 + 40 = 105.0
    E4 = 0 + 4*1.5          = 6.0
    E3 = 0 + 2*1.5          = 3.0
  requires_human exactly {E3 (angry), E4 (legal topic)}.
  Workflows: W1 healthy · W2 underperforming (open 0.20 < 0.35*0.75) · W3 underperforming
  (reply 0.06 < 0.12*0.75) · W4 underperforming (0 sent -> rates 0.0).
"""
from __future__ import annotations

from datetime import date

from app.agents.email import analytics as a
from app.agents.email.models import EmailMessage, InboxData, WorkflowStats

AS_OF = date(2026, 6, 9)


def _email(eid: str, **kw) -> EmailMessage:
    base = {
        "from_name": f"Sender {eid}",
        "from_address": f"{eid.lower()}@example.com",
        "subject": f"Subject {eid}",
        "body_excerpt": "Nothing keyword-shaped here.",
        "age_hours": 0.0,
    }
    base.update(kw)
    return EmailMessage(id=eid, **base)


def _scenario() -> InboxData:
    emails = [
        _email("E1", category_hint="needs_reply", intent="bid_request", customer_name="Pat Lee",
               customer_tier="commercial", value_cents=500_000, age_hours=10,
               job_type="the lobby RTU swap", requested_date="Friday"),
        _email("E2", category_hint="needs_reply", intent="schedule_request", age_hours=100,
               customer_tier="residential"),
        _email("E3", category_hint="needs_reply", intent="complaint", sentiment="angry", age_hours=2),
        _email("E4", subject="Invoice #12 question?", intent="invoice_question", topic="legal",
               age_hours=4),  # no hint: '?' keyword -> needs_reply
        _email("E5", category_hint="fyi"),
        _email("E6", subject="Shipment notice", body_excerpt="Your parts left the warehouse."),
        _email("E7", category_hint="promo", age_hours=49),
        _email("E8", subject="Mega deal 20% off compressors", age_hours=30),
        _email("E9", subject="Trade Digest", age_hours=240),
        _email("E10", subject="Urgent invoice - wire transfer required", age_hours=5),
        _email("E11", category_hint="workflow_report"),
        _email("E12", subject="Your weekly workflow report"),
    ]
    workflows = [
        WorkflowStats("W1", "Review request", 100, 40, 12, 0),
        WorkflowStats("W2", "Estimate follow-up", 100, 20, 10, 1),
        WorkflowStats("W3", "Win-back", 100, 40, 6, 0),
        WorkflowStats("W4", "Dormant sequence", 0, 0, 0, 0),
    ]
    return InboxData(as_of=AS_OF, emails=emails, workflows=workflows)


class TestClassification:
    def test_hint_wins_with_hint_confidence(self) -> None:
        bucket, cat, conf = a.classify(_email("X", category_hint="needs_reply"))
        assert (bucket, cat, conf) == ("needs_reply", None, a.HINT_CONFIDENCE)

    def test_trash_hint_maps_to_trash_bucket_with_category(self) -> None:
        assert a.classify(_email("X", category_hint="newsletter")) == ("trash", "newsletter", a.HINT_CONFIDENCE)

    def test_spam_keyword_beats_reply_keyword(self) -> None:
        # "invoice" is a reply keyword, but "wire transfer" must claim it for spam first.
        bucket, cat, conf = a.classify(_email("X", subject="Urgent invoice - wire transfer required"))
        assert (bucket, cat) == ("trash", "spam") and conf >= 0.85

    def test_promo_and_newsletter_keywords(self) -> None:
        assert a.classify(_email("X", subject="Mega deal 20% off"))[:2] == ("trash", "promo")
        assert a.classify(_email("X", subject="Trade Digest"))[:2] == ("trash", "newsletter")

    def test_workflow_keyword(self) -> None:
        assert a.classify(_email("X", subject="Your weekly workflow report"))[0] == "workflow_report"

    def test_question_mark_keyword_needs_reply(self) -> None:
        assert a.classify(_email("X", subject="Was the charge included?"))[0] == "needs_reply"

    def test_default_is_fyi(self) -> None:
        assert a.classify(_email("X", subject="Shipment notice"))[0] == "fyi"


class TestPriorityScore:
    def test_value_age_and_commercial_bonus(self) -> None:
        e = _email("X", value_cents=500_000, age_hours=10, customer_tier="commercial")
        assert a.priority_score(e) == 105.0  # 5000*0.01 + 10*1.5 + 40

    def test_age_capped_at_72_hours(self) -> None:
        assert a.priority_score(_email("X", age_hours=100)) == 108.0  # 72*1.5, not 150

    def test_no_bonus_for_residential(self) -> None:
        assert a.priority_score(_email("X", age_hours=10, customer_tier="residential")) == 15.0


class TestRequiresHuman:
    def test_angry_and_legal_and_insurance_flag(self) -> None:
        assert a.requires_human(_email("X", sentiment="angry"))
        assert a.requires_human(_email("X", topic="legal"))
        assert a.requires_human(_email("X", topic="insurance"))
        assert not a.requires_human(_email("X", sentiment="neutral", topic=None))


class TestEngine:
    def test_totals(self) -> None:
        t = a.analyze(_scenario()).totals
        assert (t.unread_total, t.needs_reply, t.fyi, t.trash_candidates, t.workflow_reports) == (12, 4, 2, 4, 2)

    def test_priority_order_and_scores_hand_computed(self) -> None:
        tops = a.analyze(_scenario()).top_priorities
        assert [p.email_id for p in tops][:3] == ["E2", "E1", "E4"]
        assert [p.priority_score for p in tops][:3] == [108.0, 105.0, 6.0]

    def test_one_draft_per_needs_reply_email(self) -> None:
        analysis = a.analyze(_scenario())
        assert len(analysis.reply_drafts) == analysis.totals.needs_reply == 4

    def test_requires_human_ids_and_confidences(self) -> None:
        drafts = {d.email_id: d for d in a.analyze(_scenario()).reply_drafts}
        assert {i for i, d in drafts.items() if d.requires_human} == {"E3", "E4"}
        assert drafts["E3"].confidence == a.REPLY_CONFIDENCE_HUMAN
        assert drafts["E1"].confidence == a.REPLY_CONFIDENCE

    def test_draft_templates_interpolate_extracted_fields(self) -> None:
        drafts = {d.email_id: d for d in a.analyze(_scenario()).reply_drafts}
        assert "$5,000" in drafts["E1"].draft_body and "Friday" in drafts["E1"].draft_body
        assert drafts["E1"].draft_subject == "Re: Subject E1"
        assert "sorry" in drafts["E3"].draft_body.lower()

    def test_trash_queue_categories_ages_confidences(self) -> None:
        trash = {t.email_id: t for t in a.analyze(_scenario()).trash_queue}
        assert {i: t.category for i, t in trash.items()} == {
            "E7": "promo", "E8": "promo", "E9": "newsletter", "E10": "spam"
        }
        assert trash["E7"].age_days == 2  # 49h // 24
        assert all(t.confidence >= 0.85 for t in trash.values())

    def test_workflow_statuses_each_failure_mode(self) -> None:
        by = {w.workflow_id: w for w in a.analyze(_scenario()).workflows}
        assert by["W1"].status == "healthy"
        assert by["W2"].status == "underperforming"  # open 0.20 < 0.2625
        assert by["W3"].status == "underperforming"  # reply 0.06 < 0.09
        assert by["W4"].status == "underperforming"  # nothing sent
        assert (by["W2"].open_rate, by["W2"].reply_rate) == (0.2, 0.1)
        assert by["W1"].benchmark_open_rate == a.BENCHMARK_OPEN_RATE
        assert by["W1"].benchmark_reply_rate == a.BENCHMARK_REPLY_RATE

    def test_rewrite_only_for_underperformers_and_cites_benchmarks(self) -> None:
        by = {w.workflow_id: w for w in a.analyze(_scenario()).workflows}
        assert by["W1"].proposed_rewrite is None
        rewrite = by["W2"].proposed_rewrite
        assert rewrite is not None
        assert rewrite.subject == "Quick question about your estimate"
        assert "20%" in rewrite.rationale and "35%" in rewrite.rationale and "12%" in rewrite.rationale

    def test_inputs_hash_stable_and_hex(self) -> None:
        h1, h2 = a.analyze(_scenario()).inputs_hash, a.analyze(_scenario()).inputs_hash
        assert h1 == h2 and len(h1) == 64
