"""Wiring test for the SEO agent's fixture adapter -> engine -> schema -> narration path.

No database, no network. Asserts the demo-tenant intel fixtures produce the exact, hand-computed
weekly review the dashboard (and the landing page) will show, so the demo numbers can't silently
drift. Oracle:

  competitor gaps   = 23   (Front Range 9 + Mile High 8 + Summit 6 missed keywords)
  pages audited     = 5, exactly 3 below the 2026 GEO benchmarks:
                      AC Repair  82/100  fact density 0.55 per 200 words (< the 1/200 floor)
                      FAQ        78/100  8 questions (< the 15-30 band)
                      About Us   67/100  210 days stale (> the 30-day freshness benchmark)
                      Homepage   97/100  pass · Water Heater Cost Guide  98/100  pass
  blog opportunities = 8; #1 = "after hours answering service for hvac cost"
                      (reddit r/HVAC, 1,300/mo, difficulty 12 -> 1300*1.3*1.2/22 = 92.2)
  comment drafts     = 3 (2 reddit + 1 youtube), relevance 97 / 76 / 71
  weekly_summary     = {gaps_found: 23, pages_below_benchmark: 3, posts_planned: 2,
                        comments_drafted: 3}
"""
from __future__ import annotations

from datetime import date, datetime

from app.agents.seo.analytics import analyze
from app.agents.seo.data import assemble_seo_data
from app.agents.seo.reasoning import _template_narrative
from app.agents.seo.schemas import build_result
from app.integrations.seo_intel.fixture_client import FixtureSeoIntelClient

AS_OF = date(2026, 6, 8)
TOP_KEYWORD = "after hours answering service for hvac cost"
EXPECTED_BLOG_SCORES = [92.2, 85.7, 78.0, 77.6, 72.0, 62.1, 61.6, 57.5]
EXPECTED_WEEKLY_SUMMARY = {
    "gaps_found": 23,
    "pages_below_benchmark": 3,
    "posts_planned": 2,
    "comments_drafted": 3,
}


async def _analyze_fixtures():
    data = await assemble_seo_data(FixtureSeoIntelClient(), as_of=AS_OF)
    return analyze(data)


class TestCompetitorOracle:
    async def test_23_total_gaps_across_three_competitors(self) -> None:
        gaps = (await _analyze_fixtures()).competitor_gaps
        assert [(g.competitor, g.keywords_we_miss) for g in gaps] == [
            ("Front Range Mechanical", 9),
            ("Mile High Plumbing & Air", 8),
            ("Summit Home Services", 6),
        ]
        assert sum(g.keywords_we_miss for g in gaps) == 23

    async def test_top_competitor_fields(self) -> None:
        top = (await _analyze_fixtures()).competitor_gaps[0]
        assert (top.domain, top.domain_rating, top.ai_citation_share) == (
            "frontrangemech.com", 38, 0.31,
        )


class TestGeoAuditOracle:
    async def test_exactly_three_pages_below_benchmark(self) -> None:
        audit = (await _analyze_fixtures()).geo_audit
        assert len(audit) == 5
        below = [p.page for p in audit if p.status == "below_benchmark"]
        assert sorted(below) == ["AC Repair", "About Us", "FAQ"]

    async def test_each_failure_is_the_designated_benchmark(self) -> None:
        audit = {p.page: p for p in (await _analyze_fixtures()).geo_audit}
        # AC Repair fails ONLY fact density: 6 facts in 2200 words = 0.55 per 200
        assert len(audit["AC Repair"].fixes) == 1
        assert "1-per-200" in audit["AC Repair"].fixes[0]
        assert audit["AC Repair"].facts_per_200_words == 0.55
        # FAQ fails ONLY the question band: 8 questions vs 15-30
        assert len(audit["FAQ"].fixes) == 1
        assert "8 questions" in audit["FAQ"].fixes[0] and "15-30" in audit["FAQ"].fixes[0]
        # About Us fails ONLY freshness: 210 days vs <30
        assert len(audit["About Us"].fixes) == 1
        assert "210 days" in audit["About Us"].fixes[0] and "3.2x" in audit["About Us"].fixes[0]

    async def test_hand_computed_scores(self) -> None:
        # score = 30*fact_density + 25*faq + 25*freshness + 20*length, rounded:
        #   Homepage  30 + 25 + 25 + 20*(2400/2900) = 96.55 -> 97
        #   AC Repair 30*(0.5454..) + 25 + 25 + 20*(2200/2900) = 81.54 -> 82
        #   FAQ       30 + 25*(8/15) + 25 + 20*(1450/2900) = 78.33 -> 78
        #   About Us  30 + 25 + 25*(30/210) + 20*(1160/2900) = 66.57 -> 67
        #   Guide     30 + 25 + 25 + 20*(2610/2900) = 98.0 -> 98
        audit = {p.page: (p.score, p.status) for p in (await _analyze_fixtures()).geo_audit}
        assert audit == {
            "Homepage": (97, "pass"),
            "AC Repair": (82, "below_benchmark"),
            "FAQ": (78, "below_benchmark"),
            "About Us": (67, "below_benchmark"),
            "Water Heater Installation Cost Guide": (98, "pass"),
        }

    async def test_audit_sorted_worst_first(self) -> None:
        scores = [p.score for p in (await _analyze_fixtures()).geo_audit]
        assert scores == sorted(scores)
        assert (await _analyze_fixtures()).geo_audit[0].page == "About Us"


