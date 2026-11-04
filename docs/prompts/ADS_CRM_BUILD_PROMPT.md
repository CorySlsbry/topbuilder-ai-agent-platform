# Build Prompt — Admin Ads-CRM: automated Meta + Google campaign engine (Top Builder AI)

> Paste this whole file into a Claude Code session rooted at the repo root
> (`C:\Users\you\Downloads\ServiceTitan Agent platform`). It is the spec for an operator-only
> (platform-admin) module that builds and manages Meta Ads + Google Ads campaigns from templates and
> ties them into a real leads pipeline (CRM). Build it to the **$50k bar** this codebase already holds.

---

You are a top-0.1% staff engineer extending **Top Builder AI**, a multi-tenant FastAPI + LangGraph +
Postgres(+pgvector, RLS) platform with a Next.js frontend. Your job: ship an **admin/operator-only
Ads-CRM module** that (1) holds a real **leads pipeline**, (2) **OAuths into Meta Ads + Google Ads** and
**builds/manages campaigns automatically from templates**, and (3) closes the loop — ad leads land in the
CRM, and CRM outcomes sync back as conversions so the ad platforms optimize to real buyers.

## 0. Before writing any code (do this first, in order)
1. **Read the brain + project memory:** `[[central-build-learnings]]`
   (`C:\Users\you\Downloads\brain\wiki\synthesis\central-build-learnings.md`), this repo's `CLAUDE.md`,
   `docs/ENGINEERING_LOG.md`, `docs/adr/*` (esp. **ADR 0003** deterministic-compute firewall and
   **ADR 0007** human-approved action path), `docs/SECURITY_AUDIT_2026-06-12.md`, and the auto-memory
   `~/.claude/projects/C--Users-Cory-Downloads-ServiceTitan-Agent-platform\memory\MEMORY.md`.
2. **Study the patterns you will mirror** (do not reinvent):
   - Provider OAuth + credential vault: `app/integrations/*`, the Procore connector
     `/v1/integrations/procore/{connect,callback}`, the provider registry (`auth_kind`/`connect`),
     `app/crypto.py` (AES-256-GCM) and `scripts/rotate_credentials.py`.
   - Action gate (propose → approve → execute, idempotent, undoable, master switch `ACTIONS_ENABLED`,
     per-kind allowlist, RLS-isolated `agent_actions`): `app/actions/{executors,service,schemas}.py`,
     `app/repositories/actions.py`.
   - Operator authz: `PLATFORM_OPERATOR_EMAILS` allowlist, `require_unrestricted`, aal2 gating
     (from the 2026-06-12 security work). Reuse it; do not weaken it.
   - Persistence + RLS conventions, the loop-aware async engine in `app/db.py`, asyncpg casting rules.
   - The in-app assistant tool-permission gate (`app/assistant/*`) — its tools mirror REST bars exactly.
3. **Plan before code:** use `brainstorming` → `writing-plans`; write an **ADR (next number, e.g. ADR 0009)**
   "Admin Ads-CRM + ad-platform integration" capturing the data model, authz posture, money guardrails,
   determinism boundary, and phasing. Confirm the plan in the plan file before implementing. **TDD**: pure
   engine + hand-computed oracles first (C-1), then wire.
4. **Run the security skill** `enterprise-security-audit` against the design and again before "done."

## 1. Hard constraints (non-negotiable — violating any is a defect)
- **Operator-only.** Every route, table, and UI in this module is reachable ONLY by a platform operator
  (`PLATFORM_OPERATOR_EMAILS` + `require_unrestricted`; require **aal2** for any write that spends money or
  mutates a live ad account). This is **Cory's GTM data at the platform layer — NOT tenant data.** It must
  never be visible to or scoped by a tenant. Decide and document the storage posture: operator-global tables
  guarded by the operator gate (RLS policy that resolves only under the operator/platform context, fail
  closed) — keep consistency with the repo's RLS-everywhere rule; if you introduce a `platform`/operator
  scope, enforce it in DB policy AND app layer.
- **No money moves without explicit approval.** All ad-platform **writes** (create/update/activate campaign,
  raise budget, publish) go through the **action gate** (ADR 0007): `propose → approve → execute`,
  idempotent via an `external_ref`, reversible (pause/delete compensation). New campaigns/ads are created
  **PAUSED**; going ACTIVE is a separate gated action. Master switch off by default.
