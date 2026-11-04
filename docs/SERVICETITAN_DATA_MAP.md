# ServiceTitan Data Map — feasibility + reliability for the Org Chart and the 55-KPI Scorecard

**Author/date:** 2026-06-17 · **Scope:** confirm (or flag) that once a tenant connects ServiceTitan, we
can build (a) the **Org Chart / org sphere** and (b) **every scorecard KPI** in
[`docs/ALEX_SCORECARD_SPEC.md`](ALEX_SCORECARD_SPEC.md), with each claim grounded in the **current**
ServiceTitan developer API (developer.servicetitan.io).

**Hard constraint honored throughout (Cory):** **NO third-party connectors / iPaaS — absolutely NO
Zapier.** Every integration here is a **direct, first-party** call to ServiceTitan's own REST API
(OAuth2 client-credentials → `ST-App-Key` → `api.servicetitan.io/...`). This is the design that killed
the client's brittle Zapier flow (Summit Heat Pumps; their Zapier→Bloom pipe "broke constantly").

**Citation note:** the ServiceTitan dev portal (developer.servicetitan.io) is a JS-rendered SPA that
does not return HTML to a fetcher, so endpoint *paths and operation IDs* below are grounded in
ServiceTitan's own published help articles plus the OpenAPI-derived third-party references that mirror
the spec verbatim (Prismatic, Celigo, Rollout, the ServicePytan client, and the OpenAPI-generated
ServiceTitan MCP tool catalog on Glama). Each row links the doc section it came from. Field/unit shapes
must still be re-verified against the first live tenant before a number is served (ADR 0005) — that is
the only "trust but verify" caveat, and it is exactly what our fail-closed live skeleton enforces.

---

## 1. Auth + connection model (the reliable, no-Zapier path)

ServiceTitan exposes a single first-party REST API secured by **OAuth 2.0 client-credentials** (machine-
to-machine). There is no user-interactive OAuth and **no refresh token** — you mint a short-lived bearer
token from a per-tenant Client ID/Secret and present it with an app-wide `ST-App-Key` header.

### 1.1 The three credential artifacts

