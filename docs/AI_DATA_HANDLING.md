# AI Data Handling & the No-Training Guarantee

How Top Builder AI handles customer data when it uses a large language model (LLM). Written to answer
the questions partners and security reviewers ask directly — e.g. Procore's: *"Is customer data used
in model training or isolated to inference? Is data retained beyond a session? What are the deletion
controls?"* (tracked as the **No-training guarantee** and **retention/deletion** BUILD items in
[`docs/PROCORE_PARTNER_APPLICATION.md`](./PROCORE_PARTNER_APPLICATION.md) and the security gate in
[`docs/SECURITY_AUDIT_2026-06-12.md`](./SECURITY_AUDIT_2026-06-12.md)).

This document describes only what the running code does. Every claim cites the file that enforces it.

## TL;DR

- **Inference only — never training.** External LLM calls (Anthropic's Messages API) are used to write
  human-readable narration. Anthropic's commercial API does not train models on API inputs or outputs,
  and nothing in our code opts into any training/feedback program. There is no such setting to enable.
- **The model never produces a business number.** Every figure (gaps, hours, dollars, confidence) comes
  from deterministic, unit-tested code — the **ADR-0003 figure firewall**. The LLM only narrates results
  that were already computed.
- **LLM calls are stateless.** Each request carries the conversation it needs and nothing is retained by
  the model between requests. Customer / ServiceTitan / QuickBooks data persists only in **our**
  RLS-isolated Postgres, per tenant — never in the model.
- **Self-learning is retrieval, not training.** The self-learning layer stores per-tenant *narration*
  cases in our own database and retrieves them to steer wording. It does **not** fine-tune or train any
  model, and by construction it cannot touch a figure.
- **Retention & deletion** are controlled by us in our own database; see
  [Retention & deletion](#5-data-retention--deletion).

## 1. Where an LLM is actually called

| Path | LLM used? | Notes |
| --- | --- | --- |
| Deterministic agents (workforce, financial, inventory, booking, routing, documents, email, SEO) | Narration only — and **off in production** | Each `app/agents/<name>/reasoning.py` short-circuits to a deterministic template when `DISABLE_LLM=1` or no key is set (see `agents/financial/reasoning.py` `explain()`). Production runs with `DISABLE_LLM=1`. |
| **In-app assistant** (`app/assistant/`) | **Yes — the one live LLM path** | A Claude Sonnet tool-use loop that drafts copy and does admin work. It is independent of `DISABLE_LLM`. |
| Self-learning nightly consolidation (`app/learning/consolidation.py`, `eval_harness.py`) | Optional, narration-distillation only | Proposes/evaluates *narration* rules; gated behind eval + human approval (ADR 0008). Never trains a model. |

Because the assistant is the single live-LLM path in the running product, the external-LLM data posture
is pinned and documented in one place: **`app/assistant/llm_client.py`**. `app/assistant/service.py`
builds its client via `build_assistant_client(settings)` from that module — no inline client.

## 2. Inference only, never training

- The Anthropic commercial API does **not** use API inputs or outputs to train models. Our client
  constructor (`app/assistant/llm_client.py` → `build_assistant_client`) opts into **no** training or
  data-sharing program; there is deliberately no "enable training" header or setting anywhere in the
  codebase.
- The self-learning loop (Section 4) is **retrieval-augmented narration**, not model training: it writes
  rows to our database and reads them back into a prompt. No gradients, no fine-tuning, no model weights
  are produced or updated by anything we run.

## 3. The figure firewall (ADR-0003) — the LLM never computes

Per [ADR 0003](./adr/0003-deterministic-analytics-llm-explains.md), every agent is split into:

1. a **deterministic compute layer** (pure Python + SQL, fully unit-/property-tested) that produces
   *every* number; and
2. a **narration layer** where the LLM receives the *already-computed* results and writes prose, with an
   explicit instruction to quote the numbers, never recompute them.

This is enforced even on the live assistant path: the assistant's tools return figures verbatim from
persisted agent results, and its system prompt (`app/assistant/prompts.py`, hard rule #1) forbids
inventing or computing any figure. The figure firewall is therefore a *correctness* control and an
*AI-data* control at once — a number can never be shaped by, or leak through, the model.

## 4. Self-learning = per-tenant retrieval, RLS-isolated, narration-only

The self-learning layer (`app/learning/`, [ADR 0008](./adr/0008-self-learning-memory-layer.md)) lets the
agents improve their *explanations* from human feedback — it does not train a model:

- `app/learning/service.py` writes narration **cases** (`record_case`) and preference rules
  (`on_feedback`) and reads them back (`retrieve_lessons`) into the narration prompt **only**. Its module
  docstring states the ADR-0003 boundary explicitly: it never reads or writes a figure.
- Storage is **our** Postgres, **RLS-isolated per tenant** (migration `0010` tables `agent_cases`,
  `agent_preferences`, `learning_events`; global-tier rows are operator-seed-only via `WITH CHECK`).
  One tenant's learned narration can never reach another tenant — there is no cross-tenant aggregation.
- Every learning read/write runs in its own isolated, best-effort `tenant_session` (try/except), so a
  learning failure can never roll back a run.
- Poisoning defenses (distinct-author quorum, offline eval refuse-by-default, deploy-gated auto-approve,
  a financial-injection denylist) are documented in the security gate; see
  [`docs/SECURITY_AUDIT_2026-06-12.md`](./SECURITY_AUDIT_2026-06-12.md).

This is recommendation/retrieval, not model training: a learned rule only changes which past *wording*
is shown to the narration model, and only after clearing an eval gate + human approval + canary.

## 5. Data retention & deletion

- **The model retains nothing.** LLM calls are stateless per request (Section 1). No customer, ServiceTitan,
  or QuickBooks data is retained by the model beyond serving the call.
- **We retain data in our own RLS-isolated Postgres**, per tenant — the system of record for runs,
  recommendations, communications, tasks, audit events, and the self-learning cases above. Tenant
  isolation is Postgres **RLS FORCE** with a non-superuser app role; cross-tenant reads fail closed (see
  [`docs/SECURITY_POSTURE.md`](./SECURITY_POSTURE.md)).
- **Deletion controls** — purge of a tenant's data on request, retention duration, and the customer
  deletion-request runbook are owned in the security/partner program: see the retention + deletion BUILD
  items in [`docs/PROCORE_PARTNER_APPLICATION.md`](./PROCORE_PARTNER_APPLICATION.md) (items 1 and 5) and
  [`docs/SECURITY_POSTURE.md`](./SECURITY_POSTURE.md). Audit trails (`audit_events`) are append-only.
- **No-retention at the LLM provider, when entitled.** Zero-data-retention is an *account-level* Anthropic
  entitlement. When it is provisioned on the production account, set `ANTHROPIC_ZERO_RETENTION=true`
  (Section 6) and `app/assistant/llm_client.py` sends the documented opt-out header so request/response
  bodies are not retained beyond serving the call. The flag defaults **off** (no-op); the no-**training**
  guarantee in Section 2 holds regardless of this header.

## 6. Configuration

`ANTHROPIC_API_KEY` (existing) is the only credential the live LLM path needs; with it unset the assistant
returns `503` and no external call is made, and `DISABLE_LLM=1` keeps all agent/learning narration on the
deterministic templates.

One **optional** new setting governs the provider-side no-retention header (it does not affect the
no-training posture, which is always on):

```
# Optional. Send Anthropic's no-retention opt-out header. Only effective once zero-data-retention is
# provisioned on the Anthropic account; defaults off (no-op). See app/assistant/llm_client.py.
ANTHROPIC_ZERO_RETENTION=false
```

Backed by the new setting `anthropic_zero_retention: bool = False` (see the wiring note in the engineering
summary). The helper reads it defensively, so it is safe whether or not the setting has been added to
`config.py` yet.
