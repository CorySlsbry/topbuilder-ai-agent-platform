"""Oracle + property tests for the EOS communication-hub engine (PURE, no DB).

Covers the two surfaces beyond the scorecard: the L10 **Issues** list (create / resolve / sort /
summary) and the **Business Plan** (annual goals on-track + attainment, budget-to-actual variance +
favorability, and the trailing-12 P&L trend). Every asserted figure is an INDEPENDENT hand-computed
oracle — derived here from first principles, never from the engine's own output. Money is carried as
integer **cents** in the raw inputs and emitted as **dollars** by the engine, so the usd oracles
divide by 100.
"""
from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.org import eos
from app.org import eos_data as ed
from app.org.eos import (
    AnnualGoal,
    BudgetLine,
    BusinessPlan,
    Issue,
    TrailingPoint,
)

# --------------------------------------------------------------------------------------------
# 1. Issues — create / resolve / sort / summary (pure list transforms)
# --------------------------------------------------------------------------------------------


def _issue(
    iid: str, *, priority: int = 2, status: str = "open", created: str = "2026-06-01",
    resolved: str | None = None,
) -> Issue:
    return Issue(
        id=iid, title=f"issue {iid}", owner="Owner", department="finance",
        priority=priority, status=status, created=created, resolved=resolved,
    )


class TestNormalizePriority:
    @pytest.mark.parametrize("raw, expected", [(1, 1), (2, 2), (3, 3), (0, 1), (9, 3), (-4, 1)])
    def test_clamped_to_1_3(self, raw: int, expected: int) -> None:
        assert eos.normalize_priority(raw) == expected

    def test_non_numeric_defaults_to_medium(self) -> None:
        assert eos.normalize_priority("nope") == 2
        assert eos.normalize_priority(None) == 2


class TestValidateIssueTitle:
    def test_trims_and_keeps(self) -> None:
        assert eos.validate_issue_title("  fix A/R  ") == "fix A/R"

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            eos.validate_issue_title("   ")

    def test_caps_length_at_200(self) -> None:
        assert len(eos.validate_issue_title("x" * 500)) == 200


class TestMakeIssue:
    def test_builds_open_validated_issue(self) -> None:
        it = eos.make_issue(
            issue_id="iss-1", title=" close rate ", owner=" Dana ", department="sales",
            priority=9, created="2026-06-10",
        )
        assert (it.id, it.title, it.owner, it.department) == ("iss-1", "close rate", "Dana", "sales")
        assert (it.priority, it.status, it.created, it.resolved) == (3, "open", "2026-06-10", None)

    def test_blank_owner_becomes_unassigned(self) -> None:
        it = eos.make_issue(
            issue_id="iss-2", title="t", owner="  ", department="", priority=1, created="2026-06-10",
        )
        assert it.owner == "Unassigned"


class TestApplyIssueCreate:
    def test_prepends_newest_first_without_mutating(self) -> None:
        base = [_issue("a"), _issue("b")]
        new = eos.make_issue(
            issue_id="c", title="t", owner="o", department="d", priority=1, created="2026-06-12",
        )
        out = eos.apply_issue_create(base, new)
        assert [i.id for i in out] == ["c", "a", "b"]
        assert [i.id for i in base] == ["a", "b"]  # input untouched


class TestApplyIssueResolve:
    def test_closes_the_matching_open_issue(self) -> None:
        out = eos.apply_issue_resolve([_issue("a"), _issue("b")], "a", resolved_on="2026-06-15")
        by_id = {i.id: i for i in out}
        assert (by_id["a"].status, by_id["a"].resolved) == ("closed", "2026-06-15")
        assert (by_id["b"].status, by_id["b"].resolved) == ("open", None)

    def test_unknown_id_is_a_noop(self) -> None:
        base = [_issue("a")]
        assert eos.apply_issue_resolve(base, "zzz", resolved_on="2026-06-15") == base

    def test_resolving_a_closed_issue_is_idempotent(self) -> None:
        closed = _issue("a", status="closed", resolved="2026-06-01")
        out = eos.apply_issue_resolve([closed], "a", resolved_on="2026-06-20")
        # already closed: resolved date is NOT overwritten.
        assert out[0].resolved == "2026-06-01"


