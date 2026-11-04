"""Deterministic confidence scoring for workforce recommendations.

Confidence is a function of (a) how far out the forecast is and (b) how much historical data backs
it — never the LLM's self-reported certainty (ADR 0003). All outputs are in [0, 1], rounded to 3
decimals to match the `numeric(4,3)` storage column.
"""
from __future__ import annotations

# Each week into the future costs this much confidence...
HORIZON_DECAY_PER_WEEK = 0.08
# ...but never below this floor (even distant forecasts carry signal).
MIN_HORIZON_DECAY = 0.5
# Historical job-duration samples needed before the "data support" half saturates.
SAMPLE_SATURATION = 500
# Overtime is computed from an already-assigned schedule, so its base certainty is high.
OVERTIME_ASSIGNMENT_CERTAINTY = 0.9


def horizon_decay(week_offset: int) -> float:
    """1.0 this week, decaying linearly with the forecast horizon down to a floor."""
    return max(MIN_HORIZON_DECAY, 1.0 - HORIZON_DECAY_PER_WEEK * week_offset)


def data_support(total_sample_size: int, mean_completion_rate: float) -> float:
    """Blend sample volume (saturating) with historical completion reliability."""
    sample_factor = min(1.0, total_sample_size / SAMPLE_SATURATION)
    return 0.5 * sample_factor + 0.5 * mean_completion_rate


def understaffing_confidence(
    week_offset: int, total_sample_size: int, mean_completion_rate: float
) -> float:
    return round(horizon_decay(week_offset) * data_support(total_sample_size, mean_completion_rate), 3)


def overtime_confidence(week_offset: int) -> float:
    return round(horizon_decay(week_offset) * OVERTIME_ASSIGNMENT_CERTAINTY, 3)
