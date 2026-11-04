"""LLM token + cost telemetry for the narration layer (ADR-0003 safe — meters prose, not figures).

Two concerns live here, both deterministic and pure-testable:

1. PRICING — a model -> ($/MTok in, $/MTok out) table and `cost_usd(model, tokens_in, tokens_out)`.
   Prices are the public Anthropic list prices (USD per 1M tokens) as of 2026-06; an unknown model maps
   to the closest known family, else a conservative default so cost is never silently zero.

2. COLLECTION — a per-task contextvar the centralized LLM client writes `response.usage` into, and the
   orchestrating service reads after the graph runs to persist `tokens_in/tokens_out/cost_usd` on the
   run. A contextvar is used (not a return value) so the existing graph node signatures don't change:
   the `_reason` node and the service run in the SAME async task, so the collector the service resets
   before invoking the graph is exactly the one the client appended to.

Nothing here can affect a business number — it only counts tokens and multiplies by a price.
"""
from __future__ import annotations

import contextvars
from dataclasses import dataclass

# Public Anthropic list prices, USD per 1,000,000 tokens (input, output), 2026-06. Kept as a small
# table so a price change is a one-line edit. Prefix-matched (longest prefix wins) so dated model ids
# like `claude-sonnet-4-6-20260219` resolve without a table entry per snapshot.
_PRICE_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-opus-4": (15.0, 75.0),
    "claude-sonnet-4": (3.0, 15.0),
    "claude-haiku-4": (1.0, 5.0),
    "claude-3-5-sonnet": (3.0, 15.0),
    "claude-3-5-haiku": (0.80, 4.0),
    "claude-3-opus": (15.0, 75.0),
    "claude-3-haiku": (0.25, 1.25),
}
# Used when no prefix matches — Sonnet-tier, the platform's default reasoning model. Conservative
# (never zero) so an unrecognized model still records a non-trivial cost.
_DEFAULT_PRICE: tuple[float, float] = (3.0, 15.0)


def price_per_mtok(model: str) -> tuple[float, float]:
    """(input, output) USD per 1M tokens for `model`, by longest matching prefix, else the default."""
    best: tuple[float, float] | None = None
    best_len = -1
    m = (model or "").strip()
    for prefix, price in _PRICE_PER_MTOK.items():
        if m.startswith(prefix) and len(prefix) > best_len:
            best, best_len = price, len(prefix)
    return best if best is not None else _DEFAULT_PRICE


def cost_usd(model: str, tokens_in: int, tokens_out: int) -> float:
    """Dollar cost of a call, rounded to 6 dp (matches the numeric(12,6) column)."""
    pin, pout = price_per_mtok(model)
    total = (max(0, tokens_in) / 1_000_000) * pin + (max(0, tokens_out) / 1_000_000) * pout
    return round(total, 6)


@dataclass
class RunTelemetry:
    """Accumulated token usage + cost for one run (may span >1 model call, e.g. email polish)."""

    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    calls: int = 0

    def add(self, *, model: str, tokens_in: int, tokens_out: int) -> None:
        self.tokens_in += max(0, int(tokens_in))
        self.tokens_out += max(0, int(tokens_out))
        self.cost_usd = round(self.cost_usd + cost_usd(model, tokens_in, tokens_out), 6)
        self.calls += 1

    def as_run_fields(self) -> dict[str, float | int | None]:
        """The persistable fields, or all-None when no model call was made (template path)."""
        if self.calls == 0:
            return {"tokens_in": None, "tokens_out": None, "cost_usd": None}
        return {"tokens_in": self.tokens_in, "tokens_out": self.tokens_out, "cost_usd": self.cost_usd}


# Per-task collector. `None` means "not collecting" (e.g. a unit test calling explain() directly) —
# the client records only when a collector is active, so telemetry is opt-in per run and never leaks
# across requests (each service run resets it on its own task).
_collector: contextvars.ContextVar[RunTelemetry | None] = contextvars.ContextVar(
    "run_telemetry", default=None
)


def start_collection() -> RunTelemetry:
    """Begin collecting for the current task; returns the fresh collector the service later reads."""
    tel = RunTelemetry()
    _collector.set(tel)
    return tel


def record_usage(*, model: str, usage: object | None) -> None:
    """Add one model call's `response.usage` to the active collector (no-op if none / no usage).

    Tolerant of a missing/partial usage object so a telemetry hiccup never breaks narration."""
    tel = _collector.get()
    if tel is None or usage is None:
        return
    tin = getattr(usage, "input_tokens", 0) or 0
    tout = getattr(usage, "output_tokens", 0) or 0
    tel.add(model=model, tokens_in=int(tin), tokens_out=int(tout))


def current_collection() -> RunTelemetry | None:
    """The active collector, if any (the service reads this after the graph completes)."""
    return _collector.get()
