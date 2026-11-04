# ADR 0009 — Admin Ads-CRM (operator-global leads pipeline + ad-platform campaign engine)

- **Status:** Accepted
- **Date:** 2026-06-22
- **Related:** [0002](0002-multitenancy-via-postgres-rls.md) (RLS), [0003](0003-deterministic-analytics-llm-explains.md)
  (the determinism firewall), [0005](0005-servicetitan-adapter-pattern.md) (fixture/live adapter),
  [0007](0007-human-approved-actions.md) (the gated write path — reused verbatim), [0008](0008-self-learning-memory-layer.md)
  · migration `0023_ads_crm.sql` · go-live gates: `docs/ADS_INTEGRATION_GOLIVE.md`

## Context

Top Builder AI needs its **own** go-to-market machine: a CRM for inbound leads (from the booking page,
landing page, Meta/Google ads, referrals) and an engine to plan, launch, and measure paid ad campaigns
(starting with the trade-show / geofence play that wins HVAC contractors). This is **Cory's / the
platform operator's** marketing data — leads, ad spend, campaign performance — **not** a customer
tenant's data. It must never appear in, or be reachable from, a tenant session.

That single fact drives every decision below. The rest of the platform is multi-tenant and RLS-scoped on
`app.current_tenant`; these tables are **operator-global** (no `tenant_id`) and must be:

- invisible to every tenant (a contractor logged into their own org must see zero ad/CRM rows);
- writable **only** by the platform operator (Cory), with 2FA;
- able to spend real money on Meta/Google — which means every ad-platform write must be **gated,
  audited, idempotent, and reversible**, exactly like every other system-of-record write;
- fully **testable offline** (the whole module runs with no live ad API), and **fail-closed** the
  moment it touches a live platform before that integration is verified;
- compliant on PII — conversion uploads to Meta/Google require hashed identifiers, never plaintext.

We deliberately do **not** invent a parallel write path, a parallel auth model, or a parallel crypto
story. The platform already has battle-tested machinery for all four concerns (gated writes, operator
auth, the credential vault, the determinism firewall). The Ads-CRM **reuses** them.

## Decision

### 1. Storage: operator-global tables + a two-layer operator gate

`0023_ads_crm.sql` adds nine operator-global tables — `operator_credentials` (ad-platform OAuth token
vault, separate from the tenant `tenant_credentials` vault), `crm_contacts` / `crm_leads` /
`crm_activities` (the CRM), and `ad_accounts` / `ad_campaign_templates` / `ad_campaigns` / `ad_metrics`
/ `conversion_syncs` (the ad engine). **No `tenant_id` column** anywhere — this is not tenant data.

Access is gated in **two independent layers** (defense in depth):

- **App layer** — every `/v1/crm` and `/v1/ads` route depends on `require_admin` (admin role **and**
  `aal == 'aal2'`, i.e. verified 2FA) **and** then calls a module-local `_require_platform_operator(principal)`
  that 403s unless `principal.email` is in `PLATFORM_OPERATOR_EMAILS`. This is the same two-line pattern
  proven in `routes_admin.py` / `routes_data_rights.py`. A per-tenant admin is **not** a platform operator;
  the allowlist is empty by default (fail-closed → nobody).
- **DB layer (RLS)** — the operator tables carry a fail-closed policy keyed on a transaction-local GUC:
  `USING (current_setting('app.operator', true) = 'on')`. The app opens these tables through
  `db.operator_session()`, which sets `app.operator='on'`. A normal `tenant_session` (which sets
  `app.current_tenant`, never `app.operator`) sees **zero rows**. The GUC defaults to `''` → policy
  false → no access. RLS is `ENABLE` (not `FORCE`) so the migration runner (table owner) can seed; the
  runtime `app_user` is a non-superuser and **is** subject to the policy.

Two boundaries means a bug in either one alone cannot leak: skip the app gate and RLS still returns
nothing; bypass RLS and the route still 403s a non-operator. Money is integer **cents** everywhere
(`*_cents`); enums are `text` + `CHECK` (codebase convention).