class TestSortIssues:
    def test_open_before_closed_then_priority_then_recency(self) -> None:
        issues = [
            _issue("old-open-p2", priority=2, created="2026-06-01"),
            _issue("closed-p1", priority=1, status="closed", created="2026-06-09", resolved="2026-06-10"),
            _issue("new-open-p1", priority=1, created="2026-06-08"),
            _issue("old-open-p1", priority=1, created="2026-06-02"),
        ]
        order = [i.id for i in eos.sort_issues(issues)]
        # open p1 newest, open p1 older, open p2, then the closed one last.
        assert order == ["new-open-p1", "old-open-p1", "old-open-p2", "closed-p1"]


class TestIssueSummary:
    def test_counts_and_open_by_priority(self) -> None:
        issues = [
            _issue("a", priority=1), _issue("b", priority=1), _issue("c", priority=3),
            _issue("d", priority=2, status="closed", resolved="2026-06-10"),
        ]
        s = eos.issue_summary(issues)
        assert s["total"] == 4
        assert s["open"] == 3
        assert s["closed"] == 1
        assert s["open_by_priority"] == {"1": 2, "2": 0, "3": 1}


# --------------------------------------------------------------------------------------------
# 2. Annual goals — on_track + attainment
# --------------------------------------------------------------------------------------------


def _goal(*, unit="usd", target, actual, higher=True) -> AnnualGoal:
    return AnnualGoal(key="g", label="g", unit=unit, target=target, actual=actual, higher_is_better=higher)


class TestGoalOnTrack:
    def test_higher_is_better(self) -> None:
        assert eos.goal_on_track(_goal(target=100, actual=120, higher=True)) is True
        assert eos.goal_on_track(_goal(target=100, actual=80, higher=True)) is False

    def test_lower_is_better(self) -> None:
        # A/R over 90 days: lower is healthier.
        assert eos.goal_on_track(_goal(target=50_000_00, actual=41_200_00, higher=False)) is True
        assert eos.goal_on_track(_goal(target=50_000_00, actual=60_000_00, higher=False)) is False

    def test_unmeasured_actual_is_none(self) -> None:
        assert eos.goal_on_track(_goal(target=100, actual=None)) is None


class TestGoalAttainment:
    def test_pct_of_goal(self) -> None:
        # $3,220,000 actual of a $7,000,000 target = 46.0%
        assert eos.goal_attainment_pct(_goal(target=700_000_000, actual=322_000_000)) == pytest.approx(46.0)

    def test_zero_target_is_none(self) -> None:
        assert eos.goal_attainment_pct(_goal(target=0, actual=10)) is None

    def test_unmeasured_actual_is_none(self) -> None:
        assert eos.goal_attainment_pct(_goal(target=100, actual=None)) is None

    def test_lower_is_better_is_direction_aware(self) -> None:
        # A cost/AR cap of $50k: being UNDER the cap must read as >=100% attained, not <100%.
        under = _goal(target=50_000_00, actual=41_200_00, higher=False)  # under the cap → beating it
        assert eos.goal_attainment_pct(under) == pytest.approx(121.36, abs=0.01)
        over = _goal(target=50_000_00, actual=100_000_00, higher=False)  # 2× over the cap
        assert eos.goal_attainment_pct(over) == pytest.approx(50.0)
        # Zero actual against a cap is fully attained (clamped, not a divide-by-zero).
        assert eos.goal_attainment_pct(_goal(target=50_000_00, actual=0, higher=False)) == 999.0


# --------------------------------------------------------------------------------------------
# 3. Budget-to-actual — per-line variance + favorability + derived net income
# --------------------------------------------------------------------------------------------


def _line(key, kind, budget, actual) -> BudgetLine:
    return BudgetLine(key=key, label=key, kind=kind, budget_cents=budget, actual_cents=actual)


