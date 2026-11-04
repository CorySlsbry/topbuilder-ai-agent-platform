"""Pure, deterministic math for the self-learning layer — no I/O, fully unit-testable.

These functions decide: how good was a recommendation (effectiveness), how different is a human
edit (edit_cost), how relevant is a past case now (retrieval_score = recency × effectiveness ×
relevance, after Generative Agents), whether two memories collide (near_duplicate), and whether a
learned preference has enough support to go active (is_active). All values are bounded and traceable.
"""
from __future__ import annotations

import math

# Feedback vocab normalization. The platform stores rating as up|down|edit; action outcomes add
# undone/rejected/executed. We collapse to: win / edit / loss.
_WIN = {"up", "approve", "approved", "accept", "accepted", "executed"}
_EDIT = {"edit", "edited"}
_LOSS = {"down", "reject", "rejected", "undo", "undone"}
# Undo/undone is the *strongest* negative — it reverses a decision a human had already approved.
_STRONG_LOSS = {"undo", "undone"}

# Retrieval weights (sum to 1.0): relevance dominates, then effectiveness, then recency.
W_RECENCY = 0.25
W_EFFECTIVENESS = 0.35
W_RELEVANCE = 0.40

DEFAULT_HALF_LIFE_DAYS = 45.0
DEFAULT_DEDUP_TAU = 0.92
DEFAULT_MIN_SUPPORT = 3


def _token_levenshtein(a: list[str], b: list[str]) -> int:
    """Classic edit distance over token lists (substitutions/insertions/deletions cost 1)."""
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ta in enumerate(a, start=1):
        cur = [i]
        for j, tb in enumerate(b, start=1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ta != tb)))
        prev = cur
    return prev[-1]


def edit_cost(original: str, edited: str) -> float:
    """Normalized token-level edit distance in [0, 1]. 0.0 = identical, 1.0 = nothing in common.

    This is the CIPHER signal: a small edit means the recommendation was nearly right (mild signal);
    a large edit means the human substantially rewrote it (strong signal worth learning a preference from).
    """
    a = original.split()
    b = edited.split()
    denom = max(len(a), len(b))
    if denom == 0:
        return 0.0
    return _token_levenshtein(a, b) / denom


def effectiveness(rating: str, *, edit_distance: float | None = None) -> float:
    """Outcome label → effectiveness in [0, 1]. Win=1.0, loss=0.0, edit=partial (capped at 0.5)."""
    r = (rating or "").strip().lower()
    if r in _WIN:
        return 1.0
    if r in _LOSS:
        return 0.0
    if r in _EDIT:
        # An edit is at best a half-win, decayed by how much was changed.
        return max(0.0, 0.5 - (edit_distance if edit_distance is not None else 0.5))
    return 0.0  # unknown/pending → treated as no positive signal


def is_strong_negative(rating: str) -> bool:
    """An undo (reversal of an approved action) is the strongest negative signal."""
    return (rating or "").strip().lower() in _STRONG_LOSS


def recency_decay(age_days: float, *, half_life_days: float = DEFAULT_HALF_LIFE_DAYS) -> float:
    """Exponential decay in (0, 1]. 1.0 at age 0, 0.5 at one half-life. Never below 0."""
    if age_days <= 0:
        return 1.0
    return math.exp(-math.log(2.0) * age_days / half_life_days)


def retrieval_score(
    *,
    similarity: float,
    effectiveness_value: float,
    age_days: float,
    half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
) -> float:
    """Generative-Agents-style relevance score in [0, 1]:
    W_RELEVANCE·similarity + W_EFFECTIVENESS·effectiveness + W_RECENCY·recency_decay(age).

    `similarity` is cosine in [-1, 1]; we clamp to [0, 1] (negatives are irrelevant).
    """
    sim = min(1.0, max(0.0, similarity))
    eff = min(1.0, max(0.0, effectiveness_value))
    rec = recency_decay(age_days, half_life_days=half_life_days)
    return round(W_RELEVANCE * sim + W_EFFECTIVENESS * eff + W_RECENCY * rec, 6)


def near_duplicate(similarity: float, *, tau: float = DEFAULT_DEDUP_TAU) -> bool:
    """True when a candidate is too close to an existing memory to be worth storing separately."""
    return similarity >= tau


def is_active(support_count: int, *, min_support: int = DEFAULT_MIN_SUPPORT) -> bool:
    """A learned preference only goes ACTIVE after >= min_support corroborating cases (noise guard:
    one loud edit can never change behavior; it stays quarantined until repeated)."""
    return support_count >= min_support
