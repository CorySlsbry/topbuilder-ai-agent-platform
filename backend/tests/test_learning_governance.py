"""Hand-computed oracles for the pure governance math (Phase C/D eval-gate, canary, drift, tuning).

Imports only app.learning.governance + stdlib, so it runs in the offline (no-DB) suite.
"""
from __future__ import annotations

from app.learning import governance as g


class TestRuleSafetyCheck:
    def test_clean_rule_passes(self) -> None:
        ok, reasons = g.rule_safety_check(
            "Always lead with the dollar exposure, then name the single highest-impact action."
        )
        assert (ok, reasons) == (True, [])

    def test_too_short(self) -> None:
        assert g.rule_safety_check("ok") == (False, ["too_short"])

    def test_too_long(self) -> None:
        ok, reasons = g.rule_safety_check("x" * 601)
        assert ok is False and "too_long" in reasons

    def test_red_flag_ignore_numbers(self) -> None:
        ok, reasons = g.rule_safety_check("Ignore the small line items when summarizing.")
        assert ok is False and any(r.startswith("red_flag") for r in reasons)

    def test_red_flag_round(self) -> None:
        ok, _ = g.rule_safety_check("Round up the totals to look cleaner.")
        assert ok is False


class TestGoldenMatch:
    def test_all_includes_present_no_avoids(self) -> None:
        assert g.golden_match("Cash moves to $50,000 by 30d.", ["$50,000"], []) == (True, [])

    def test_missing_include(self) -> None:
        ok, fails = g.golden_match("Cash is healthy.", ["$50,000"], [])
        assert ok is False and fails == ["missing:$50,000"]

    def test_avoid_present(self) -> None:
        ok, fails = g.golden_match("We rounded the figures.", [], ["rounded"])
        assert ok is False and fails == ["present:rounded"]


class TestEvalScoreVerdict:
    def test_score_fraction(self) -> None:
        assert g.eval_score(3, 4) == 0.75

    def test_score_empty_is_one(self) -> None:
        assert g.eval_score(0, 0) == 1.0

    def test_score_zero(self) -> None:
        assert g.eval_score(0, 3) == 0.0

    def test_verdict_pass(self) -> None:
        assert g.eval_verdict(safety_ok=True, invariant_ok=True, score=1.0) == "pass"

    def test_verdict_fail_on_regression(self) -> None:
        assert g.eval_verdict(safety_ok=True, invariant_ok=True, score=0.75) == "fail"

    def test_verdict_fail_on_unsafe(self) -> None:
        assert g.eval_verdict(safety_ok=False, invariant_ok=True, score=1.0) == "fail"

    def test_verdict_fail_on_invariant(self) -> None:
        assert g.eval_verdict(safety_ok=True, invariant_ok=False, score=1.0) == "fail"


class TestCanary:
    def test_full_rollout_always_in(self) -> None:
        assert g.in_canary("rule-1", "tenant-1", 100) is True

    def test_zero_rollout_never_in(self) -> None:
        assert g.in_canary("rule-1", "tenant-1", 0) is False

    def test_deterministic(self) -> None:
        a = g.in_canary("rule-9", "tenant-3", 40)
        b = g.in_canary("rule-9", "tenant-3", 40)
        assert a == b

    def test_distribution_matches_pct(self) -> None:
        # ~30% of distinct rules should fall inside a 30% rollout for a fixed tenant.
        n = 2000
        inside = sum(1 for i in range(n) if g.in_canary(f"rule-{i}", "tenant-x", 30))
        assert 0.24 <= inside / n <= 0.36

    def test_monotonic_in_pct(self) -> None:
        # If a rule is in the canary at pct P, it is in the canary at every larger pct.
        rid, tid = "rule-42", "tenant-7"
        on = next(p for p in range(0, 101) if g.in_canary(rid, tid, p))
        assert all(g.in_canary(rid, tid, p) for p in range(on, 101))
        assert all(not g.in_canary(rid, tid, p) for p in range(0, on))


class TestDriftFlag:
    def test_healthy_not_flagged(self) -> None:
        assert g.drift_flag(edit_rate=0.2, reject_rate=0.1, avg_effectiveness=0.8) is False

    def test_high_edit_rate_flagged(self) -> None:
        assert g.drift_flag(edit_rate=0.6, reject_rate=0.1, avg_effectiveness=0.8) is True

    def test_low_effectiveness_flagged(self) -> None:
        assert g.drift_flag(edit_rate=0.2, reject_rate=0.1, avg_effectiveness=0.3) is True


class TestBanditUpdate:
    def test_positive_reward_raises(self) -> None:
        # span=0.4, step=0.2*1.0*0.4*0.1=0.008 -> 0.25+0.008
        assert g.bandit_update(0.25, reward=1.0, lr=0.2, lo=0.1, hi=0.5) == 0.258

    def test_negative_reward_lowers(self) -> None:
        assert g.bandit_update(0.25, reward=-1.0, lr=0.2, lo=0.1, hi=0.5) == 0.242

    def test_clamped_to_hi(self) -> None:
        assert g.bandit_update(0.5, reward=1.0, lr=0.2, lo=0.1, hi=0.5) == 0.5

    def test_clamped_to_lo(self) -> None:
        assert g.bandit_update(0.1, reward=-1.0, lr=0.2, lo=0.1, hi=0.5) == 0.1
