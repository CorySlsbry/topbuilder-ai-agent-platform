"""Wiring test for the Email agent's fixture adapter -> engine -> schema -> narration path.

No database, no network. Asserts the realistic fixture inbox produces the exact, hand-computed result
the dashboard (and the landing page) will show, so the demo numbers can't silently drift.

Oracle (26 unread emails, 3 workflows):
  triage        = 7 needs_reply / 6 fyi / 9 trash / 4 workflow_report
  top-3 priority (score = value_usd*0.01 + min(age_h,72)*1.5 + 40 if commercial):
    EM-3001  $12,400 commercial bid, 6h   -> 124 + 9  + 40 = 173.0
    EM-3004  $6,200 renewal, 30h, comm.   ->  62 + 45 + 40 = 147.0
    EM-3002  $3,800 estimate ask, 26h     ->  38 + 39 + 0  =  77.0
  reply drafts  = 7, exactly 2 requires_human {EM-3005 angry, EM-3006 insurance}
  trash         = 9 (promo 4 / newsletter 3 / spam 2), every confidence >= 0.85
  workflows     = WF-102 "Estimate follow-up" underperforming (open 0.19 vs 0.35 benchmark,
                  reply 0.04 vs 0.12) with a proposed rewrite; WF-101 + WF-103 healthy, no rewrite.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from app.agents.email.analytics import analyze
from app.agents.email.data import assemble_inbox_data
from app.agents.email.reasoning import _template_narrative
from app.agents.email.schemas import EmailRunResult, build_result
from app.integrations.email_inbox.fixture_client import FixtureEmailInboxClient

AS_OF = date(2026, 6, 9)
TOP3_IDS = ["EM-3001", "EM-3004", "EM-3002"]
TOP3_SCORES = [173.0, 147.0, 77.0]
REQUIRES_HUMAN_IDS = {"EM-3005", "EM-3006"}
TRASH_IDS = {
    "EM-3020", "EM-3021", "EM-3022", "EM-3023", "EM-3024",
    "EM-3025", "EM-3026", "EM-3027", "EM-3028",
}


async def _analyze_fixtures():
    data = await assemble_inbox_data(FixtureEmailInboxClient(), as_of=AS_OF)
    return analyze(data)


class TestFixtureOracle:
    async def test_triage_totals(self) -> None:
        t = (await _analyze_fixtures()).totals
        assert (t.unread_total, t.needs_reply, t.fyi, t.trash_candidates, t.workflow_reports) == (26, 7, 6, 9, 4)

    async def test_top3_priorities_hand_computed(self) -> None:
        tops = (await _analyze_fixtures()).top_priorities
        assert [p.email_id for p in tops][:3] == TOP3_IDS
        assert [p.priority_score for p in tops][:3] == TOP3_SCORES
        assert tops[0].value_cents == 1_240_000  # the $12,400 commercial bid leads the briefing
        assert tops[0].age_hours == 6

    async def test_reply_drafts_counts_flags_confidences(self) -> None:
        drafts = (await _analyze_fixtures()).reply_drafts
        assert len(drafts) == 7
        assert {d.email_id for d in drafts if d.requires_human} == REQUIRES_HUMAN_IDS
        assert all(d.confidence == 0.6 for d in drafts if d.requires_human)
        assert all(d.confidence == 0.9 for d in drafts if not d.requires_human)
        assert drafts[0].email_id == "EM-3001"  # highest priority drafted first
        assert "$12,400" in drafts[0].draft_body and "Friday, June 12" in drafts[0].draft_body

    async def test_trash_queue_ids_categories_confidences(self) -> None:
        trash = (await _analyze_fixtures()).trash_queue
        assert {t.email_id for t in trash} == TRASH_IDS
        assert all(t.confidence >= 0.85 for t in trash)
        by_category: dict[str, int] = {}
        for t in trash:
            by_category[t.category] = by_category.get(t.category, 0) + 1
        assert by_category == {"promo": 4, "newsletter": 3, "spam": 2}
        by_id = {t.email_id: t for t in trash}
        assert by_id["EM-3020"].age_days == 12  # 288h
        assert trash[0].email_id == "EM-3025"   # oldest (20 days) first

    async def test_workflow_benchmarks_and_single_underperformer(self) -> None:
        by = {w.workflow_id: w for w in (await _analyze_fixtures()).workflows}
        under = by["WF-102"]
        assert under.name == "Estimate follow-up"
        assert (under.open_rate, under.reply_rate) == (0.19, 0.04)
        assert (under.benchmark_open_rate, under.benchmark_reply_rate) == (0.35, 0.12)
        assert under.status == "underperforming"
        assert under.booked_jobs == 2
        rewrite = under.proposed_rewrite
        assert rewrite is not None and rewrite.subject and rewrite.preview
        assert "19%" in rewrite.rationale and "35%" in rewrite.rationale
        assert "4%" in rewrite.rationale and "12%" in rewrite.rationale
        for wid in ("WF-101", "WF-103"):
            assert by[wid].status == "healthy" and by[wid].proposed_rewrite is None

    async def test_template_narration_quotes_the_figures(self) -> None:
        narration = _template_narrative(await _analyze_fixtures())
        assert "26 unread" in narration and "7 need a reply" in narration
        assert "$12,400" in narration
        assert "Estimate follow-up" in narration and "19%" in narration and "35%" in narration

    async def test_inputs_hash_stable(self) -> None:
        h1 = (await _analyze_fixtures()).inputs_hash
        h2 = (await _analyze_fixtures()).inputs_hash
        assert h1 == h2 and len(h1) == 64


class TestSchemas:
    async def test_result_matches_the_frontend_contract(self) -> None:
        analysis = await _analyze_fixtures()
        result = build_result(
            analysis,
            narrative=_template_narrative(analysis),
            analysis_timestamp=datetime(2026, 6, 9, 13, 0, tzinfo=timezone.utc),
            run_id=uuid.uuid4(),
        )
        dumped = result.model_dump(mode="json")
        # exact spec field names — the frontend is built against these
        assert {
            "run_id", "agent", "analysis_timestamp", "briefing", "reply_drafts",
            "trash_queue", "workflows", "narration", "reasoning_logs", "inputs_hash",
        } <= set(dumped)
        assert dumped["agent"] == "email"
        assert set(dumped["briefing"]) == {
            "unread_total", "needs_reply", "fyi", "trash_candidates",
            "workflow_reports", "top_priorities",
        }
        assert set(dumped["briefing"]["top_priorities"][0]) == {
            "email_id", "from_name", "subject", "reason", "value_usd", "age_hours", "priority_score",
        }
        assert dumped["briefing"]["top_priorities"][0]["value_usd"] == 12400.0
        assert set(dumped["reply_drafts"][0]) == {
            "email_id", "from_name", "subject", "draft_subject", "draft_body",
            "confidence", "requires_human",
        }
        assert set(dumped["trash_queue"][0]) == {
            "email_id", "from_name", "subject", "category", "age_days", "confidence",
        }
        assert set(dumped["workflows"][0]) == {
            "workflow_id", "name", "emails_sent", "open_rate", "reply_rate", "booked_jobs",
            "benchmark_open_rate", "benchmark_reply_rate", "status", "proposed_rewrite",
            "applied_rewrite",  # operator-applied copy (assistant's update_email_workflow)
        }
        rewrites = [w["proposed_rewrite"] for w in dumped["workflows"] if w["proposed_rewrite"]]
        assert len(rewrites) == 1
        assert set(rewrites[0]) == {"subject", "preview", "rationale"}
        assert isinstance(dumped["reasoning_logs"], list)

    async def test_round_trip_and_polish_overlay(self) -> None:
        analysis = await _analyze_fixtures()
        polished = {"EM-3001": {"draft_subject": "Polished subject", "draft_body": "Polished body."}}
        result = build_result(
            analysis,
            narrative="brief",
            analysis_timestamp=datetime(2026, 6, 9, 13, 0, tzinfo=timezone.utc),
            run_id=uuid.uuid4(),
            polished=polished,
        )
        revived = EmailRunResult.model_validate(result.model_dump(mode="json"))
        assert revived == result
        by_id = {d.email_id: d for d in revived.reply_drafts}
        assert by_id["EM-3001"].draft_subject == "Polished subject"
        assert by_id["EM-3001"].draft_body == "Polished body."
        # polish touches WORDING only — the flag + confidence figures are untouched
        assert by_id["EM-3001"].requires_human is False and by_id["EM-3001"].confidence == 0.9
        assert by_id["EM-3002"].draft_subject.startswith("Re: ")  # others keep the template
