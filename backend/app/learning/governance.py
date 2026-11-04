"""Pure governance math for the self-learning eval-gate, canary, drift, and tuning (Phase C/D).

No I/O — every function here is deterministic and unit-tested. The eval gate exists so a learned
RULE only becomes active when it (a) is structurally safe and (b) does not break the ADR-0003
invariant (every authoritative figure still appears) on the golden set. Governance tunes THRESHOLDS,
never a figure.
"""
from __future__ import annotations

import hashlib
import re

# A learned narration rule must never tell the model to alter/omit a figure or inject unsafe content.
# These red flags keep a distilled human edit (or a nightly-proposed rule) from quietly corrupting
# output. This is the always-on, offline gate (the golden-set narration eval is the richer online one).
_RED_FLAGS: tuple[str, ...] = (
    # figure tampering
    r"\bignore\b", r"\bomit\b", r"\bskip\b", r"\bround (up|down|the)\b", r"\bmake up\b",
    r"\bfabricat", r"\binflat", r"\bexaggerat", r"\bhide\b", r"\bdon'?t mention\b",
    r"\bchange the (number|figure|total|amount|cash|margin)", r"\boverrid", r"\bdisregard\b",
    r"\bdelete\b", r"\bdrop the\b",
    # SEC-3: financial-instruction / social-engineering injection (a narration STYLE rule has no
    # business telling the operator to move money, change payment details, or bypass controls)
    r"\bwir(e|ing)\b", r"\bbank (details|account|routing)", r"\brouting number\b",
    r"\baccount number\b", r"\bgift card", r"\bcrypto", r"\bbitcoin\b", r"\bsend (money|payment|funds)",
    r"\bpay(ment)? to\b", r"\bnew (bank|payment|wire) (details|instructions)",
    r"\bupdated (bank|payment|wire) (details|instructions)", r"\bclick (here|this link)\b",
    r"\bhttps?://", r"\bpassword\b", r"\bapi[- ]?key\b", r"\bcredential", r"\bssn\b",
    r"\bbypass\b", r"\bapprov\w* (without|automatically)\b", r"\bautomatically\b",
    r"\bwithout review\b", r"\bwithout approval\b",
)
_MIN_LEN = 8
_MAX_LEN = 600


def rule_safety_check(text: str) -> tuple[bool, list[str]]:
    """Deterministic guardrail every candidate rule must pass before any eval. Returns (ok, reasons)."""
    reasons: list[str] = []
    t = (text or "").strip()
    if len(t) < _MIN_LEN:
        reasons.append("too_short")
    if len(t) > _MAX_LEN:
        reasons.append("too_long")
    low = t.lower()
    for pat in _RED_FLAGS:
        if re.search(pat, low):
            reasons.append(f"red_flag:{pat}")
    return (len(reasons) == 0, reasons)


def golden_match(narrative: str, must_include, must_avoid) -> tuple[bool, list[str]]:
    """A golden case passes iff every must_include token is present and no must_avoid phrase is."""
    nlow = (narrative or "").lower()
    fails: list[str] = []
    for tok in must_include or []:
        if tok and tok.lower() not in nlow:
            fails.append(f"missing:{tok}")
    for bad in must_avoid or []:
        if bad and bad.lower() in nlow:
            fails.append(f"present:{bad}")
    return (len(fails) == 0, fails)


def eval_score(passed: int, total: int) -> float:
    """Fraction of golden cases passed. With no golden set, returns 1.0 (safety_check alone decides)."""
    if total <= 0:
        return 1.0
    return round(passed / total, 6)


def eval_verdict(
    *, safety_ok: bool, invariant_ok: bool, score: float, min_score: float = 1.0,
    evaluatable: bool = True,
) -> str:
    """'pass' only if the rule is safe, the figure-invariant held, it cleared the golden bar, AND the
    eval could actually exercise the rule. SEC-3: when the gate cannot test the rule's effect (offline
    / no LLM, where the golden narration is the situation verbatim), `evaluatable=False` forces a
    fail so a candidate can NEVER auto-activate without a real evaluation or a human approval."""
    if not evaluatable:
        return "fail"
    return "pass" if (safety_ok and invariant_ok and score >= min_score) else "fail"


def in_canary(rule_id: str, tenant_id: str, rollout_pct: int) -> bool:
    """Deterministic canary gate: a stable hash of (rule, tenant) under the rollout %. 100 => always."""
    if rollout_pct >= 100:
        return True
    if rollout_pct <= 0:
        return False
    # Non-cryptographic: a stable bucketing hash for canary rollout, not a security control.
    digest = hashlib.md5(f"{rule_id}:{tenant_id}".encode(), usedforsecurity=False).hexdigest()
    bucket = int(digest, 16) % 100
    return bucket < rollout_pct


def drift_flag(
    *, edit_rate: float, reject_rate: float, avg_effectiveness: float,
    edit_max: float = 0.5, reject_max: float = 0.3, eff_min: float = 0.4
) -> bool:
    """Flag an agent whose recent human signal is degrading (too many edits/rejects, low effectiveness)."""
    return (edit_rate > edit_max) or (reject_rate > reject_max) or (avg_effectiveness < eff_min)


def bandit_update(current: float, *, reward: float, lr: float = 0.2, lo: float, hi: float) -> float:
    """Nudge a THRESHOLD toward higher reward, clamped to [lo, hi].

    reward in [-1, 1]: positive raises the knob, negative lowers it; magnitude scales the step. This
    tunes governance knobs (e.g. the edit-distance threshold or quorum), never a figure (ADR 0003)."""
    span = hi - lo
    step = lr * max(-1.0, min(1.0, reward)) * span * 0.1
    return round(min(hi, max(lo, current + step)), 6)