class TestLineVariance:
    def test_variance_cents_signed(self) -> None:
        # actual 40,250 - budget 38,000 = +2,250 (in dollars: +$2,250 → cents +225,000)
        assert eos.line_variance_cents(_line("r", "revenue", 38_000_00, 40_250_00)) == 2_250_00

    def test_variance_pct_vs_budget(self) -> None:
        # (40,250 - 38,000) / 38,000 = 5.92%
        assert eos.line_variance_pct(_line("r", "revenue", 38_000_00, 40_250_00)) == pytest.approx(5.92)

    def test_zero_budget_pct_is_none(self) -> None:
        assert eos.line_variance_pct(_line("r", "revenue", 0, 100)) is None


class TestLineFavorable:
    def test_revenue_over_budget_is_favorable(self) -> None:
        assert eos.line_favorable(_line("r", "revenue", 100, 120)) is True
        assert eos.line_favorable(_line("r", "revenue", 120, 100)) is False

    def test_expense_over_budget_is_unfavorable(self) -> None:
        assert eos.line_favorable(_line("e", "expense", 100, 120)) is False
        assert eos.line_favorable(_line("e", "expense", 120, 100)) is True

    def test_cogs_over_budget_is_unfavorable(self) -> None:
        assert eos.line_favorable(_line("c", "cogs", 100, 130)) is False

    def test_on_budget_is_favorable(self) -> None:
        assert eos.line_favorable(_line("e", "expense", 100, 100)) is True


def _bta_lines() -> list[BudgetLine]:
    # Independent of the fixture — a small hand-computable set.
    return [
        _line("rev_a", "revenue", 30_000_00, 32_000_00),
        _line("rev_b", "revenue", 10_000_00, 9_000_00),
        _line("cogs_a", "cogs", 18_000_00, 19_000_00),
        _line("exp_a", "expense", 6_000_00, 5_500_00),
    ]


class TestNetIncomeDerivation:
    def test_net_income_is_revenue_minus_cogs_minus_expense(self) -> None:
        lines = _bta_lines()
        # budget net = (30,000 + 10,000) - 18,000 - 6,000 = 16,000
        assert eos.net_income_cents(lines, field="budget_cents") == 16_000_00
        # actual net = (32,000 + 9,000) - 19,000 - 5,500 = 16,500
        assert eos.net_income_cents(lines, field="actual_cents") == 16_500_00


class TestBudgetToActualTotals:
    def test_blocks_and_net_income_in_dollars(self) -> None:
        totals = eos.budget_to_actual_totals(_bta_lines())
        assert totals["revenue"] == {"budget": 40_000.0, "actual": 41_000.0, "variance": 1_000.0}
        assert totals["cogs"] == {"budget": 18_000.0, "actual": 19_000.0, "variance": 1_000.0}
        assert totals["expense"] == {"budget": 6_000.0, "actual": 5_500.0, "variance": -500.0}
        assert totals["net_income"] == {
            "budget": 16_000.0, "actual": 16_500.0, "variance": 500.0, "favorable": True,
        }

    def test_net_income_unfavorable_when_actual_below_budget(self) -> None:
        # Push COGS up so actual net drops below budget net.
        lines = [_line("rev", "revenue", 40_000_00, 40_000_00), _line("cogs", "cogs", 20_000_00, 25_000_00)]
        totals = eos.budget_to_actual_totals(lines)
        assert totals["net_income"]["budget"] == 20_000.0
        assert totals["net_income"]["actual"] == 15_000.0
        assert totals["net_income"]["favorable"] is False


# --------------------------------------------------------------------------------------------
# 4. Trailing-12 — per-point margin + blended totals
# --------------------------------------------------------------------------------------------


class TestTrailingMargin:
    def test_margin_pct(self) -> None:
        # 6,070,000 cents net / 64,650,000 cents revenue = 9.39%
        p = TrailingPoint(month="2026-06", revenue_cents=64_650_00, net_income_cents=6_070_00)
        assert eos.trailing_margin_pct(p) == pytest.approx(9.39)

    def test_zero_revenue_is_none(self) -> None:
        assert eos.trailing_margin_pct(TrailingPoint(month="x", revenue_cents=0, net_income_cents=10)) is None


