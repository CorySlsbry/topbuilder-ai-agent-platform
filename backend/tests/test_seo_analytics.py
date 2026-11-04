"""Unit + property tests for the deterministic SEO/GEO Marketing engine."""
from __future__ import annotations

from datetime import date

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.agents.seo import analytics as a
from app.agents.seo.models import BlogSource, CommentThread, Competitor, SeoData, SitePage

AS_OF = date(2026, 6, 8)


class TestPrimitives:
    @pytest.mark.parametrize(
        "facts, words, expected",
        [(10, 2000, 1.0), (6, 2200, 0.5454545), (29, 2900, 2.0), (0, 0, 0.0)],
    )
    def test_facts_per_200_words(self, facts: int, words: int, expected: float) -> None:
        assert a.facts_per_200_words(facts, words) == pytest.approx(expected, abs=1e-6)

    def test_fact_density_subscore_caps_at_one(self) -> None:
        assert a.fact_density_subscore(2.0) == 1.0
        assert a.fact_density_subscore(0.5) == pytest.approx(0.5)

    @pytest.mark.parametrize(
        "count, is_faq, expected",
        [
            (0, False, 1.0),  # band applies only to FAQ pages
            (15, True, 1.0),  # lower band edge passes
            (30, True, 1.0),  # upper band edge passes
            (8, True, 8 / 15),
            (40, True, 30 / 40),
        ],
    )
    def test_faq_subscore(self, count: int, is_faq: bool, expected: float) -> None:
        assert a.faq_subscore(count, is_faq) == pytest.approx(expected)

    @pytest.mark.parametrize("days, expected", [(0, 1.0), (30, 1.0), (60, 0.5), (210, 30 / 210)])
    def test_freshness_subscore(self, days: int, expected: float) -> None:
        assert a.freshness_subscore(days) == pytest.approx(expected)

    def test_length_subscore_caps_at_citable_target(self) -> None:
        assert a.length_subscore(2900) == 1.0
        assert a.length_subscore(5800) == 1.0
        assert a.length_subscore(1450) == pytest.approx(0.5)

    @pytest.mark.parametrize(
        "searches, difficulty, intent, source, expected",
        [
            (1300, 12, "commercial", "reddit", 92.2),  # 1300*1.3*1.2/22
            (2400, 18, "informational", "search", 85.7),  # 2400/28
            (900, 15, "transactional", "youtube", 62.1),  # 900*1.5*1.15/25
        ],
    )
    def test_opportunity_score_hand_computed(
        self, searches: int, difficulty: int, intent: str, source: str, expected: float
    ) -> None:
        assert a.opportunity_score(searches, difficulty, intent, source) == expected

    @given(st.integers(0, 100_000), st.integers(0, 100), st.integers(0, 100))
    def test_opportunity_score_monotone_in_difficulty(
        self, searches: int, d1: int, d2: int
    ) -> None:
        lo, hi = sorted((d1, d2))
        assert a.opportunity_score(searches, lo, "commercial", "reddit") >= a.opportunity_score(
            searches, hi, "commercial", "reddit"
        )

    @pytest.mark.parametrize(
        "matched, age, replies, expected",
        [(3, 3, 42, 97), (2, 6, 31, 76), (2, 12, 88, 71)],
    )
    def test_comment_relevance_hand_computed(
        self, matched: int, age: int, replies: int, expected: int
    ) -> None:
        assert a.comment_relevance_score(matched, age, replies) == expected

    @given(st.integers(0, 10), st.integers(0, 365), st.integers(0, 1000))
    def test_comment_relevance_bounded(self, matched: int, age: int, replies: int) -> None:
        assert 0 <= a.comment_relevance_score(matched, age, replies) <= 100

    @given(
        st.integers(1, 10_000),
        st.integers(0, 100),
        st.integers(0, 50),
        st.booleans(),
        st.integers(0, 730),
    )
    def test_page_score_bounded(
        self, words: int, facts: int, faq: int, is_faq: bool, days: int
    ) -> None:
        page = SitePage("p", "/p", words, facts, faq, is_faq, days)
        assert 0 <= a.page_score(page) <= 100