- **DB-backed budget caps, enforced server-side.** Per-campaign and per-account daily + lifetime caps live
  in the DB; the execute path refuses any spend change that would exceed them. Neither an operator misclick
  nor an agent can overspend.
- **Determinism firewall (ADR 0003).** All money/ROI/pacing/spend math comes from pure, unit-tested code.
  An LLM may *draft ad copy* and *explain* performance, but must **never compute a budget, bid, spend, or
  conversion number.** Keep the LLM on the narration/creative side of the boundary only.
- **Fixture-first, fail-closed live.** Mirror the existing integration pattern: every adapter has a
  `*_MODE=fixture|live` switch; fixture returns deterministic canned responses so the whole feature is
  testable with **no live API access**; the live path **fails closed** (never fabricates a successful ad
  write) and is exercised only when real secrets + modes are set.
- **PII hygiene.** Emails/phones sent to Meta CAPI / Google offline conversions are **SHA-256 hashed,
  normalized** per each platform's spec; never logged in plaintext; ad-account OAuth tokens live ONLY in the
  AES-256-GCM vault, never in logs or the DB in plaintext.
- **Real-auth deployment.** This module holds real PII + money-spending credentials → it must NOT run under
  the public demo posture (`ENV=dev`, dev-token). Gate it so it is inert unless `ENV=prod`/operator-JWKS is
  active (or document a separate operator-secured deployment). Add a startup guard + a test proving the
  module 403s under dev-token.

## 2. Data model (Postgres; new migration `00NN_ads_crm.sql`, next sequential number)
Operator-scoped (platform layer), all timestamps tz-aware, all money in integer **minor units (cents)**:
- `crm_contacts` — id, full_name, company, email (citext, unique-ish), phone, title, source, city/region,
  enrichment jsonb, created/updated.
- `crm_leads` — id, contact_id FK, pipeline_stage (enum: `new`→`contacted`→`booked`→`demoed`→`won`/`lost`),
  source (enum incl. `meta_ads`,`google_ads`,`booking`,`landing`,`manual`,`referral`), owner, value_cents,
  utm jsonb (source/medium/campaign/content/term), ad_ref jsonb (platform, campaign_id, adset/adgroup_id,
  ad_id), status, lost_reason, created/updated.
- `crm_activities` — id, lead_id FK, kind (note/email/call/booking/stage_change/conversion_synced), body,
  actor, payload jsonb, created.
- `ad_accounts` — id, platform (`meta`|`google`), external_account_id, name, vault_credential_id (FK to the
  existing vault), status, scopes, connected_by, connected_at. (Tokens NOT here — only the vault ref.)
- `ad_campaign_templates` — id, name, platform, objective, geo_spec jsonb (custom_locations: lat/long/
  radius/unit + location_type "recent"/"presence"), targeting_spec jsonb, schedule_spec jsonb (start/end),
  budget_spec jsonb (daily_cents, lifetime_cap_cents), creative_spec jsonb (primary_text/headline/
  description/cta/landing_url/image_ref), notes. Seed it from the trade-show kit (see §6).
- `ad_campaigns` — id, template_id FK (nullable), ad_account_id FK, platform, external_campaign_id,
  external_adset_id/adgroup_id, external_ad_ids jsonb, name, status (`draft`|`paused`|`active`|`ended`),
  daily_budget_cents, lifetime_cap_cents, spend_cents (synced), start_at/end_at, last_synced_at, created.
- `ad_metrics` — id, ad_campaign_id FK, day, impressions, clicks, landing_page_views, leads, spend_cents,
  raw jsonb. (Read-side; populated by the sync job.)
- `conversion_syncs` — id, lead_id FK, platform, event_name, sent_at, status, dedupe_key (idempotent),
  request/response jsonb (PII redacted/hashed).
Add RLS policies + a two-context test proving non-operator/tenant contexts see nothing.

## 3. Integrations (mirror `app/integrations/*`; fixture + live skeleton)
### 3a. Meta Ads (`app/integrations/ads_meta/`)
- OAuth: extend the provider registry + `/v1/integrations/meta/{connect,callback}` with **PKCE + state→
  server-session** (don't repeat Procore's open-state to-do). Scopes: `ads_management`, `ads_read`,
  `business_management`, `leads_retrieval`. Store token in vault → `ad_accounts.vault_credential_id`.
