"""Figure-faithfulness verifier — the runtime guard on the ADR-0003 firewall.

ADR 0003: the deterministic engine OWNS every business number; the LLM only NARRATES. This module is
the cheap, pure check that the narration honored that contract on the way out — it never computes a
figure, it only compares strings.

Two assertions, both string-level (no math):
  1. COVERAGE   — every authoritative dollar figure the engine handed the model appears verbatim in
                  the narrative (the model didn't silently drop a number).
  2. NO-INVENTION — no `$`-amount appears in the narrative that is NOT in the authoritative set (the
                  model didn't hallucinate a new dollar figure).

On any failure the caller falls back to the deterministic template renderer and logs a structured
`narration_figure_drift` event — so a drifting model degrades to provably-correct prose, never ships a
wrong number. Authoritative figures are pulled from the same `_analysis_brief(...)` dict each agent
already builds for the model, so the allowed set is exactly what the model was told to quote.

Everything here is deterministic and unit-tested (`tests/test_figure_guard.py`); no I/O, no SDK.
"""
from __future__ import annotations

import re
from typing import Any

# A US dollar amount as it renders in our narratives/briefs: `$1,234`, `$1,234.50`, `$-200`, `$0`.
# We normalize away the thousands separators + an optional sign before comparing, so `$1,234` in the
# brief matches `$1,234` in the prose regardless of how either side grouped digits.
_DOLLAR_RE = re.compile(r"-?\$\s?-?[0-9][0-9,]*(?:\.[0-9]+)?")


def normalize_amount(token: str) -> str:
    """Canonicalize a `$`-amount to `<sign><digits>[.<digits>]` so equal values compare equal.

    Drops the `$`, whitespace, and thousands commas; folds a leading `-$` / `$-` to one sign; strips a
    trailing `.00`/`.0` and a `.50`→`.5` so `$1,200.00` and `$1200` and `$1,200` all canonicalize the
    same. Purely lexical — never parses to a float for comparison, so there is no rounding.
    """
    t = token.strip()
    negative = t.count("-") % 2 == 1
    t = t.replace("$", "").replace(",", "").replace(" ", "").replace("-", "")
    if "." in t:
        whole, frac = t.split(".", 1)
        frac = frac.rstrip("0")
        t = whole if not frac else f"{whole}.{frac}"
    t = t or "0"
    return f"-{t}" if (negative and t != "0") else t


def extract_dollar_amounts(text: str) -> list[str]:
    """Every `$`-amount in `text`, normalized (see `normalize_amount`). Order-preserving, de-duped."""
    seen: dict[str, None] = {}
    for m in _DOLLAR_RE.findall(text or ""):
        seen.setdefault(normalize_amount(m), None)
    return list(seen)