### 2. Every ad-platform write reuses the ADR-0007 action gate (no parallel write path)

There is exactly **one** way to perform an external write in this codebase: `propose → approve →
execute` through `app/actions/`. The Ads-CRM adds five new `kind`s and their executors and registers
them — it does **not** add an ad-specific write endpoint.

- New kinds (in `app/agents/ads/executors.py`, registered in `app/actions/executors.py`):
  `ads.create_campaign`, `ads.update_budget`, `ads.activate_campaign`, `ads.pause_campaign`,
  `ads.sync_conversion`. Each is added to `actions_allowed_kinds` in `config.py` (registering an
  executor is necessary but **not** sufficient — `is_executable_kind` also requires the kind in the
  allowlist).
- **Create-PAUSED.** `ads.create_campaign` always builds the platform payload with `status='PAUSED'`
  (the pure engine, `app/ads/engine.py`, sets it). Nothing spends on create. The **only** executor that
  flips a campaign to `ACTIVE` is `ads.activate_campaign` — so starting spend is a distinct, separately
  approvable, 2FA-gated step.
- **activate / create / budget = aal2 + ALWAYS-HITL.** The three money-committing kinds
  (`ads.create_campaign`, `ads.update_budget`, `ads.activate_campaign`) are added to `ALWAYS_HITL_KINDS`
  so that even an `auto`-mode agent **queues** them for a human rather than self-firing. `ads.pause_campaign`
  (reduces spend) and `ads.sync_conversion` (idempotent, no spend) are safe to auto-execute.
- **Reversible.** Each kind has an undo executor: create→delete/archive, update_budget→restore the prior
  budget (carried in `params`), activate→pause, pause→activate, sync→retract/flag. Every executor result
  carries a stable `external_ref` — the audit handle and the undo handle.
- **Idempotent.** Pass a stable natural id (the external campaign/conversion id) or a caller
  `idempotency_key` so a retried create/update can't double-spend. `conversion_syncs` is additionally
  idempotent at the DB layer: `UNIQUE (platform, dedupe_key)`.

Because the gate is generic and `agent`/`kind` are free-text columns, **no migration to `agent_actions`
is needed** — ad-platform actions are recorded by the same agent-agnostic persistence as every other
action, with the same audit, idempotency, and RLS guarantees.

### 3. Determinism firewall (ADR 0003) — the LLM never computes a budget, bid, spend, or schedule

All money/budget/bid/spend/cents/schedule math lives in pure, tested code (`app/ads/engine.py` +
`app/ads/schemas.py`). The engine resolves a template's jsonb specs + the selected ad account into a
fully platform-ready `CampaignPlan`, including the per-platform CREATE payloads, with **no I/O and no DB
access** — every value is computed from inputs, so it is unit-testable against hand-computed oracles.
Unit conversions are deterministic and hand-checkable: Meta `daily_budget` is cents-as-a-string (minor
units); Google `amount_micros = cents * 10_000`. The LLM (where used at all) only narrates the plan; it
never produces a figure. This makes ad-spend reward-hacking impossible by construction — the numbers
never pass through a model.

### 4. Fixture-first / fail-closed live (ADR 0005)

`ads_mode` (one gate for both platforms, `fixture | live`, default `fixture`) selects the adapter:

- **fixture** — `app/integrations/ads_meta/client.py` + `app/integrations/ads_google/client.py` return
  deterministic ids and canned metrics fully offline. The entire module — engine, executors, service,
  routes, CRM — is testable with **no live ad API**.
- **live** — the live client path **fails closed**: until the real Meta/Google write is wired and
  verified, an executor **raises** `ActionError` rather than fabricating a success. A campaign can never
  be reported as launched when it wasn't. (Same posture as `SERVICETITAN_MODE=live`, proven by the
  fail-closed tests.)

### 5. PII hashing for conversion uploads

