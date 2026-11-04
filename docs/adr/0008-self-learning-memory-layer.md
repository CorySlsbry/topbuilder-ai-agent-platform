# ADR 0008 — Self-learning memory layer (agents that improve from wins & losses)

- **Status:** Accepted
- **Date:** 2026-06-06
- **Related:** [0003](0003-deterministic-analytics-llm-explains.md) (the firewall this depends on),
  [0002](0002-multitenancy-via-postgres-rls.md), [0007](0007-human-approved-actions.md),
  the feedback loop (migration 0009)

## Context

The product promise is agents that get **better with use** — learning from what humans approve (wins) and
what they edit/reject/undo (losses). The naive way to "make an AI learn" is to fine-tune the base model on
feedback. For this product that is the wrong tool: fine-tuning is slow, expensive, per-tenant-impossible at
our price point, opaque to audit, and — most dangerously — it could move the **numbers**. This platform's
entire trust posture (ADR 0003) is that *figures come from deterministic, tested code and the LLM only
narrates*. Anything that lets feedback perturb a dollar amount is disqualified.

We also reviewed the failure mode that kills learning systems: **reward hacking / drift** — a loop that
optimizes a proxy until the output is gamed, or that amplifies one loud correction into global behavior.

## Decision

Adopt **gradient-free, memory-based learning** that lives entirely on the *narration / retrieval* side of
the ADR-0003 firewall. No base-model weights change. Four research-backed mechanisms, each chosen for a
specific reason:

1. **Case-Based Reasoning (CBR) case bank** — every run is recorded as a `agent_cases` row: the *situation*
   (numbers-light brief + embedding) and the *recommendation shape*, with an `outcome` that feedback later
   labels (`accepted|edited|rejected|undone`) and an `effectiveness` score. Retrieval surfaces the nearest
   resolved cases to steer future narration. (Generative-Agents-style retrieval: relevance × effectiveness ×
   recency.)
2. **CIPHER preference-from-edits** — a *substantial* human edit (normalized token-Levenshtein > 0.25) is
   distilled into a human-readable `agent_preferences` rule ("lead with the dollar exposure, then the single
   highest-impact action"). This is the highest-signal, most auditable form of learning.
3. **Reflexion / ExpeL framing** — wins and losses are retrieved as explicit "do this / avoid this" guidance
   injected into the prompt, not as opaque weights.
4. **LLM-as-judge + quorum** as the noise guard (below).

**The load-bearing safety property:** learning *only* writes/reads cases, preferences, and the narration
"lessons" block. It is structurally incapable of changing a computed figure, because the figures never pass
through this layer — they come from the deterministic engine and the persona still forbids recomputation.
This is why reward-hacking the numbers is *impossible by construction*, not by vigilance.

**Anti-drift controls (all enforced, not advisory):**

- **Quorum gate.** A distilled preference is born `quarantined`. It only becomes `active` after **≥3
  corroborating** cases. One angry edit cannot change behavior.
- **Tenant isolation.** Cases and auto-distilled preferences default `tenant_id` to the current tenant via
  RLS; `agent_preferences`' `WITH CHECK` *forbids* `app_user` from writing a global (NULL-tenant) row — the
  product-wide GLOBAL tier is operator-seed-only (Phase C, with an eval gate + approval). Tenant A's private
  corrections can never leak to Tenant B.
- **Best-effort + isolated sessions.** Every learning read/write runs in its **own** `tenant_session`,
  wrapped in `try/except`. A learning failure (even an un-applied migration) degrades to the exact
  pre-learning behavior and can never roll back a recommendation run or a feedback write.
- **Append-only audit.** Every learning write emits a `learning_events` row (this is an audited product).
- **Embeddings.** `vector(3072)` to match `knowledge_chunks` (OpenAI `text-embedding-3-large`); offline
  hashing provider in tests/CI. Brute-force cosine kNN (3072 > ivfflat's 2000-dim cap → no ANN index).

**Flow (online path, this slice):**

```
run ──▶ record_case(outcome='pending')                      [financial/service.py, isolated session]
feedback ──▶ on_feedback: label case + (edit>0.25) distill preference   [routes_feedback.py, isolated]
next run ──▶ retrieve_lessons() ──▶ graph state.lessons ──▶ reasoning.explain(lessons=…)  [narration only]
```

The retrieval is done in the service (not inside the LangGraph graph) so the graph stays session-free, per
existing convention. The reason node only narrates; the persona still quotes every deterministic figure
exactly.

## Consequences

- Agents demonstrably improve where it is **safe** to improve — phrasing, emphasis, which past approach to
  echo, which rejected approach to avoid — while the numbers stay frozen and tested. This is the honest
  version of "self-learning" for a financial-grade tool.
- New agent = same two hooks (`record_case` in its service, `lessons` in its graph/reasoning). Mechanical to
  replicate across the other five agents.
- **Deferred to later phases (not in this slice):**
  - **Phase C** — nightly consolidation (reflect → curate → **golden-set eval gate** → approval queue);
    a parameter/threshold store with a bandit tuner for the few numeric knobs that are *thresholds, not
    figures* (e.g. confidence cutoffs), still behind the eval gate.
  - **Phase D** — golden-set regression harness, shadow/canary rollout of newly-active rules, drift monitor,
    and the admin "learned-rule approval queue" UI surface.
- A preference is text a human can read, approve, edit, or retire — the opposite of an inscrutable weight
  update. Auditability is a feature, not an afterthought.
