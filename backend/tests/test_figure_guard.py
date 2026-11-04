"""Pure oracle tests for the figure-faithfulness verifier (`app/agents/_figure_guard.py`).

The verifier is the runtime guard on the ADR-0003 firewall: the LLM narrates, and this check proves
the narration neither dropped an authoritative figure nor invented a new dollar amount. These tests
are hand-computed (no call's output is used as its own oracle) and exercise normalization, coverage,
no-invention, and the guard/fallback decision.
"""
from __future__ import annotations

import pytest

from app.agents import _figure_guard as fg


class TestNormalizeAmount:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("$1,234", "1234"),
            ("$1234", "1234"),
            ("$1,200.00", "1200"),
            ("$1,200.50", "1200.5"),
            ("$0", "0"),
            ("$0.00", "0"),
            ("-$200", "-200"),
            ("$-200", "-200"),
            ("$ 3,260", "3260"),
            ("-$0", "0"),  # negative zero folds to plain zero
        ],
    )
    def test_canonicalizes_equal_values_equally(self, raw: str, expected: str) -> None:
        assert fg.normalize_amount(raw) == expected

    def test_thousands_grouping_does_not_matter(self) -> None:
        assert fg.normalize_amount("$1,234,567") == fg.normalize_amount("$1234567") == "1234567"


class TestExtractDollarAmounts:
    def test_extracts_all_distinct_amounts_in_order(self) -> None:
        text = "Cash moves from $120,000 to $98,500 (30d); leakage ~$3,260 and again $3,260."
        assert fg.extract_dollar_amounts(text) == ["120000", "98500", "3260"]

    def test_no_dollar_amounts_returns_empty(self) -> None:
        assert fg.extract_dollar_amounts("12 jobs, 3 techs, 95% utilization.") == []

    def test_handles_none_and_empty(self) -> None:
        assert fg.extract_dollar_amounts("") == []
        assert fg.extract_dollar_amounts(None) == []  # type: ignore[arg-type]


class TestAllowedAmountsFromBrief:
    def test_collects_numeric_usd_fields_and_embedded_amounts(self) -> None:
        # Mirrors the shape each agent's `_analysis_brief` produces: *_usd floats + nested lists.
        brief = {
            "starting_cash": 120000,
            "totals": {"recovered_revenue_usd": 3260.0, "after_hours_recovered_usd": 2895.0},
            "leakage": [{"job": "A", "exposure_usd": 1500.0}],
            "note": "covers $2,895 of after-hours.",
        }
        allowed = fg.allowed_amounts_from_brief(brief)
        # Every authoritative figure is present, normalized; booleans/strings don't break it.
        assert {"120000", "3260", "2895", "1500"} <= allowed

    def test_booleans_are_not_treated_as_amounts(self) -> None:
        allowed = fg.allowed_amounts_from_brief({"after_hours": True, "value_usd": 0.0})
        # True must not collapse into the "1" amount; only the real 0.0 figure is allowed.
        assert "1" not in allowed
        assert "0" in allowed


class TestVerifyNarrative:
    def test_passes_when_every_required_figure_present_and_none_invented(self) -> None:
        allowed = {"120000", "98500", "3260"}
        narrative = "Cash goes from $120,000 to $98,500; ~$3,260 leakage flagged."
        ok, drift = fg.verify_narrative(narrative, allowed=allowed)
        assert ok is True
        assert drift == {"invented": [], "missing": []}

    def test_flags_an_invented_amount(self) -> None:
        allowed = {"120000", "98500"}
        # $5,000 was never authorized by the engine — a hallucinated figure.
        narrative = "Cash goes from $120,000 to $98,500, with a $5,000 bonus opportunity."
        ok, drift = fg.verify_narrative(narrative, allowed=allowed)
        assert ok is False
        assert drift["invented"] == ["5000"]
        assert drift["missing"] == []

    def test_flags_a_dropped_required_figure(self) -> None:
        allowed = {"120000", "98500", "3260"}
        # The model omitted the $3,260 leakage figure it was required to quote.
        narrative = "Cash goes from $120,000 to $98,500."
        ok, drift = fg.verify_narrative(narrative, allowed=allowed, required={"3260"})
        assert ok is False
        assert drift["missing"] == ["3260"]
        assert drift["invented"] == []

    def test_required_defaults_to_allowed(self) -> None:
        # With no explicit `required`, every allowed amount must appear.
        ok, drift = fg.verify_narrative("only $100 here", allowed={"100", "200"})
        assert ok is False
        assert drift["missing"] == ["200"]

    def test_grouping_difference_between_brief_and_prose_still_matches(self) -> None:
        # Engine authorized 3260 (from a 3260.0 float); prose writes "$3,260" — normalization bridges.
        ok, _ = fg.verify_narrative("recovered ~$3,260", allowed={"3260"}, required={"3260"})
        assert ok is True