`ads.sync_conversion` ships customer-match identifiers to Meta's Conversions API / Google's Enhanced
Conversions. Both require identifiers **normalized then SHA-256 hashed (lowercase hex)** before they
leave our servers. `app/ads/pii.py` is the pure, no-log normalizer: email → trim+lowercase→sha256;
phone → strip to E.164 digits→sha256. The executor and `conversion_syncs.payload` only ever hold the
hex digest — **plaintext PII is never persisted, logged, or printed.**

### 6. OAuth: PKCE + a state→server-session binding (operator-scoped)

The three older providers (Procore/Google/QBO) use a stateless HMAC `state` and explicitly **defer**
PKCE + session binding as pre-production hardening. The Ads-CRM **closes** that gap rather than copying
the shortcut (`app/api/routes_ads_oauth.py`):

- **PKCE (RFC 7636, S256)** — the `code_challenge` rides the authorize URL; the matching `code_verifier`
  never leaves our server, so an intercepted `code` alone is useless.
- **state → server session** — `state` + `code_verifier` are HMAC-signed (over the app's JWT secret,
  which refuses the `change-me` placeholder) into a short-lived **HttpOnly, SameSite=Lax** cookie. The
  callback re-derives them and refuses unless the cookie's `state` matches the query `state` (constant-time
  compare) — binding the round-trip to the initiating browser and defeating login-CSRF.
- `/connect` is operator-only (`require_admin` + the operator allowlist). `/callback` carries **no** auth
  dependency by design (the caller is the provider redirect) — the signed cookie + state are the proof of
  which flow it belongs to. Provider exchange errors map to a **generic 502** (never echo the body, which
  can contain the code). Tokens are stored encrypted in the **operator** vault (`operator_credentials`,
  AES-256-GCM via `app/crypto.py`) and bound to `ad_accounts.vault_credential_id`. Google's
  `refresh_token` is required (we force `prompt=consent`); a missing one fails closed rather than storing a
  half-linked connection.

Operator ad tokens are added to `scripts/rotate_credentials.py` coverage so key rotation still reaches
them.

## Phasing

- **Phase 1 (this slice — built):** the full offline-capable spine. Migration 0023; the operator gate
  (app + RLS); `app/ads/` pure engine + schemas + PII + service; the five gated/reversible executors
  registered + allowlisted + HITL-defaulted; fixture Meta/Google clients; `/v1/crm` + `/v1/ads` routes;
  PKCE+session OAuth connect/callback for Meta + Google Ads; operator-credential vault. `ads_mode=fixture`,
  `ACTIONS_ENABLED=false` — advisory/offline, nothing spends. Pure tests green.
- **Phase 2 (live wiring):** implement the live Meta Marketing/Conversions + Google Ads write paths
  behind `ads_mode=live` (still fail-closed until each call is verified against a real account); seed the
  trade-show/geofence campaign templates; inject the env-gated Meta Pixel + Google tag on the show pages
  for client-side signal; nightly metrics sync into `ad_metrics`. Requires Cory's external go-live gates
  (`docs/ADS_INTEGRATION_GOLIVE.md`).
- **Phase 3 (close the loop):** lead→conversion attribution (`ad_ref`/`utm` on `crm_leads` → server-side
  `ads.sync_conversion` on stage changes like booked/won), and feed measured results back into the
  campaign engine (which template/geo/budget actually produced booked jobs).

## Consequences

- The platform's own marketing system is **operator-isolated by two boundaries**, **spends money only
  through the audited, reversible, 2FA-gated action gate**, **never lets a model compute a figure**, runs
  **fully offline in fixture mode**, **fails closed on live**, and **hashes PII** — i.e. it inherits every
  trust property the customer-facing product already has, with no new bespoke security surface.
- New ad platform later = one new fixture/live client pair behind the same `ads_mode` gate + (if needed)
  new `kind`s. No new pipeline, no new auth, no new vault, no new crypto.
- The work that genuinely needs Cory (Meta App Review, Google Ads developer-token approval, pixel/CAPI
  tokens, the prod env flips) is isolated to **Phase 2/3** and enumerated in `docs/ADS_INTEGRATION_GOLIVE.md`.