- Graph Marketing API client (live skeleton): create **Campaign** (`objective` OUTCOME_TRAFFIC /
  OUTCOME_LEADS, `status` PAUSED), **AdSet** with `targeting.geo_locations.custom_locations:
  [{latitude, longitude, radius, distance_unit:"mile"}]` + `targeting.geo_locations.location_types:["recent"]`
  for "recently in", interest targeting, `daily_budget` (cents), `start_time`/`end_time`, `billing_event`,
  `optimization_goal` (LANDING_PAGE_VIEWS), `bid_strategy`. **AdCreative** (`object_story_spec.link_data`:
  message/link/name/description/call_to_action/image_hash) and **Ad** (PAUSED). Read: insights →
  `ad_metrics`. Lead Ads retrieval → CRM. **Conversions API**: `Schedule`/`Lead` events with SHA-256 hashed
  user data → close the loop.
- Fixture mode returns deterministic ids (e.g. `meta-camp-FIXT01`) so tests pass with no network.
### 3b. Google Ads (`app/integrations/ads_google/`)
- OAuth: `/v1/integrations/google_ads/{connect,callback}` (PKCE+session). Needs an approved **developer
  token** + OAuth client + optional `login-customer-id` (MCC). Store token in vault.
- google-ads client (live skeleton): CampaignBudget; **Campaign** (`advertising_channel_type` DEMAND_GEN
  or DISPLAY for geofence, SEARCH reserved for branded/retargeting; `status` PAUSED); **proximity**
  campaign criterion (`ProximityInfo`: geo_point lat/long in micro-degrees, radius, `radius_units` MILES);
  location option **PRESENCE** ("people in or regularly in"); ad group + Demand Gen/responsive ad; final
  URL = the show landing page. Read: GAQL metrics → `ad_metrics`. **Offline conversion import /
  Enhanced Conversions for Leads** (hashed email) → close the loop.
- Fixture mode returns deterministic ids.

## 4. Action gate wiring (money safety)
Add executors to the existing registry: `ads.create_campaign`, `ads.update_budget`, `ads.activate_campaign`,
`ads.pause_campaign` (compensation = pause), `ads.sync_conversion`. Each: validates against DB budget caps,
is idempotent on `external_ref`, audited, PAUSED-on-create, reversible. Reuse `app/actions/service.py`
propose/approve/execute. `ACTIONS_ENABLED` + per-kind allowlist must include these explicitly.

## 5. Campaign engine (the "CRM builds the campaigns" core)
Pure, tested orchestrator `app/ads/engine.py`:
`build_from_template(template, ad_account) -> CampaignPlan` (pure: resolves geo/targeting/budget/schedule/
creative into the platform-specific request payloads, **deterministically**, with hand-computed oracles for
budget/cents/schedule math) → emits **proposed actions** (does NOT call the live API directly; goes through
the gate). A thin `app/ads/service.py` runs retrieve→plan→propose; on approve+execute the adapter performs
the live writes and records `ad_campaigns`/external ids. A nightly **sync job** (reuse the cron pattern,
`X-Cron-Key`) pulls metrics + leads and updates `ad_metrics`, `crm_leads`, fires due `conversion_syncs`.
Optional: a narration-only "Ads agent" that *drafts* copy/creative variants and *explains* performance —
strictly on the non-deterministic side of ADR 0003.

## 6. Seed the trade-show template (reproduce what we already built by hand)
Seed `ad_campaign_templates` from `marketing/trade-shows/2026-06-22/` so the CRM can one-click a show:
- **Build Expo Nashville** template: objective TRAFFIC; geo custom_location {lat 36.1565, long -86.7766,
  radius 1, unit mile, location_type "recent"} (+ optional host-hotel pins from `geofence-configs.md §1`);
  interests ServiceTitan/QuickBooks/contractor/HVAC/plumbing/roofing; daily_budget 1000 (=$10), lifetime
  cap 2000 (=$20); schedule 2026-06-30→2026-07-02; creative = Variant A from `ad-copy.md §1`, landing
  `https://topbuilderai.com/shows/build-expo-nashville-2026`. Also seed Houston, Western Roofing, Pantheon
  from the same kit. A generic `trade_show_geofence` template type drives all four (params differ only).

## 7. Lead capture + retargeting
- **Landing/booking → CRM:** add a signed webhook (or extend the booking service `booking/`) so a booking or
  show-page form submit creates `crm_contacts`+`crm_leads` (source/utm/ad_ref captured from query params).
  De-dupe by email; attach to the originating campaign via utm.