def _walk_strings_and_numbers(value: Any):
    """Yield every scalar (str/int/float/bool) reachable in a nested dict/list brief."""
    if isinstance(value, dict):
        for v in value.values():
            yield from _walk_strings_and_numbers(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _walk_strings_and_numbers(v)
    else:
        yield value


# Which numeric scalars in a brief are authoritative USD figures the model may quote. Money lives under
# `*_usd` / `*_cents` keys (the convention every agent's _analysis_brief follows) or a money-named key.
# Counts, percentages, day-counts, confidences and ids are NOT money and must stay OUT of the allowed
# set — otherwise a hallucinated small figure that collides with one (a "$45 late fee" vs
# `days_overdue=45`) would launder straight through the no-invention check.
_MONEY_WORDS = (
    "cost", "revenue", "cash", "price", "amount", "fee", "dollar", "margin", "ticket", "leak",
    "recovered", "savings", "balance", "payroll", "wage", "total", "value", "carry", "spend",
)


def _is_money_key(key: str) -> bool:
    k = key.lower()
    return k.endswith("_usd") or k.endswith("_cents") or "usd" in k or any(w in k for w in _MONEY_WORDS)


def _monetary_forms(dollars: float) -> set[str]:
    """Every way one dollar value legitimately renders in our briefs/prose, so display rounding is OK.

    The narratives format money as `:,.0f` (whole dollars) or `:,.2f` (cents); a brief float of
    `98500.75` must therefore allow the prose's `$98,501`. We add the raw, the whole-dollar, and the
    two-decimal canonical forms. Purely lexical via `normalize_amount` — no float-equality anywhere.
    """
    return {
        normalize_amount(f"${dollars}"),
        normalize_amount(f"${dollars:,.0f}"),
        normalize_amount(f"${dollars:,.2f}"),
    }


def allowed_amounts_from_brief(brief: Any) -> set[str]:
    """The authoritative set of dollar amounts the model was allowed to quote, from the analysis brief.

    A numeric scalar is treated as money only when its key is monetary (`*_usd`, `*_cents`, or a
    money-named key — see `_is_money_key`); `*_cents` values are divided by 100. Each money value is
    expanded to its display forms (`_monetary_forms`) so the prose's rounded `$98,501` matches a brief
    float of `98500.75`. Any `$`-amount embedded in a string scalar is always authoritative. Counts and
    percentages are deliberately excluded so they cannot launder a hallucinated dollar figure.
    """
    allowed: set[str] = set()

    def walk(node: Any, *, cents: bool, money: bool) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                key = str(k).lower()
                walk(v, cents=key.endswith("_cents"), money=_is_money_key(key))
        elif isinstance(node, (list, tuple)):
            for v in node:
                walk(v, cents=cents, money=money)
        elif isinstance(node, bool):
            return
        elif isinstance(node, (int, float)):
            if money:
                allowed.update(_monetary_forms(node / 100.0 if cents else float(node)))
        elif isinstance(node, str):
            for tok in extract_dollar_amounts(node):
                allowed.add(tok)

    walk(brief, cents=False, money=False)
    return allowed


def verify_narrative(
    narrative: str, *, allowed: set[str], required: set[str] | None = None
) -> tuple[bool, dict[str, list[str]]]:
    """Check a narrative against the authoritative figure set. Returns `(ok, drift)`.

    `allowed`  — every dollar amount the engine authorized (typically `allowed_amounts_from_brief`).
    `required` — the subset that MUST appear verbatim (defaults to `allowed`); pass a narrower set when
                 the template legitimately omits some figures (e.g. a zero-state summary).

    `drift` has two keys:
      * `invented` — `$`-amounts in the narrative that are not in `allowed` (hallucinated figures).
      * `missing`  — `required` amounts absent from the narrative (dropped figures).
    `ok` is True iff both lists are empty. The check is lexical and side-effect free.
    """
    required = allowed if required is None else required
    present = set(extract_dollar_amounts(narrative))
    invented = sorted(present - allowed)
    missing = sorted(required - present)
    return (not invented and not missing), {"invented": invented, "missing": missing}


def guard_or_fallback(
    *, narrative: str, template: str, brief: Any, required: set[str] | None = None
) -> tuple[str, dict[str, list[str]] | None]:
    """Return the LLM `narrative` if it is figure-faithful, else the deterministic `template`.

    The single call site each `explain()` uses: it builds the allowed set from `brief`, verifies the
    model's `narrative`, and on drift swaps in `template` (which is figure-correct by construction).
    Returns `(text_to_ship, drift_or_None)` — a non-None drift is what the caller logs as the structured
    `narration_figure_drift` event. The template is NEVER itself re-verified (it cannot drift), so this
    can only ever make output safer.

    `required` defaults to the amounts the `template` itself prints, so the model is only ever rejected
    for INVENTING a dollar amount or DROPPING one the deterministic narrative also surfaces — a more
    terse (but faithful) model summary is allowed. Pass an explicit set to force specific figures.
    """
    allowed = allowed_amounts_from_brief(brief)
    if required is None:
        required = set(extract_dollar_amounts(template))
    ok, drift = verify_narrative(narrative, allowed=allowed, required=required)
    if ok:
        return narrative, None
    return template, drift