class TestTrailing12Totals:
    def test_blended_totals_and_margin(self) -> None:
        points = [
            TrailingPoint(month="2026-05", revenue_cents=60_000_00, net_income_cents=6_000_00),
            TrailingPoint(month="2026-06", revenue_cents=40_000_00, net_income_cents=2_000_00),
        ]
        totals = eos.trailing_12_totals(points)
        # revenue $100,000 ; net $8,000 ; margin 8.0% ; 2 months
        assert totals == {"revenue": 100_000.0, "net_income": 8_000.0, "net_margin_pct": 8.0, "months": 2}

    def test_empty_is_zero_with_no_margin(self) -> None:
        totals = eos.trailing_12_totals([])
        assert totals == {"revenue": 0.0, "net_income": 0.0, "net_margin_pct": None, "months": 0}


class TestEngineProperties:
    @given(st.integers(1, 10_000_000), st.integers(0, 10_000_000))
    def test_revenue_line_favorable_iff_actual_ge_budget(self, budget: int, actual: int) -> None:
        line = _line("r", "revenue", budget, actual)
        assert eos.line_favorable(line) == (actual >= budget)

    @given(
        st.lists(
            st.tuples(
                st.sampled_from(["revenue", "cogs", "expense"]),
                st.integers(0, 5_000_000),
                st.integers(0, 5_000_000),
            ),
            min_size=1,
            max_size=12,
        )
    )
    def test_net_income_matches_independent_sum(self, raw: list[tuple[str, int, int]]) -> None:
        lines = [_line(f"l{i}", kind, b, a) for i, (kind, b, a) in enumerate(raw)]
        sign = {"revenue": 1, "cogs": -1, "expense": -1}
        expected = sum(sign[k] * a for (k, _b, a) in raw)
        assert eos.net_income_cents(lines, field="actual_cents") == expected


# --------------------------------------------------------------------------------------------
# 5. JSON serialization — the contract the frontend builds to
# --------------------------------------------------------------------------------------------


def _plan() -> BusinessPlan:
    return BusinessPlan(
        company="Test Co",
        fiscal_year=2026,
        period_label="June 2026",
        annual_goals=[_goal(unit="usd", target=700_000_000, actual=322_000_000)],
        budget_lines=_bta_lines(),
        trailing_12=[TrailingPoint(month="2026-06", revenue_cents=64_650_00, net_income_cents=6_070_00)],
    )


class TestBusinessPlanJson:
    def test_top_level_shape(self) -> None:
        js = eos.business_plan_to_json(_plan())
        assert set(js) == {
            "company", "fiscal_year", "period_label", "annual_goals", "budget_to_actual", "trailing_12",
        }

    def test_usd_goal_emits_dollars(self) -> None:
        js = eos.business_plan_to_json(_plan())
        goal = js["annual_goals"][0]
        assert goal["target"] == 7_000_000.0  # dollars from cents
        assert goal["actual"] == 3_220_000.0
        assert goal["attainment_pct"] == pytest.approx(46.0)
        assert goal["on_track"] is False

    def test_non_usd_goal_keeps_natural_unit(self) -> None:
        plan = BusinessPlan(
            company="c", fiscal_year=2026, period_label="x",
            annual_goals=[_goal(unit="percent", target=70, actual=23)],
            budget_lines=[], trailing_12=[],
        )
        goal = eos.business_plan_to_json(plan)["annual_goals"][0]
        assert goal["target"] == 70  # percent, NOT divided by 100
        assert goal["actual"] == 23

    def test_budget_line_shape(self) -> None:
        js = eos.business_plan_to_json(_plan())
        line = next(l for l in js["budget_to_actual"]["lines"] if l["key"] == "rev_a")
        assert set(line) == {"key", "label", "kind", "budget", "actual", "variance", "variance_pct", "favorable"}
        assert (line["budget"], line["actual"], line["variance"]) == (30_000.0, 32_000.0, 2_000.0)
        assert line["favorable"] is True

    def test_trailing_point_shape(self) -> None:
        js = eos.business_plan_to_json(_plan())
        point = js["trailing_12"]["points"][0]
        assert set(point) == {"month", "revenue", "net_income", "net_margin_pct"}
        assert point["revenue"] == 64_650.0