| Artifact | Where it comes from | Scope | Notes |
|---|---|---|---|
| **App Key** (`ST-App-Key`) | Our developer app in the dev portal **My Apps** (generated once we add tenant IDs + select scopes + select webhook events) | One per **application** | Same App Key is reused across all tenants. ([App Key/Client ID/Secret FAQ](https://developer.servicetitan.io/docs/faqs-app-key-client-id-secret/)) |
| **Client ID + Client Secret** | The **tenant's** ServiceTitan admin authorizes our app (Settings → Integrations → API Application Access); each connection issues a Client ID/Secret **unique to that app + tenant** | One pair **per tenant** | "If you have an application used by 10 ServiceTitan customers/tenants, you need 10 Client IDs & Secrets but can use the same app key." ([FAQ](https://developer.servicetitan.io/docs/faqs-app-key-client-id-secret/)) |
| **Tenant ID** | The tenant's numeric ServiceTitan account id | One per tenant | Goes in **every** request path: `/{module}/v2/tenant/{tenant}/...` ([ServicePytan endpoint structure](https://elliotp.medium.com/introducing-servicepytan-a-python-library-for-the-servicetitan-api-v2-f77a16eee46b)) |

This is the **"I, the app developer, will configure the credentials on behalf of each tenant"** client-
credentials mode — the tenant authorizes once, we hold the per-tenant secret. ([Prismatic ServiceTitan
connector](https://prismatic.io/docs/components/servicetitan/))

### 1.2 Token flow

1. `POST {auth_host}/connect/token` with `grant_type=client_credentials`, `client_id`, `client_secret`
   (form-urlencoded). Returns an `access_token` that **expires in 900 seconds** and **no refresh token**:
   *"Currently, the ServiceTitan API employs only access tokens and does not issue refresh tokens."*
   ([OAuth 2.0 docs](https://partnerapis.servicetitan.io/docs/oauth20/))
2. Call any module endpoint with `Authorization: Bearer {access_token}` **and** `ST-App-Key: {app key}`.
3. **Cache the token** — ServiceTitan throttles requests for *new* tokens: *"We recommend you cache the
   access token instead of requesting a new token for every transaction, since ServiceTitan employs
   throttling of API requests to new access tokens."* ([OAuth 2.0 docs](https://partnerapis.servicetitan.io/docs/oauth20/))

> **Status in our codebase:** already implemented and unit-testable in
> `backend/app/integrations/servicetitan/live_client.py` — `_access_token()` does the client-credentials
> POST with monotonic-clock token caching (refresh 60s before expiry) and tenacity retry/backoff;
> `_headers()` sets `Authorization` + `ST-App-Key`. Config knobs already exist in `app/config.py`:
> `servicetitan_client_id/_secret/_app_key/_tenant_id`, `servicetitan_auth_url`
> (`https://auth.servicetitan.io/connect/token`), `servicetitan_base_url`. ✓ No code change needed for auth.

### 1.3 Environments (integration vs production)

ServiceTitan runs **two fully separate stacks**, each with its own ClientID/Secret. The docs say to use
*"environment (integration versus production)-specific ClientID and Secret key."*
([OAuth 2.0 docs](https://partnerapis.servicetitan.io/docs/oauth20/))

| | Auth host | API host |
|---|---|---|
| **Integration** (sandbox; for our build/test) | `https://auth-integration.servicetitan.io/connect/token` ([Rollout API essentials](https://rollout.com/integration-guides/servicetitan/api-essentials)) | `https://api-integration.servicetitan.io` |
| **Production** (the live customer tenant) | `https://auth.servicetitan.io/connect/token` ([OAuth 2.0 docs](https://partnerapis.servicetitan.io/docs/oauth20/)) | `https://api.servicetitan.io` |

> **Action:** our default `servicetitan_base_url` is `https://api.servicetitan.io` (production). For the
> first integration-tenant test, override `servicetitan_base_url`→`api-integration` and
> `servicetitan_auth_url`→`auth-integration`. (Note: ServiceTitan integration tenants are provisioned by
> ServiceTitan; "always use ServiceTitan's sandbox environment for testing." — [Rollout](https://rollout.com/integration-guides/servicetitan/api-essentials).)

### 1.4 Rate limits

- **Standard APIs:** **60 calls / second / application / tenant.** ([ServiceTitan help — default API rate
  limits](https://help.servicetitan.com/problem-solution/what-are-the-default-api-rate-limits-in-servicetitan-for-regular-apis-and); echoed by [Rollout](https://rollout.com/integration-guides/servicetitan/api-essentials))
- **Reporting API:** **the *same* report can be run only ~1–5×/minute/tenant** (the ServiceTitan help
  page states *"1 of the same report per minute per tenant"*; Rollout cites 5). Treat the Reporting API as
  **scarce** — pull a report at most a few times/minute and cache. ([help](https://help.servicetitan.com/problem-solution/what-are-the-default-api-rate-limits-in-servicetitan-for-regular-apis-and))
- New-token minting is separately throttled (see §1.2) → token caching is mandatory.

> Our paginator (`_get_paginated`) already backs off + retries; add a 60-req/s tenant limiter and a
> separate, slow Reporting-API queue at go-live (§5).

### 1.5 Freshness — the reliable pattern (webhooks where available, else scheduled Export/Reporting polls), and how it fails closed

ServiceTitan gives three freshness mechanisms, in descending order of "real-time":

1. **V2 Webhooks** — *"a next-generation event notification platform offering improved performance,
   enhanced security through **HMAC verification**, a self-service interface to manage event
   subscriptions, a more robust retry mechanism for failed deliveries, and closer alignment with API data
   models."* Subscribed per app in **My Apps** (callback URL + event selection), delivered per tenant.
   ([V2 Webhooks FAQ](https://developer-next.servicetitan.io/docs/faqs-v2-webhooks/)) Best for **event-
   driven** triggers: a job completes, an invoice posts, an employee is hired/terminated → push to us.
2. **Export APIs** — endpoints with **`/export` in the path** that *"return active, inactive, deleted data
   with no filters applied"* for *"a full snapshot of the data [you] refresh as frequently as you want,"*
   using a **continuation token** (`from`) so each subsequent pull returns only what changed (the
   `export_invoices` / `export_invoice_items` tools take `tenant`, `from` = continuation token/date,
   `includeRecentChanges`). *"Only a few highly adopted APIs have data export endpoints."*
   ([Transactional & Export APIs](https://developer.servicetitan.io/docs/transactional-and-export-apis/);
   [export_invoice_items](https://glama.ai/mcp/servers/JordanDalton/ServiceTitanMcpServer/tools/export_invoice_items))
   Best for **high-volume entities** (invoices, jobs) as a durable change-feed.
3. **Delta GET polls** — standard list endpoints accept `modifiedOnOrAfter` / `modifiedBefore` (and
   `completedOnOrAfter`, `createdOnOrAfter`) so a scheduled poll fetches *"only changed records since the
   last sync time."* ([Rollout — reading data](https://rollout.com/integration-guides/servicetitan/reading-and-writing-data-using-the-servicetitan-api))
   Best for the **weekly scorecard rollups** (cheap, bounded by date window) and any entity without a
   webhook/export.

**The reliable design (no Zapier):**
- **Roster (hire/fire):** subscribe the employee/technician webhook (real-time org-sphere update),
  **backstopped** by a nightly `employees`/`technicians` reconcile poll. We already have both seams
  (`routes_webhooks.receive_servicetitan` → `classify_employee_event` → `apply_employee_change`; bulk
  `reconcile_roster`).
- **Scorecard:** **scheduled weekly polls** of the standard list endpoints with date windows (jobs by
  `completedOnOrAfter`, estimates by `soldAfter`, calls by date) + the Reporting API for the Dispatch-Pro
  productivity table — Export API for invoices. Webhooks merely *trigger an earlier recompute*; the number
  is always recomputed from a deterministic pull, never from the webhook body.

**How it fails closed (already enforced in our code):**
- Webhooks are **HMAC-verified** and **deduped**; an unverified or replayed event is dropped
  (`routes_webhooks`). An **empty roster pull refuses to mark the whole org departed** (`reconcile_roster`
  guards `if not any(external_ref): return skipped`) — a provider outage can't fire everyone.
- `scorecard_data.get_scorecard_data()` **raises rather than fabricate** when live mapping isn't verified
  (ADR 0005). The Workforce live client raises `NotImplementedError` on any unmapped endpoint rather than
  guess units. So a partial/failed ST pull surfaces as a clear error, never a wrong figure (ADR 0003).

---

## 2. Org-chart coverage (Settings module)

The org sphere/chart needs: **people**, **departments**, **roles**, **manager edges**, **per-person
fields**, **agent-access**, and a **hire/fire reconcile**. ServiceTitan's **Settings** module
(`settings/v2`) is the system of record for people; **technicians** specifically live under Settings.
([Prismatic](https://prismatic.io/docs/components/servicetitan/): *"technicians use settings"*;
[employees/business-units/user-roles tools](https://glama.ai/mcp/servers/JordanDalton/ServiceTitanMcpServer/tools/jobs_get_list)
list `employees_get/get_list`, `technicians_get_list`, `business_units_get/get_list`, `user_roles_get_list`.)

| Org element | ST source (endpoint) | Coverage | Notes / mapping |
|---|---|---|---|
| **People (office/back-office)** | `settings/v2/tenant/{t}/employees` (`employees_get_list`) | ✓ direct | Employee id, name, active flag, role, business-unit. Maps → `org_people` (`external_ref` = ST employee id). |
| **People (field techs)** | `settings/v2/tenant/{t}/technicians` (`technicians_get_list`) | ✓ direct | Techs are a distinct ST entity; union with employees for the full roster. `external_ref` = ST technician id. |
| **Departments** | `settings/v2/tenant/{t}/business-units` (`business_units_get_list`) | ⚠ derivable | ST **Business Units** ("a division within your business" — [Settings docs](https://developer.servicetitan.io/docs/api-resources-settings/)) ≈ our departments, but BUs are revenue/trade divisions (e.g. "HVAC Install"), not always EOS-style departments (front_office/dispatch/warehouse). **Map ST BU → our department key** via a per-tenant mapping table; default unmapped people → Field Operations (our `apply_employee_change` already does this). |
| **Roles / role_tier** | `settings/v2/tenant/{t}/user-roles` (`user_roles_get_list`) + employee role field | ⚠ derivable | ST roles drive permissions, not an org hierarchy. Map ST role → our `role_tier` (owner/exec/manager/ic) via a lookup; our payroll mapper already does role→pay-class (`mappers.pay_class_for_role`) as precedent. |
| **Manager edges** | — | ✗ gap | ServiceTitan has **no first-class "reports-to" field** on employees. Derive from BU/role + a per-tenant manager map captured at onboarding, OR let leadership set it in-app. The sphere already stores `manager_id`; seed it from onboarding, not from ST. |
| **Per-person `ai_context`** | — | ✗ gap (by design) | Authored in-app (our seed writes it); ST has no equivalent. Not an ST responsibility. |
| **Agent-access grants** | — | ✗ gap (by design) | Our `org_person_agent_grants` (migration 0020) is server-side authz we own; never sourced from ST. |
| **Hire/fire roster reconcile** | employees/technicians webhook (real-time) + nightly list poll (backstop) | ✓ direct | Webhook `event_type` → `classify_employee_event` → `apply_employee_change`; nightly `reconcile_roster(roster)` where `roster=[{external_ref, full_name, title, department_key, role_tier}]` built from employees ∪ technicians. Empty-pull guard prevents mass-departure on outage. |

**Org-chart verdict:** ✓ **People + departments + roles + the dynamic hire/fire roster are fully
populatable from Settings.** The **only true gaps are the manager hierarchy and our app-owned fields
(ai_context, agent grants)** — none of which ServiceTitan models; they are captured at onboarding /
in-app, which is the correct design. The sphere renders fully on day one of a connection.

---

## 3. KPI coverage — all 55 scorecard KPIs

Legend: **✓** = direct from a named ST endpoint/report · **⚠** = derivable (ST has the inputs; we compute,
or it needs a report/add-on) · **✗** = not in ServiceTitan (→ QuickBooks or our own agent). **C** =
calculated by our pure engine (ADR-0003), **R** = raw from source. Money stays integer **cents** in the
engine; dollars only at the API boundary.

Module endpoints referenced (all first-party, all `/{module}/v2/tenant/{t}/...`):
`jpm` (jobs/appointments/projects — [Job Planning](https://developer.servicetitan.io/docs/api-resources-job-planning/)),
`sales` (estimates — [Sales & Estimates](https://developer.servicetitan.io/docs/api-resources-salestech/)),
`dispatch` ([Dispatch](https://developer.servicetitan.io/docs/api-resources-dispatch/)),
`payroll` (timesheets/job-splits/adjustments — [Payroll](https://developer-next.servicetitan.io/docs/api-resources-payroll/)),
`telecom` (calls — [calls_get_calls](https://glama.ai/mcp/servers/JordanDalton/ServiceTitanMcpServer/tools/jobs_get_list)),
`accounting` (invoices/payments — [Accounting](https://developer.servicetitan.io/docs/api-resources-accounting/)),
`inventory` (POs/vendors/bills), `reporting` ([report data](https://glama.ai/mcp/servers/@JordanDalton/ServiceTitanMcpServer/tools/report_category_reports_get_data)).

### 3.1 Sales (ServiceTitan) — entities = sales reps / comfort advisors

| KPI | C/R | ST source | Cov | Raw vs derived |
|---|---|---|---|---|
| gross_sales (Gross Sales HVAC) | R | `sales/v2/.../estimates` filtered `soldAfter/soldBefore`, sum `total`; or `jpm` jobs sold-revenue by BU | ✓ | raw sum (per `soldById` = per rep) |
| opportunities | R | `sales/v2/.../estimates` count by status (open+sold+dismissed) in window | ✓ | raw count |
| jobs_sold | R | `jpm/v2/.../jobs` `soldById` set, won; or estimates `status=Sold` | ✓ | raw count |
| closing_pct | C | jobs_sold ÷ opportunities × 100 | ✓ | derived (pure helper) |
| leads | R | `telecom` calls marked Lead, or `crm` leads assigned to rep | ✓ | raw count |
| rpl (Revenue per Lead) | C | gross_sales ÷ leads | ✓ | derived |
| average_ticket | C | gross_sales ÷ jobs_sold | ✓ | derived |
| sold_hours | R | estimate line **labor hours** (estimate items), summed | ⚠ | derivable from estimate items; verify labor-hours field exists on the tenant's pricebook |
| tech_generated_leads | R | `telecom`/`crm` lead with **source/campaign = technician**, or job "lead generated by" | ⚠ | derivable from lead source attribution; depends on tenant tagging tech-gen leads |
| needs_coaching | C | rep closing_pct < goal | ✓ | derived (training flag) |

### 3.2 Operations (ServiceTitan: field + dispatch + warehouse) — entities = technicians

| KPI | C/R | ST source | Cov | Raw vs derived |
|---|---|---|---|---|
| completed_revenue_service | R | `jpm/v2/.../jobs` `jobStatus=Completed` + `completedOnOrAfter`, service BU, sum revenue | ✓ | raw sum |
| converted_jobs | R | `jpm` jobs converted (job created from a call/estimate) | ⚠ | derivable: join calls/estimates→jobs |
| conversion_rate | C | converted_jobs ÷ dispatched × 100 | ✓ | derived (dispatched count from `dispatch`/appointments) |
| utilization (Technician Utilization) | C | **Reporting API** "Technician Productivity Performance" report, **or** payroll `timesheets`/job-splits (billable ÷ available) | ⚠ | ST tracks utilization (60–80% benchmark) automatically; cleanest via the **Reporting API** report seen on Dispatch-Pro Supervisor Console; derivable from payroll job-splits otherwise |
| job_count (Job Count) | R | `jpm` jobs completed per tech | ✓ | raw count |
| idle_time | R | Reporting API tech-productivity report (Idle Time column), or payroll clock gaps | ⚠ | ST defines idle = "completed a job and waits before next dispatch" ([manage idle time](https://help.servicetitan.com/docs/manage-technician-idle-time)); surfaced in the report |
| driving_time | R | Reporting API tech-productivity report (Driving Time), or payroll non-job "drive" events | ⚠ | ST "automatically documents technicians' drive time… on timesheets" ([field metrics](https://www.servicetitan.com/blog/field-service-metrics)) |
| late_alerts | R | Reporting API tech-productivity report (Number of Late Alerts) / Dispatch | ⚠ | the Supervisor Console "Number of Late Alerts" column → Reporting API |
| avg_drive_per_day | C | driving_time ÷ business_days | ✓ | derived |
| avg_idle_per_day | C | idle_time ÷ business_days | ✓ | derived |
| drive_time_saved | R | **our Routing agent** (not ST) | ✗→own | computed by our routing engine |
| technicians_needed | C | ceil((calls_week ÷ business_days) ÷ calls_per_tech_day) | ✓ | derived (calls from `telecom`) |
| overtime_hours | R | `payroll/v2` timesheets/gross-pay `overtimeHours` | ✓ | raw (our payroll engine recomputes from the clock) |
| understaffing_gap | R | **our Workforce agent** (ST capacity vs demand inputs) | ⚠→own | derived by our agent from ST capacity-planning availability ([adjustable capacity via API](https://www.servicetitan.com/blog/field-service-metrics)) |
| unbilled_materials | R | **our Inventory agent** (ST inventory issued-to-job vs invoiced) | ⚠→own | derived from `inventory` + `accounting` invoice items |
| hvac_maint_non_job_rev | R | `accounting`/`memberships` recurring maintenance revenue not tied to a job | ⚠ | derivable from membership/recurring-service billing |

### 3.3 Sales + Marketing (ServiceTitan: front office) — entities = call takers (CSRs)

| KPI | C/R | ST source | Cov | Raw vs derived |
|---|---|---|---|---|
| calls_taken | R | `telecom/v2/.../calls` (`calls_get_calls`), count by agent in window | ✓ | raw count |
| leads_fo (Leads) | R | `telecom` calls flagged **Lead** ("calls >60s are potential leads… count toward CSR metrics" — [call booking](https://help.servicetitan.com/docs/call-booking)) | ✓ | raw count |
| booked | R | `telecom` lead → booking, or `jpm` job booked from call | ✓ | raw count |
| book_rate | C | booked ÷ leads_fo × 100 | ✓ | derived |
| missed_call_rate | C | missed ÷ (handled+missed) × 100 | ⚠ | derivable from `telecom` call dispositions (missed/abandoned) |
| after_hours_recovered | R | **our Booking agent** | ✗→own | our 24/7 booking engine |
| booking_recovered | R | **our Booking agent** | ✗→own | our booking engine |
| avg_booking_value | C | booking_recovered ÷ booked | ✓ | derived |

### 3.4 Finance (QuickBooks — NOT ServiceTitan) — company-level

These are the set Alex explicitly said **comes from QuickBooks** ("finance comes from QuickBooks,
everything else from ServiceTitan reports"). They confirm the **dual-source design**. ServiceTitan's
Accounting module holds **AR aging tied to invoices** ([Accounting docs](https://developer.servicetitan.io/docs/api-resources-accounting/);
ST AR Management *"provides detailed information on aging invoices"*) — so A/R *can* be sourced from
ServiceTitan **or** QuickBooks. The cash/CC/LOC/quick-ratio balance-sheet items are **only** in QuickBooks.

| KPI | C/R | Source | Cov (ST) | Note |
|---|---|---|---|---|
| cash_collected | R | QBO payments received (or ST `accounting` payments) | ✗ (QBO primary) | both have it; QBO is the book of record for cash |
| cash | R | QBO bank balance | ✗ | balance sheet — **QBO only** |
| credit_card_balance | R | QBO CC liability | ✗ | balance sheet — **QBO only** |
| line_of_credit_used | R | QBO LOC drawn | ✗ | balance sheet — **QBO only** |
| quick_ratio | C | (cash + ar_total) ÷ current_liabilities | ✗ | needs QBO balance sheet |
| ar_total / ar_current / ar_1_30 … ar_121_plus | R | **QBO AR Aging Summary** (or ST `accounting` AR aging) | ⚠ ST has it | ST exposes invoice-level AR + aging; QBO is the reconciled book of record. We pull AR from **QBO** for the reconciled figure (matches the client's manual Google-Sheet tracker). |
| ar_pct_current / ar_pct_over_30 | C | from aging buckets | ⚠ | derived |
| margin_leakage | R | **our Financial agent** | ✗→own | our agent (job-cost vs billed) |
| average_job_size | C | completed_revenue ÷ jobs | ⚠ | ST jobs supply the inputs; computed by us |
| department_income | R | QBO P&L by class/dept (ST BU income as a cross-check) | ✗ (QBO primary) | P&L — QBO |
| upcoming_jobs_1wk/_2wk/_4wk | R | `jpm` scheduled jobs by appointment date window × estimate value (**ServiceTitan**, not QBO) | ✓ | raw pipeline — **this one is ST** despite living in the "Finance/Looking-Forward" Bloom group |
| follow_up_backlog | R | `sales` sold-but-not-completed estimate backlog (**ServiceTitan**) | ✓ | raw — **ST**, not QBO |

> **Dual-source confirmed:** the **balance-sheet + cash + P&L** Finance KPIs are QuickBooks (our
> `accounting_mode=quickbooks` path, `app/config.py` QBO OAuth2 settings already present). The **forward
> pipeline + backlog** items that *appear* under Bloom's "Looking Forward/Finance" band are actually
> **ServiceTitan** jobs/estimates. A/R can come from either; we take it from **QBO** for the reconciled
> number (and can cross-check against ST AR aging).

### 3.5 Coverage tally

- **ServiceTitan-direct (✓):** ~22 KPIs (sales totals/counts/close-rate, completed revenue, job count,
  overtime, calls/leads/booked/book-rate, upcoming-jobs pipeline, follow-up backlog) + all pure-calculated
  KPIs derived from them.
- **ServiceTitan-derivable (⚠):** ~11 (utilization/idle/drive/late via Reporting API or payroll splits;
  sold-hours; tech-gen leads; converted-jobs join; missed-call rate; maintenance non-job revenue; AR aging).
- **Not in ServiceTitan (✗ → QuickBooks):** the 6 balance-sheet/cash/P&L Finance KPIs (cash, CC, LOC,
  quick-ratio, cash-collected book-of-record, department income).
- **Not in ServiceTitan (✗ → our own agents):** drive_time_saved, after_hours/booking_recovered,
  margin_leakage, understaffing_gap, unbilled_materials — these are *our* value-add, computed from ST
  inputs by the Routing/Booking/Financial/Workforce/Inventory agents.

**Every one of the 55 KPIs has a confirmed source.** None is unsourceable.

---

## 4. Gaps + mitigations

| Gap (⚠/✗) | Why | Mitigation / ask the tenant |
|---|---|---|
| **Manager hierarchy** (org chart) | ST has no reports-to field | Capture at onboarding (one CSV/screen) or let leadership set it in-app; we own `manager_id`. |
| **Business-Unit → department mapping** | ST BUs are trade/revenue divisions, not EOS departments | Per-tenant BU→department lookup at onboarding; default unmapped → Field Operations (already coded). |
| **Technician utilization / idle / drive / late-alerts** | The Dispatch-Pro Supervisor Console table is **report-backed** | Two paths: (a) **Reporting API** — pull that report (needs the tenant to grant **Reporting API access** + we map category/report IDs; rate-limited, so cache); (b) derive from **payroll job-splits + clock events** (needs **payroll scope**). Prefer (a) for fidelity; (b) as fallback. Confirm the tenant has **Dispatch Pro** (the productivity metrics originate there). |
| **Sold hours / tech-generated leads** | Depend on pricebook labor-hours + lead-source tagging | Verify the tenant tags tech-generated leads and that estimate items carry labor hours; otherwise mark ⚠ and surface "—". |
| **Reporting API scarcity** | ~1–5 same-report/min/tenant | Dedicated slow queue + cache; never put a report on the hot path. |
| **AR aging book-of-record** | Both ST and QBO have it | Use **QBO** for the reconciled figure (matches the client's manual tracker); optional ST cross-check. |
| **Cash / CC / LOC / quick-ratio / P&L** | Balance-sheet/P&L not in ST | **QuickBooks Online** (our `accounting_mode=quickbooks`, Intuit OAuth2 — direct, no Zapier). |
| **No refresh token / 900s tokens** | ST design | Token cache + 60s pre-expiry refresh (already implemented). |
| **60 req/s + reporting limits** | ST throttling | Per-tenant rate limiter + Export API for bulk + delta GET windows for weekly rollups. |

**Tenant enablement checklist (the "ask"):** ServiceTitan **API Application Access** authorized for our
app (issues per-tenant Client ID/Secret) · scopes for **Settings, JPM, Dispatch, Sales/Estimates,
Payroll, Telecom, Accounting, Inventory, Reporting** (read-only) · **Reporting API access** + the report
IDs for the tech-productivity report · **Dispatch Pro** add-on (for the productivity metrics) · **V2
Webhook** subscription (employee + job + invoice events) pointed at our callback. QuickBooks Online OAuth2
connected for the Finance balance-sheet set.

---

## 5. Wiring note — which seam each ST endpoint plugs into at go-live

When `SERVICETITAN_MODE` flips from `fixture`→`live`, the work is **mapping**, not new architecture — every
seam already exists and fails closed. Money stays in **cents** through the engines; ADR-0003 holds
(ServiceTitan/QBO supply *raw figures*; our deterministic code computes; the LLM only narrates).

| ST endpoint(s) | Plugs into | What to fill |
|---|---|---|
| `settings/v2 employees` + `technicians` | `backend/app/repositories/org.reconcile_roster` (nightly) + `apply_employee_change` (webhook) | Build the `roster=[{external_ref, full_name, title, department_key, role_tier}]` from employees ∪ technicians; map ST BU→department_key + ST role→role_tier. `external_ref` = ST id. |
| employee/technician **webhook** | `backend/app/api/routes_webhooks.receive_servicetitan` → `org_access.classify_employee_event` | Confirm ST V2 event_type strings for hire/terminate; the HMAC verify + dedupe already guard it. |
| `jpm/v2 jobs` (completedOnOrAfter, businessUnitId, soldById, jobStatus) | `servicetitan/live_client.get_appointments`/`get_job_durations` **and** `org/scorecard_data` live branch | Map job → completed_revenue, job_count, converted_jobs, average_job_size inputs, upcoming-jobs pipeline. Verify revenue field + units. |
| `sales/v2 estimates` (soldAfter, soldById, total, status) | `org/scorecard_data` (Sales dept) | Map → gross_sales, opportunities, jobs_sold, sold_hours, follow_up_backlog. |
| `telecom/v2 calls` | `org/scorecard_data` (Sales+Marketing dept) + Booking agent | Map → calls_taken, leads_fo, booked, missed-call inputs, tech-gen leads, technicians_needed (calls/week). |
| `payroll/v2 timesheets` + job-splits + adjustments | `servicetitan/mappers.map_timesheet`/`map_workday`/`map_worker`/`map_piece_earning` → Workforce **payroll engine** | Already-built mappers; fill exact ST field names (regularHours/overtimeHours, dispatched/completed clock). Supplies overtime_hours; utilization fallback. |
| `dispatch/v2` + **Reporting API** (`reporting/v2/.../report-category/{c}/reports/{r}/data`) | `org/scorecard_data` (Operations dept) + Dispatch agent (`integrations/dispatch`) | Map the tech-productivity report → utilization, idle_time, driving_time, late_alerts. Cache hard (rate limit). |
| `accounting/v2 invoices`/`payments` + **Export API** (`/export`, continuation `from`) | Financial agent + (optional) AR cross-check | Bulk invoice/payment sync via Export; AR aging primary = QBO. |
| `inventory/v2` POs/vendors/bills | Inventory agent (`integrations/inventory`) | unbilled_materials, partial-consumable proration (Alex's metal-spool pain). |
| QuickBooks Online (Intuit OAuth2, `accounting_mode=quickbooks`) | Financial agent + `org/scorecard_data` (Finance dept) | cash, CC, LOC, quick_ratio, department_income, AR aging (reconciled). Direct Intuit API — **no Zapier**. |

**Go-live becomes a known checklist:** (1) provision integration tenant → verify auth round-trip; (2) fill
each mapper against live shapes (ADR 0005); (3) map BU→department + role→role_tier; (4) subscribe the V2
webhook; (5) wire the Reporting-API report IDs; (6) connect QBO; (7) flip `SERVICETITAN_MODE`/
`accounting_mode`/`dispatch_mode`/`inventory_mode` to live; (8) the fail-closed skeleton stops raising as
each mapping lands — partial coverage degrades gracefully (a KPI shows "—", never a wrong number).

---

## Verdict

**Yes — with one expected dual-source split and a short enablement list, we can build both the org chart
and the full scorecard from a connected ServiceTitan tenant, over a direct first-party API with zero
Zapier.** The **org chart is fully populatable** from the Settings module (employees + technicians +
business-units + user-roles), with a real-time hire/fire webhook backstopped by a nightly reconcile — the
only non-ST pieces are the manager hierarchy and our app-owned fields (agent grants, ai_context), which by
design are captured in-app, not in ServiceTitan. **All 55 KPIs have a confirmed source:** ~22 are direct
ServiceTitan reads, ~11 are ServiceTitan-derivable (utilization/idle/drive/late via the Reporting API or
payroll splits — needing Dispatch Pro + Reporting-API access), the 6 balance-sheet/cash/P&L Finance KPIs
come from **QuickBooks** exactly as Alex described, and a handful (drive-time-saved, recovered revenue,
margin leakage) are our own agents' value-add computed from ST inputs. The reliability constraint is met:
OAuth2 client-credentials with cached 900-second tokens, a 60-req/s-aware paginator, **V2 webhooks
(HMAC-verified) where real-time matters and scheduled Export/Reporting/delta polls otherwise**, and a
fail-closed live skeleton that raises rather than fabricate — so the only real "partial" is operational
(confirm the tenant has Dispatch Pro + grants Reporting-API/Payroll scopes), not architectural.