def _scenario() -> SeoData:
    competitors = [
        Competitor("CompA", "compa.example", 40, ["k1", "k2", "k3"], 0.40, "strong"),
        Competitor("CompB", "compb.example", 20, ["k4", "k5", "k6", "k7", "k8"], 0.10, "broad"),
    ]
    pages = [
        # fails fact density: 5*200/2000 = 0.5; score 15 + 25 + 25 + 20*(2000/2900) = 78.79 -> 79
        SitePage("Service", "/service", 2000, 5, 0, False, 10),
        # fails FAQ band (over): fd 10*200/1450=1.38->30; faq 30/40*25=18.75; fresh 25; len 10 -> 84
        SitePage("FAQ", "/faq", 1450, 10, 40, True, 5),
        # passes everything incl. the freshness boundary (30d is still <= benchmark): score 100
        SitePage("Guide", "/guide", 2900, 29, 0, False, 30),
    ]
    h2s = ["A", "B", "C", "D"]
    blogs = [
        BlogSource("kw-x", "Title X", 1000, 10, "reddit", "r/x thread", "transactional", h2s, "ix"),
        BlogSource("kw-y", "Title Y", 1000, 10, "search", "PAA", "informational", h2s, "iy"),
    ]
    threads = [
        # 0.5*1 + 0.3*1 + 0.2*1 = 1.0 -> 100 (age 7 = freshness boundary, replies 50 = saturation)
        CommentThread("reddit", "T1", "https://reddit.example/t1", 7, 50, ["s1", "s2", "s3"], "c1"),
        # 0.5*(1/3) + 0.3*(7/14) + 0.2*(25/50) = 0.41667 -> 42
        CommentThread("youtube", "T2", "https://youtube.example/t2", 14, 25, ["s1"], "c2"),
    ]
    return SeoData(AS_OF, competitors, pages, blogs, threads)


class TestCompetitorGaps:
    def test_sorted_by_missed_keywords_and_counted(self) -> None:
        gaps = a.analyze(_scenario()).competitor_gaps
        assert [(g.competitor, g.keywords_we_miss) for g in gaps] == [("CompB", 5), ("CompA", 3)]


class TestGeoAudit:
    def test_statuses_and_scores(self) -> None:
        audit = {p.page: p for p in a.analyze(_scenario()).geo_audit}
        assert (audit["Service"].status, audit["Service"].score) == ("below_benchmark", 79)
        assert (audit["FAQ"].status, audit["FAQ"].score) == ("below_benchmark", 84)
        assert (audit["Guide"].status, audit["Guide"].score) == ("pass", 100)

    def test_sorted_worst_first(self) -> None:
        assert [p.page for p in a.analyze(_scenario()).geo_audit] == ["Service", "FAQ", "Guide"]

    def test_fix_messages_name_the_failed_benchmark(self) -> None:
        audit = {p.page: p for p in a.analyze(_scenario()).geo_audit}
        assert len(audit["Service"].fixes) == 1
        assert "1-per-200" in audit["Service"].fixes[0]
        # 2000 words need ceil(2000/200)=10 facts; the page has 5 -> add 5
        assert "add 5 verifiable facts" in audit["Service"].fixes[0]
        assert len(audit["FAQ"].fixes) == 1
        assert "15-30" in audit["FAQ"].fixes[0]
        assert audit["Guide"].fixes == []

    def test_freshness_fix_past_boundary(self) -> None:
        stale = SitePage("Old", "/old", 2900, 29, 0, False, 31)
        audited = a.analyze(SeoData(AS_OF, [], [stale], [], [])).geo_audit[0]
        assert audited.status == "below_benchmark"
        assert "31 days" in audited.fixes[0] and "3.2x" in audited.fixes[0]


class TestBlogAndComments:
    def test_blog_scoring_and_order(self) -> None:
        blogs = a.analyze(_scenario()).blog_opportunities
        assert [(b.keyword, b.opportunity_score) for b in blogs] == [("kw-x", 90.0), ("kw-y", 50.0)]

    def test_comment_scoring_and_order(self) -> None:
        comments = a.analyze(_scenario()).comment_opportunities
        assert [(c.thread_title, c.relevance_score) for c in comments] == [("T1", 100), ("T2", 42)]


class TestSummaryAndMeta:
    def test_weekly_summary(self) -> None:
        s = a.analyze(_scenario()).weekly_summary
        assert (s.gaps_found, s.pages_below_benchmark, s.posts_planned, s.comments_drafted) == (
            8, 2, 2, 2,
        )

    def test_posts_planned_capped_by_available_opportunities(self) -> None:
        data = _scenario()
        one_blog = SeoData(AS_OF, data.competitors, data.pages, data.blog_sources[:1], [])
        assert a.analyze(one_blog).weekly_summary.posts_planned == 1

    def test_inputs_hash_stable_and_hex(self) -> None:
        h1 = a.analyze(_scenario()).inputs_hash
        h2 = a.analyze(_scenario()).inputs_hash
        assert h1 == h2 and len(h1) == 64
