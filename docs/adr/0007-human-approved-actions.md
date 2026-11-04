# ADR 0007 — Human-approved action execution (the gated write path)

- **Status:** Accepted
- **Date:** 2026-06-04
- **Related:** [0003](0003-deterministic-analytics-llm-explains.md), [0005](0005-servicetitan-adapter-pattern.md),
  [0006](0006-booking-agent.md)

## Context

The agents are **advisory / read-only on the systems of record** (ServiceTitan, QuickBooks): they read
data, compute deterministic recommendations, and persist them — they never silently mutate the customer's
systems. That is a deliberate trust posture for a $10–50k tool wired into a contractor's live ServiceTitan.

But the product promise ("books appointments, performs tasks") requires *some* writes — booking a slot,
pushing a categorization. The question isn't read-only vs. read-write; it's **how a write happens safely.**
Three surfaces, three answers: (1) read & analyze → always read-only; (2) produce artifacts (exports,
spreadsheets, drafts, narratives) → outputs, not write-backs, always allowed; (3) **write to a system of
record → this ADR.**

## Decision

Writes to a system of record go through an explicit **propose → approve → execute** gate, off by default.

- A run **proposes** an action (`agent_actions` row, `status='proposed'`) — a typed intent (`kind` +
  `params`), e.g. `book_appointment`. Proposing is just data; it touches nothing external.
- A **human approves** it (`status='approved'`, `approved_by`/`approved_at`). Approval is **admin-only**.
- Only then can it **execute**: an executor performs the write via the live adapter, and only if the
  master switch `ACTIONS_ENABLED` is on. Execution is **idempotent** (re-running an executed action returns
  the stored result; `UNIQUE(tenant_id, idempotency_key)` blocks duplicate proposals), **audited** (every
  transition writes an `audit_events` row), and **tenant-isolated** (RLS on `agent_actions`).
- **Default OFF.** `ACTIONS_ENABLED=false` ships by default, so the platform stays advisory-only until a
  customer explicitly opts in. Unknown/disabled action `kind`s are refused.
- The **executor registry** maps `kind → executor`. In fixture mode an executor returns a deterministic
  synthetic confirmation (so the whole gate is offline-testable, per ADR 0003/0005); the live executor is a
  typed skeleton that calls the system-of-record write (e.g. ServiceTitan booking) — fail-closed until wired.

## Consequences

- "Advisory-only" becomes **"advisory by default, execute-on-approval"** without losing the trust posture:
  the AI proposes, a human disposes, every action is signed, logged, idempotent, and reversible where the
  upstream API allows. That's the enterprise-grade story (copilot with an approval gate, not an autopilot).
- The booking agent's `proposed` bookings (ADR 0006) are the natural source of `book_appointment` actions.
- The gate is generic: QBO categorizations, ServiceTitan reschedules, etc. are new `kind`s + executors, no
  new pipeline.
- **Future hardening (not in this slice):** per-tenant + per-kind policy table (this slice uses a global
  master switch), maker-checker separation (approver ≠ proposer), and reversal/compensation actions.