class TestBlogOpportunityOracle:
    async def test_eight_opportunities_with_hand_computed_scores(self) -> None:
        blogs = (await _analyze_fixtures()).blog_opportunities
        assert len(blogs) == 8
        assert [b.opportunity_score for b in blogs] == EXPECTED_BLOG_SCORES

    async def test_top_opportunity_is_the_after_hours_keyword(self) -> None:
        # 1300 searches * 1.3 commercial * 1.2 reddit / (12 difficulty + 10) = 92.2
        top = (await _analyze_fixtures()).blog_opportunities[0]
        assert top.keyword == TOP_KEYWORD
        assert (top.monthly_searches, top.difficulty, top.source) == (1300, 12, "reddit")
        assert "r/HVAC" in top.source_detail
        assert top.opportunity_score == 92.2

    async def test_every_outline_is_4_to_6_h2s_with_a_draft_intro(self) -> None:
        for b in (await _analyze_fixtures()).blog_opportunities:
            assert 4 <= len(b.outline) <= 6, b.keyword
            assert len(b.draft_intro) > 100, b.keyword

    async def test_sources_cover_reddit_youtube_and_search(self) -> None:
        sources = {b.source for b in (await _analyze_fixtures()).blog_opportunities}
        assert sources == {"reddit", "youtube", "search"}


class TestCommentOracle:
    async def test_three_drafts_two_reddit_one_youtube(self) -> None:
        comments = (await _analyze_fixtures()).comment_opportunities
        assert [c.platform for c in comments] == ["reddit", "reddit", "youtube"]
        assert [c.relevance_score for c in comments] == [97, 76, 71]

    async def test_drafts_are_owner_voice_without_link_spam(self) -> None:
        for c in (await _analyze_fixtures()).comment_opportunities:
            assert "http" not in c.draft_comment.lower(), c.thread_title  # helpful-first, no links
            assert any(w in c.draft_comment for w in ("We ", "we ", "I'd", "I ")), c.thread_title
            assert len(c.draft_comment) > 200, c.thread_title


class TestWeeklySummaryOracle:
    async def test_weekly_summary_dict_equality(self) -> None:
        analysis = await _analyze_fixtures()
        result = build_result(
            analysis, narrative="n/a", analysis_timestamp=datetime(2026, 6, 8, 6, 0)
        )
        assert result.weekly_summary.model_dump() == EXPECTED_WEEKLY_SUMMARY


class TestResultSchema:
    async def test_response_shape_matches_the_frontend_contract(self) -> None:
        analysis = await _analyze_fixtures()
        result = build_result(
            analysis, narrative="n/a", analysis_timestamp=datetime(2026, 6, 8, 6, 0)
        )
        body = result.model_dump(mode="json")
        assert result.agent == "seo"
        assert set(body) == {
            "run_id", "agent", "analysis_timestamp", "competitor_gaps", "geo_audit",
            "blog_opportunities", "comment_opportunities", "weekly_summary", "narration",
            "reasoning_logs", "inputs_hash",
        }
        assert set(body["competitor_gaps"][0]) == {
            "competitor", "domain", "domain_rating", "keywords_we_miss", "ai_citation_share",
            "notes",
        }
        assert set(body["geo_audit"][0]) == {
            "page", "url", "word_count", "facts_per_200_words", "faq_count", "freshness_days",
            "score", "status", "fixes",
        }
        assert set(body["blog_opportunities"][0]) == {
            "keyword", "monthly_searches", "difficulty", "source", "source_detail", "intent",
            "opportunity_score", "outline", "draft_intro",
        }
        assert set(body["comment_opportunities"][0]) == {
            "platform", "thread_title", "url", "relevance_score", "draft_comment",
        }
        assert body["reasoning_logs"] == []

    async def test_template_narrative_quotes_the_marquee_figures(self) -> None:
        narrative = _template_narrative(await _analyze_fixtures())
        assert "23 keyword gaps" in narrative  # quoted, not recomputed
        assert "3 of 5" in narrative
        assert TOP_KEYWORD in narrative
        assert "92.2" in narrative

    async def test_inputs_hash_stable_and_hex(self) -> None:
        h1 = (await _analyze_fixtures()).inputs_hash
        h2 = (await _analyze_fixtures()).inputs_hash
        assert h1 == h2 and len(h1) == 64
