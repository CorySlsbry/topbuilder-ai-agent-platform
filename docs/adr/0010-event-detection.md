# ADR 0010 — Universal event detection and auto-act (ServiceTitan + QuickBooks)

Status: Accepted (2026-06-27). Builds on ADR 0002 (RLS), ADR 0003 (deterministic compute,
LLM-narrates), ADR 0005 (read-only ST adapter), ADR 0007 (the human-approved action gate).

## Problem

Agents are **pull-only** today: a run happens when something `POST`s `/v1/agents/{x}/runs` or a
Cloud Scheduler cron pings an endpoint, and the run fetches the *whole* current batch by `as_of`.
Nothing watches for a single new item. The goal: **every relevant new or changed ServiceTitan and
QuickBooks item is detected, routed to the right agent, and acted on through the existing gate —
advisory by default.**

## Decision

A **change-feed poll loop is the completeness backbone; webhooks are a latency overlay** that
dedupe-merges into the *same* inbox. Everything funnels through one queue and the unchanged ADR-0007
gate.

### Detection sources (per `(tenant, source, entity)` durable cursor)

| Source | Mechanism | Role |
|---|---|---|
| ServiceTitan `/export` change-feed | `GET /{module}/v2/tenant/{t}/export/{entity}` with a persisted `continueFrom` token (filters on `modifiedOn`); `hasMore` + new `continueFrom` | **Primary** detector where an export feed exists |
| ServiceTitan modified-since list poll | standard list endpoint filtered by `modifiedOnOrAfter` watermark, existing `hasMore`/`continueFrom` paginator | Fallback for entities lacking `/export` (attachments, some payroll/inventory) |
| ServiceTitan V2 webhooks | existing signed `POST /v1/webhooks/servicetitan/{tenant_id}` | Latency overlay only — the next poll tick catches a dropped event |
| QuickBooks webhooks | new `POST /v1/webhooks/quickbooks`, `intuit-signature` HMAC, tenant from `realmId` (never a session) | Latency overlay for the eligible AP/AR set |
| QuickBooks CDC poll | `cdc?entities=...&changedSince=` over a list that **includes `Attachable`** | **Required** — `Attachable` (receipts) fires **no** QBO webhook |
| In-house emit | field-PWA snap / email-in writes the inbox row at capture | Real-time + clean OCR for app-born receipts |
| Daily reconcile sweep | wide modified-since re-anchor | Cursor-drift / crash / redeploy recovery |

Verified against the official docs: ServiceTitan's canonical change-detection is the **Export API
change-feed** (continuation token), *not* general webhooks; QuickBooks `Attachable` is **not**
webhook-eligible and must be polled (CDC or a direct `LastUpdatedTime` query).

### Pipeline

`detect (poll/webhook/emit)` -> `normalize` -> `enqueue (event_queue, dedupe)` ->
`drain: claim_pending` -> `route` -> `agent.run (deterministic, ADR-0003)` ->
`propose_action (system principal)` -> gate (`off | hitl | auto`, `ALWAYS_HITL` for money/legal).

Two cron entrypoints mirror the existing `X-Cron-Key` pattern: `POST /v1/sync/cron/poll`
(detect + enqueue) and `POST /v1/sync/cron/drain` (route + propose), plus a daily reconcile.

### Posture: approve-first

The loop only ever **proposes**. Per-agent autonomy stays `off | hitl | auto`; `ACTIONS_ENABLED`
defaults off. The first cohort runs **approve-first for everything** (every proposal waits for a
human); the per-agent `auto` mode is the path to autonomy once a shop trusts the output, and
`ALWAYS_HITL_KINDS` (AP draft, payroll, dunning, pricebook price, ad spend) force a human even under
`auto`. No new LLM call — figures stay deterministic.

## Reused vs new

Reused verbatim: `event_queue` + its dedupe + `claim_pending`/`mark_processed`, the signed webhook
receiver, `db.tenant_session` RLS, the whole `actions.service` gate, the `X-Cron-Key` cron pattern.
New: a `sync_cursor` table, `sync_dead_letter`, `qbo_connection`; `app/sync/` (pure `normalize` /
`router` / `cursors` + a `service` orchestrator + a propose-only **system principal**); the ST
`/export` + QBO CDC code paths.

## Safety invariants

1. **Tenant without a user.** Cron iterates tenants and opens a fresh `tenant_session` each; the ST
   webhook scopes from the MAC-bound path `tenant_id`; the QBO webhook from `realmId -> qbo_connection`.
   Every DB touch runs inside `tenant_session`, so RLS fail-closes.
2. **System principal is propose-only.** `role='system'` with a fixed sentinel `user_id` (not the
   demo admin). It is hard-refused inside `approve_action` / `execute_action` (belt) on top of the
   per-agent `mode` + `ALWAYS_HITL` (suspenders).
3. **Idempotency, three layers.** (a) `event_queue` `ON CONFLICT (tenant_id, source, external_id)` —
   every producer supplies a **non-null** natural key `source:entity:provider_id:modified_at`, so
   `includeRecentChanges` repeats and webhook/poll overlap collapse, while an edited item (new
   `modifiedOn`) is a new event; (b) the gate's `idempotency_key` derives from the event id so
   re-drain never double-proposes; (c) the executor claim/write/record split.
4. **Cursor durability.** `sync_cursor` advances **only after** the batch is durably enqueued in the
   same `tenant_session`, so a crashed/skipped tick resumes gap-free; the daily reconcile re-anchors
   drift. This — not webhooks — is the completeness guarantee.
5. **Poison isolation.** Per-event `try/except` + `retry_count`/`next_attempt_at` backoff; past the
   ceiling the event moves to `sync_dead_letter` (not back to pending) so it can't head-of-line block.
6. **Fail-closed live adapters.** Unmapped/NotImplemented entities refuse rather than fabricate.
   Auto-match degrades to `needs_human` on a missing/handwritten job ref — never a guessed allocation.

## Phasing

- **Phase 0** (this change): the spine + safety primitives, all fixture, zero live calls — migration,
  `sync_cursor`/`sync_dead_letter`/`qbo_connection` + `event_queue` retry columns, the system
  principal + enforcement, pure `normalize`/`router`/`cursors`, the cron skeleton + `emit_event`.
- **Phase 1**: the first vertical slice — ST inventory-bills/invoices/payments (fixture) ->
  Financial/Collections -> `create_ap_draft` (ALWAYS_HITL) + dunning candidacy, end-to-end
  advisory/idempotent/undoable. Then fill the live ST `/export` mappers against one real tenant.
- **Phase 2**: breadth across the entity ledger; QBO webhook + CDC (incl. `Attachable`); the daily
  reconcile; the field-PWA/email-in emit path.
- **Phase 3**: dead-letter replay UI, rate-budget monitoring, a dedicated worker for high-churn
  tenants, the production tenant-enumeration connection.

## Open items (tracked, not yet wired)

- **Prod tenant enumeration**: the cron iterates `DEMO_TENANTS`; prod needs an admin/RLS-bypass
  connection or a non-RLS `active_tenants` registry (the `tenants` table is RLS-protected from
  `app_user`). Same open item as every existing cron.
- **Live ST/QBO credentials + a verification tenant** (Summit) to confirm `/export` field shapes
  (mappers stay `NotImplementedError` by ADR-0005 until verified).
