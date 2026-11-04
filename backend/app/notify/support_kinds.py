"""The closed set of support-request kinds (shared by the DB CHECK, the repo, and the routes).

`ALL_KINDS` mirrors the migration 0028 CHECK exactly. `INTAKE_KINDS` is the subset a signed-in user
may POST to /v1/support/intake — 'signup' and 'chatbot' are captured by the system (membership backfill
and the assistant endpoint), never self-submitted, so they are excluded from the intake surface.
"""
from __future__ import annotations

ALL_KINDS: frozenset[str] = frozenset({"signup", "chatbot", "bug", "feature", "question"})
INTAKE_KINDS: frozenset[str] = frozenset({"bug", "feature", "question"})

# Human-readable label + a Slack emoji marker per kind. Kept here so the formatter, the digest, and
# any future UI all read one source of truth.
LABELS: dict[str, str] = {
    "signup": "New signup",
    "chatbot": "Assistant request",
    "bug": "Bug report",
    "feature": "Feature request",
    "question": "Question",
}
EMOJI: dict[str, str] = {
    "signup": "🎉",
    "chatbot": "💬",
    "bug": "🐞",
    "feature": "✨",
    "question": "❓",
}


def is_kind(kind: str) -> bool:
    return kind in ALL_KINDS


def is_intake_kind(kind: str) -> bool:
    return kind in INTAKE_KINDS


def label(kind: str) -> str:
    return LABELS.get(kind, kind.capitalize())