- **Pixel/tag:** add a config-driven Meta Pixel + Google tag include to the 4 show landing pages
  (`landing/shows/*.html`) gated on env-provided IDs (placeholders ok; do not hardcode). Fire PageView on
  show pages and a Lead/Schedule event on booking confirmation; this also feeds website Custom Audiences.
- **Retargeting:** build (paused) Meta website-custom-audience + Google remarketing audiences and a
  retargeting campaign template ("Just back from <show>?" creative from `ad-copy.md`), excluding `won`/
  `booked` leads. Document that retargeting cannot deliver until the audience populates from first traffic.

## 8. Frontend (operator-only admin)
Next.js, behind the operator gate (404/redirect for non-operators):
- **Pipeline board** (kanban by stage) + lead detail (activity timeline, ad attribution).
- **Ad accounts** (Connect Meta / Connect Google buttons → OAuth; connection-readiness line like the
  provider registry UI).
- **Campaigns** (templates → "Build campaign" → review the proposed gated action → approve → it lands
  PAUSED; a separate "Activate" button = the aal2 money action; budget cap + spend shown from `ad_metrics`).
- Reuse the friendly-error layer in `frontend/lib/api.ts`; never show raw "403"; explain operator/aal2/cap.

## 9. Tests + verification (the bar)
- Pure unit/property tests for the engine (budget cents, schedule windows, geo payload shape, cap
  enforcement, idempotency, PII hashing vectors) with hand-computed oracles — `pytest -m "not integration"`.
- DB-integration tests: RLS isolation (operator vs tenant vs anon), action gate propose→approve→execute→
  idempotent re-execute→undo, lead-capture dedupe, conversion-sync dedupe, dev-token 403 guard.
- Fixture-mode E2E: build Nashville template → proposed action → approve → fixture "creates" PAUSED
  campaign → metrics sync → a booked lead fires a (hashed) conversion_sync. **All green before "done."**
- Run the full suite the documented way; update `docs/ENGINEERING_LOG.md` (what worked / bugs / fixes),
  `CLAUDE.md` "Current state", the project auto-memory, and `[[central-build-learnings]]`.

## 10. External prerequisites (Cory's gates — surface as a checklist, do NOT fake)
Produce `docs/ADS_INTEGRATION_GOLIVE.md`: Meta App + Business verification + App Review for
`ads_management/ads_read/business_management/leads_retrieval`; Google Ads **developer token** approval +
OAuth client + (optional) MCC; the secrets to add to Secret Manager (Meta app id/secret + system-user
token, pixel id + CAPI token; Google client id/secret + dev token + login-customer-id); the env flips
(`ENV=prod`, operator JWKS, `*_MODE=live`, `ACTIONS_ENABLED=true`, `PLATFORM_OPERATOR_EMAILS`). Until those
exist, everything runs in **fixture mode** and is fully testable.

## 11. Non-goals / do-NOT
- Do NOT auto-activate or auto-spend; never click "publish" without a human-approved aal2 action.
- Do NOT let the LLM compute any spend/budget/bid/conversion figure (ADR 0003).
- Do NOT store ad tokens or PII in plaintext, in logs, or outside the vault.
- Do NOT expose any of this to tenants or under dev-token/public-demo posture.
- Do NOT hardcode account ids, pixel ids, or secrets — config/Secret Manager only.

## 12. Deliverables
ADR 0009 + plan file; migration `00NN_ads_crm.sql`; `app/integrations/ads_meta/*` + `ads_google/*`
(fixture+live); `app/ads/{engine,service}.py`; action executors; `app/repositories/{crm,ads}.py`; routes
`app/api/routes_crm.py` + `routes_ads.py` registered in `app/main.py`; seeded templates; landing pixel
includes; frontend admin views; tests (all green); `docs/ADS_INTEGRATION_GOLIVE.md`; updated ENGINEERING_LOG
+ CLAUDE.md + memory + brain. Phase so Phase 1 (CRM + fixture engine + Nashville template + pipeline UI)
lands fully green with zero live-API dependency; Phases 2–3 (live Meta, live Google, conversion loop) light
up as approvals/secrets arrive.

Work in small, test-backed increments. Stop and ask if any assumption about authz, money safety, or the
determinism boundary is unclear. Build it to the $50k bar.
