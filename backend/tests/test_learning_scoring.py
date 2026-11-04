"""Unit tests for the pure self-learning math — hand-computed oracles (no I/O, no infra)."""
from __future__ import annotations

import math

from app.learning import scoring


# --- edit_cost: normalized token Levenshtein -------------------------------------------------
def test_edit_cost_identical_is_zero():
    assert scoring.edit_cost("book the job thursday", "book the job thursday") == 0.0


def test_edit_cost_one_token_of_four_is_quarter():
    # one substitution (thursday->friday) over 4 tokens = 1/4
    assert scoring.edit_cost("book the job thursday", "book the job friday") == 0.25


def test_edit_cost_completely_different_is_one():
    assert scoring.edit_cost("alpha beta", "gamma delta") == 1.0


def test_edit_cost_empty_original_against_four_tokens_is_one():
    assert scoring.edit_cost("", "two new tokens here") == 1.0  # 4 inserts / 4


def test_edit_cost_both_empty_is_zero():
    assert scoring.edit_cost("", "") == 0.0


# --- effectiveness: outcome label -> [0,1] ---------------------------------------------------
def test_effectiveness_win_is_full():
    assert scoring.effectiveness("up") == 1.0
    assert scoring.effectiveness("approved") == 1.0


def test_effectiveness_loss_is_zero():
    assert scoring.effectiveness("down") == 0.0
    assert scoring.effectiveness("undone") == 0.0


def test_effectiveness_small_edit_is_partial():
    # edit cost 0.25 -> max(0, 0.5 - 0.25)
    assert scoring.effectiveness("edit", edit_distance=0.25) == 0.25


def test_effectiveness_large_edit_floors_at_zero():
    assert scoring.effectiveness("edit", edit_distance=0.70) == 0.0


def test_undo_is_strongest_negative():
    assert scoring.is_strong_negative("undone") is True
    assert scoring.is_strong_negative("down") is False


# --- recency decay ---------------------------------------------------------------------------
def test_recency_decay_anchors():
    assert scoring.recency_decay(0.0) == 1.0
    assert math.isclose(scoring.recency_decay(45.0, half_life_days=45.0), 0.5, rel_tol=1e-9)


def test_recency_decay_is_monotonic_decreasing_and_bounded():
    scores = [scoring.recency_decay(a) for a in (0, 10, 30, 60, 120, 365)]
    assert scores == sorted(scores, reverse=True)
    assert all(0.0 < s <= 1.0 for s in scores)


# --- retrieval score (relevance x effectiveness x recency) -----------------------------------
def test_retrieval_score_perfect_case_is_one():
    # 0.40*1 + 0.35*1 + 0.25*recency(0)=1 -> 1.0
    assert scoring.retrieval_score(similarity=1.0, effectiveness_value=1.0, age_days=0.0) == 1.0


def test_retrieval_score_clamps_negative_similarity_and_old_age_to_near_zero():
    assert scoring.retrieval_score(similarity=-0.5, effectiveness_value=0.0, age_days=1e9) == 0.0


def test_winning_case_outranks_losing_case_at_equal_similarity_and_age():
    win = scoring.retrieval_score(similarity=0.8, effectiveness_value=1.0, age_days=10.0)
    loss = scoring.retrieval_score(similarity=0.8, effectiveness_value=0.0, age_days=10.0)
    assert win > loss


# --- guardrail gates -------------------------------------------------------------------------
def test_near_duplicate_threshold():
    assert scoring.near_duplicate(0.95) is True
    assert scoring.near_duplicate(0.90) is False


def test_preference_activates_only_after_quorum():
    assert scoring.is_active(3) is True   # default min_support = 3
    assert scoring.is_active(2) is False