class TestGuardOrFallback:
    def _brief(self) -> dict:
        return {"starting_cash": 120000, "totals": {"recovered_usd": 3260.0}}

    def test_returns_model_text_when_faithful(self) -> None:
        brief = self._brief()
        good = "From $120,000, we recovered $3,260."
        template = "TEMPLATE: $120,000 / $3,260"
        shipped, drift = fg.guard_or_fallback(narrative=good, template=template, brief=brief)
        assert shipped == good
        assert drift is None

    def test_falls_back_to_template_on_invented_figure(self) -> None:
        brief = self._brief()
        bad = "From $120,000 we recovered $3,260 plus a $9,999 windfall."
        template = "TEMPLATE: $120,000 / $3,260"
        shipped, drift = fg.guard_or_fallback(narrative=bad, template=template, brief=brief)
        assert shipped == template
        assert drift is not None
        assert drift["invented"] == ["9999"]

    def test_required_defaults_to_template_amounts_so_terse_model_summary_is_allowed(self) -> None:
        # The model legitimately omits $3,260 — and so does the template — so omission is NOT drift;
        # only inventing a NEW amount would be. The template prints only $120,000 here.
        brief = self._brief()
        template = "Cash is $120,000 today."
        model = "Cash stands at $120,000."  # faithful, no invented amount, template's figure kept
        shipped, drift = fg.guard_or_fallback(narrative=model, template=template, brief=brief)
        assert shipped == model
        assert drift is None


class TestFigureGuardRegressions:
    """Regressions for the code-review findings: P0 (cents rounding) and P1 (count collision)."""

    def test_counts_and_percentages_are_not_authorized_as_dollars(self) -> None:
        # P1: only genuinely monetary keys widen the allowed set; counts/percentages stay out.
        brief = {"days_overdue": 45, "customers": 12, "pct_current": 85.0, "recovered_usd": 1000.0}
        assert fg.allowed_amounts_from_brief(brief) == {"1000"}

    def test_cents_key_read_as_dollars_and_rounded_forms_present(self) -> None:
        # P0: a `*_cents` value is read as dollars; a cents-bearing dollar value allows both its raw and
        # its whole-dollar display form.
        allowed = fg.allowed_amounts_from_brief({"balance_usd": 98500.75, "late_fee_cents": 4500})
        assert {"98501", "98500.75", "45"} <= allowed

    def test_cents_bearing_brief_does_not_false_reject_whole_dollar_prose(self) -> None:
        # P0 (the deploy blocker): a brief float with cents must allow the prose's rounded whole dollars
        # (the narratives render money with :,.0f), so the LLM narration is NOT silently discarded.
        brief = {"starting_cash_usd": 98500.75, "cash_flow": [{"projected_cash_usd": 87234.40}]}
        narrative = "Cash moves from $98,501 to $87,234."
        template = "TEMPLATE: $98,501 / $87,234"
        shipped, drift = fg.guard_or_fallback(narrative=narrative, template=template, brief=brief)
        assert shipped == narrative
        assert drift is None

    def test_invented_fee_colliding_with_a_count_is_still_caught(self) -> None:
        # P1: a hallucinated "$45 late fee" must NOT be laundered by a non-monetary `days_overdue=45`.
        brief = {"days_overdue": 45, "recovered_usd": 1000.0}
        narrative = "We recovered $1,000, and a $45 late fee applies."
        template = "TEMPLATE: $1,000"
        shipped, drift = fg.guard_or_fallback(narrative=narrative, template=template, brief=brief)
        assert shipped == template
        assert drift is not None
        assert drift["invented"] == ["45"]
