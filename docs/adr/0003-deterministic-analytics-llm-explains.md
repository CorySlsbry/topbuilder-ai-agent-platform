# ADR 0003 — Deterministic analytics; the LLM explains, never computes

- **Status:** Accepted
- **Date:** 2026-06-02

## Context

The agents make claims about money and staffing: "you'll be 38 technician-hours short on June 14,
costing ~$5,700," or (for the financial agent) GAAP-aligned cash-flow projections with "zero
tolerance for calculation drift." Large language models are not reliable arithmetic engines; their
numeric output is non-deterministic and occasionally wrong in ways that are hard to detect. Putting
an LLM on the critical path for a dollar figure is a correctness and liability risk.

## Decision

Split every agent into two strictly separated layers:

1. **Deterministic compute layer** — pure Python (+ SQL) functions that take structured inputs and
   produce every number: gaps, hours, costs, thresholds, confidence scores. No model calls. Fully
   unit-tested and property-tested (invariants: non-negativity, monotonicity, additive
   decomposition, etc.).
2. **Reasoning / narration layer** — the LLM receives the *already-computed* results plus the data
   references and produces the human-readable explanation, mitigation prose, and prioritization. It
   is explicitly instructed that the numbers are authoritative and must be quoted, not recomputed.

When `DISABLE_LLM=1` (or no API key is present), a deterministic template renders the narrative, so
the entire pipeline runs and is testable without any model call.

## Consequences

- Numbers are reproducible and auditable; the same inputs always yield the same figures and the same
  confidence scores.
- The model adds language and judgment on top of trustworthy math — its best use.
- Confidence scores are a deterministic function of data support and forecast horizon, not an LLM's
  self-reported certainty.
- This pattern is reused by the (future) Inventory and Financial agents; the financial calc engine
  will encode GAAP rules as tested code.