class TestIssuesJson:
    def test_shape_sorted_with_summary(self) -> None:
        issues = [_issue("a", priority=2), _issue("b", priority=1), _issue("c", status="closed", resolved="2026-06-10")]
        js = eos.issues_to_json(issues)
        assert set(js) == {"issues", "summary"}
        # b (open p1) first, a (open p2) next, c (closed) last.
        assert [i["id"] for i in js["issues"]] == ["b", "a", "c"]
        assert set(js["issues"][0]) == {
            "id", "title", "owner", "department", "priority", "status", "created", "resolved",
        }
        assert js["summary"]["open"] == 2


# --------------------------------------------------------------------------------------------
# 6. Canyon Ridge fixture — loads + anchors to the documented pains
# --------------------------------------------------------------------------------------------


class TestCanyonRidgeFixture:
    def test_issues_load(self) -> None:
        issues = ed.load_fixture_issues()
        assert len(issues) == 8
        # Every priority is valid; every status is open|closed.
        assert all(i.priority in eos.ISSUE_PRIORITIES for i in issues)
        assert all(i.status in eos.ISSUE_STATUSES for i in issues)
        # The headline pains are present and OPEN at top priority.
        by_id = {i.id: i for i in issues}
        assert by_id["iss-ar-aging"].priority == 1 and by_id["iss-ar-aging"].status == "open"
        assert by_id["iss-close-rate"].priority == 1
        # The resolved one carries a resolved date.
        assert by_id["iss-warranty-reg"].status == "closed"
        assert by_id["iss-warranty-reg"].resolved == "2026-06-06"

    def test_business_plan_loads_and_serializes(self) -> None:
        js = eos.business_plan_to_json(ed.load_fixture_business_plan())
        assert js["company"] == "Canyon Ridge Mechanical"
        assert len(js["annual_goals"]) == 5
        assert len(js["trailing_12"]["points"]) == 12

    def test_business_plan_net_income_derivation_anchor(self) -> None:
        # Revenue $646,500 - COGS $390,000 - Expense $151,800 = $104,700 actual net income.
        totals = eos.business_plan_to_json(ed.load_fixture_business_plan())["budget_to_actual"]["totals"]
        assert totals["revenue"]["actual"] == 646_500.0
        assert totals["cogs"]["actual"] == 390_000.0
        assert totals["expense"]["actual"] == 151_800.0
        assert totals["net_income"]["actual"] == 104_700.0
        assert totals["net_income"]["budget"] == 123_000.0
        assert totals["net_income"]["variance"] == -18_300.0
        assert totals["net_income"]["favorable"] is False  # under plan

    def test_trailing_12_blended_margin_anchor(self) -> None:
        totals = eos.business_plan_to_json(ed.load_fixture_business_plan())["trailing_12"]["totals"]
        # 12 months of revenue/net summed; blended margin ~8.46% on ~$6.55M revenue.
        assert totals["months"] == 12
        assert totals["revenue"] == pytest.approx(6_546_500.0)
        assert totals["net_income"] == pytest.approx(553_700.0)
        assert totals["net_margin_pct"] == pytest.approx(8.46, abs=0.01)

    def test_ar_goal_is_lower_is_better_and_off_track(self) -> None:
        goals = {g["key"]: g for g in eos.business_plan_to_json(ed.load_fixture_business_plan())["annual_goals"]}
        ar = goals["ar_over_90"]
        assert ar["higher_is_better"] is False
        # $412,000 actual vs a $50,000 target ceiling → off track (the >$400k pain).
        assert ar["actual"] == 412_000.0
        assert ar["on_track"] is False
