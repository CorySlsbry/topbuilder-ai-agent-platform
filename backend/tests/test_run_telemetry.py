"""Pure tests for LLM token/cost telemetry (`app/agents/_telemetry.py`).

Covers the model->price table, the cost formula (hand-computed), and the per-task collector that the
centralized client writes `response.usage` into and the service reads back. No DB, no SDK, no network.
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.agents import _telemetry as tel


@dataclass
class _Usage:
    """Stand-in for an Anthropic `response.usage` (only the two fields we read)."""

    input_tokens: int
    output_tokens: int


class TestPricePerMtok:
    def test_known_sonnet_family_price(self) -> None:
        assert tel.price_per_mtok("claude-sonnet-4-6") == (3.0, 15.0)

    def test_longest_prefix_wins_over_shorter(self) -> None:
        # "claude-3-5-haiku" must win over a hypothetical shorter "claude-3" entry.
        assert tel.price_per_mtok("claude-3-5-haiku-20251022") == (0.80, 4.0)

    def test_dated_snapshot_id_resolves_by_prefix(self) -> None:
        assert tel.price_per_mtok("claude-opus-4-1-20260101") == (15.0, 75.0)

    def test_unknown_model_uses_conservative_default(self) -> None:
        assert tel.price_per_mtok("some-future-model") == tel._DEFAULT_PRICE


class TestCostUsd:
    def test_hand_computed_sonnet_cost(self) -> None:
        # 1,000,000 in @ $3/M + 500,000 out @ $15/M = $3.00 + $7.50 = $10.50.
        assert tel.cost_usd("claude-sonnet-4-6", 1_000_000, 500_000) == 10.5

    def test_small_call_rounds_to_six_dp(self) -> None:
        # 1,200 in @ $3/M + 800 out @ $15/M = 0.0036 + 0.012 = 0.0156.
        assert tel.cost_usd("claude-sonnet-4-6", 1_200, 800) == 0.0156

    def test_negative_token_counts_are_clamped_to_zero(self) -> None:
        assert tel.cost_usd("claude-sonnet-4-6", -5, -5) == 0.0


class TestRunTelemetry:
    def test_accumulates_across_calls_and_sums_cost(self) -> None:
        t = tel.RunTelemetry()
        t.add(model="claude-sonnet-4-6", tokens_in=1_200, tokens_out=800)
        t.add(model="claude-sonnet-4-6", tokens_in=2_000, tokens_out=1_000)
        assert t.tokens_in == 3_200
        assert t.tokens_out == 1_800
        assert t.calls == 2
        # 0.0156 (first) + (2000*3 + 1000*15)/1e6 = 0.0156 + 0.021 = 0.0366.
        assert t.cost_usd == 0.0366

    def test_no_call_persists_as_all_none(self) -> None:
        assert tel.RunTelemetry().as_run_fields() == {
            "tokens_in": None, "tokens_out": None, "cost_usd": None
        }

    def test_one_call_persists_the_figures(self) -> None:
        t = tel.RunTelemetry()
        t.add(model="claude-sonnet-4-6", tokens_in=1_200, tokens_out=800)
        assert t.as_run_fields() == {"tokens_in": 1_200, "tokens_out": 800, "cost_usd": 0.0156}


class TestCollector:
    def test_record_usage_no_op_without_active_collector(self) -> None:
        # Calling explain() outside a run (e.g. a unit test) records nothing and does not raise.
        tel._collector.set(None)
        tel.record_usage(model="claude-sonnet-4-6", usage=_Usage(10, 10))
        assert tel.current_collection() is None

    def test_start_collection_then_record_reads_back(self) -> None:
        collected = tel.start_collection()
        tel.record_usage(model="claude-sonnet-4-6", usage=_Usage(1_200, 800))
        assert collected is tel.current_collection()
        assert collected.as_run_fields() == {"tokens_in": 1_200, "tokens_out": 800, "cost_usd": 0.0156}

    def test_record_usage_tolerates_missing_usage(self) -> None:
        collected = tel.start_collection()
        tel.record_usage(model="claude-sonnet-4-6", usage=None)
        assert collected.calls == 0
        assert collected.as_run_fields()["cost_usd"] is None

    def test_start_collection_resets_between_runs(self) -> None:
        first = tel.start_collection()
        tel.record_usage(model="claude-sonnet-4-6", usage=_Usage(1_200, 800))
        assert first.calls == 1
        second = tel.start_collection()  # a new run starts fresh
        assert second is not first
        assert second.calls == 0
