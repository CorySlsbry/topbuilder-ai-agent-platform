# Alex Demo — seeded enterprise org + department-scoped logins (SHIPPED)

> **2026-06-11 UPDATE — recipient corrected from Zach to ALEX (person1@example.com, the
> CPA-channel partner).** Shipped on top of the original build (commit 78ee33e; api rev 00011-92h,
> web rev 00008-qlq): owner persona renamed to Alex (zach@ fixture deleted; alex@ live, analyst,
> unrestricted, person-linked a5aa0cc3-…); **Executive view** (`/v1/org/kpis`, executive-only 403
> for dept-scoped logins; pure `app/org/kpis.py` aggregation over each agent's latest persisted
> run — verified live: total $143,558 = 3,260+2,895+119,700+14,783+2,920, echarts bar+donut,
> AI coverage 7/7); **View-As control** (`/v1/org/access-matrix`; unrestricted operators simulate
> any employee's exact view — verified live: Ray Delgado collapses nav to Organization+Dispatch,
> Exit restores); smoke renamed `smoke_alex_demo.py` (ALL GREEN on the deployed services);
> 355 pure tests. Cory's "see what Alex sees" path: Canyon Ridge demo tile (or any unrestricted
> login) → **View as** → pick the person.

> Written 2026-06-11 BEFORE building (compaction-proof checkpoint). If a session resumes cold:
> this is the single source of truth for the build. Pattern source: the `enterprise-level` skill
> (Fowler enterprise-brain blueprint) — org model as data, job-level permissions enforced at the
> data layer, radial Organization Brain UI, person-context, department-scoped agents.

## Goal

Zach logs in at the live dashboard (https://topbuilder-ai-agent-web-840472456279.us-central1.run.app)
with his own credentials and sees a fully-seeded 25–50-employee ServiceTitan contractor running on
Top Builder AI: an **Organization Brain** view (radial graph: company → departments → people →
agents), all six agents with live fixture data, and **department-restricted demo logins** that prove
job-level permissions (a dispatcher literally cannot reach the Financial agent — 403 at the API,
hidden in the UI).

## The demo company

- **Tenant:** `33333333-3333-3333-3333-333333333333`, slug `canyonridge`, name **Canyon Ridge
  Mechanical** — 38 employees, HVAC + plumbing + electrical, runs on ServiceTitan
  (`tenant_settings.fsm_provider = 'servicetitan'`). Added to `DEMO_TENANTS` in `app/demo.py`.
- **Departments (7) — color drives ALL UI coding (graph, nav chips, profile):**

| key | name | color | headcount |
|---|---|---|---|
| leadership | Leadership | #f59e0b | 3 |
| front_office | Front Office | #38bdf8 | 5 |
| dispatch | Dispatch | #a78bfa | 3 |
| field | Field Operations | #34d399 | 18 |
| sales | Sales | #fb7185 | 3 |
| finance | Finance & Accounting | #818cf8 | 3 |
| warehouse | Warehouse & Inventory | #fb923c | 3 |

- **Roster (38):** Leadership: Zach (Owner / CEO, role_tier `owner`), Marcus Reed (GM, `exec`),
  Elena Vasquez (Ops Manager, `exec`). Front Office: Tanya Brooks (Office Manager, `manager`) + 4
  CSRs (`ic`). Dispatch: Ray Delgado (Dispatch Manager, `manager`) + 2 dispatchers. Field: Cole
  Barrett (Field Supervisor, `manager`); HVAC lead + 7 techs; Plumbing lead + 4; Electrical lead +
  3. Sales: Dana Royce (Sales Manager, `manager`) + 2 comfort advisors. Finance: Priya Shah
  (Controller, `manager`), bookkeeper, payroll admin. Warehouse: Gus Romero (Warehouse Manager,
  `manager`) + 2 inventory clerks. Manager edges: everyone → their dept manager → GM → Zach.
  Each person gets a 1–2 sentence `ai_context` written FOR the AI (how they work / what they need).

## Permission model (4 layers, enforced server-side — never prompt-only)

- **Dept → agents map** (pure code, `app/org/permissions.py`):
  - leadership → ALL 6 (workforce, financial, inventory, booking, routing, documents) + all sections
  - front_office → booking, documents (+ frontdesk section)
  - dispatch → routing (+ dispatch section)
  - field → workforce
  - sales → booking
  - finance → financial, documents
  - warehouse → inventory
- `user_memberships` gains `department text NULL` + `person_id uuid NULL` (NULL department =
  executive/full view). `Principal` gains `department`. Platform roles unchanged (admin = operator
  w/ 2FA; analyst = can run; viewer = read-only).
- **Enforcement:** dependency `require_agent_access(<agent>)` on every per-agent run/latest route →
  403 `department '<d>' does not include the <a> agent` when out of scope. Admin + dev-token
  principals (no department) = unrestricted. UI additionally hides disallowed sections (UX, not the
  enforcement).
- `/auth/me` returns `department`, `allowed_agents` (null = all), `person {id, full_name, title,
  department_key}`.

## Org data layer

- **Migration `0015_org_brain.sql`:** `org_departments` (id, tenant_id, key, name, color, sort) +
  `org_people` (id, tenant_id, department_id FK, full_name, title, role_tier
  owner|exec|manager|ic, manager_id self-FK, email, ai_context, sort) — both RLS FORCE with the
  standard fail-closed tenant policy. ALTER `user_memberships` ADD department + person_id. INSERT
  canyonridge into `tenants` + `tenant_settings` (servicetitan).
- **Roster single source of truth = `app/org/seed.py`** (pure data). Seed-on-read (the existing
  comms/tasks pattern): GET /v1/org/overview seeds the roster idempotently for demo tenants when
  `org_people` is empty for the tenant. No 38-row hand-written SQL.
- **API `routes_org.py`:** `GET /v1/org/overview` → {company, departments[+head_count],
  people[id,name,title,dept_key,role_tier,manager_id], agents[key,label,dept_keys,description],
  caller_access}; `GET /v1/org/people/{id}` → profile (person, manager, direct_reports,
  allowed_agents, ai_context, not_accessible). Registered in `app/main.py`.

## Frontend (Command Center)

- **New section `organization`** (top of Command group): `components/OrgBrainView.tsx` — the wow
  screen. Left explorer panel: entity counts (People 38 · Departments 7 · AI Agents 6), dept legend
  (color dots), search. Center: **precomputed radial SVG** (NO force layout): company node center →
  7 dept hubs on ring 1 (angular sectors) → people as initial-avatars on ring 2 within their sector
  → the 6 agents as rounded squares positioned at their owning dept. Hover = tooltip; click person =
  side profile panel with tabs **Overview / AI Access / AI Context**; click agent = agent card +
  which depts it serves; selected node dims non-neighbors. Identical layout every load.
- **Nav filtering:** when `me.department` set → only allowed sections render; signed-in chip shows
  person name + dept color chip. TENANTS dev-switcher gains canyonridge.

## Demo logins (Supabase auth users — invite pattern: pre-confirmed, token cols '')

| email | role | department | person link | sees |
|---|---|---|---|---|
| zach@topbuilderai.com | analyst | NULL (executive) | Zach (Owner/CEO) | everything incl. Org Brain |
| dispatch.demo@topbuilderai.com | analyst | dispatch | Ray Delgado | Dispatch/Routing only |
| frontdesk.demo@topbuilderai.com | analyst | front_office | Tanya Brooks | Front Desk + Booking + Documents |
| finance.demo@topbuilderai.com | analyst | finance | Priya Shah | Financial + Documents |

Passwords: generated random, set via SQL bcrypt (`crypt(pw, gen_salt('bf'))`, all token columns
`''` not NULL — the GoTrue gotcha), reported to Cory in chat to hand to Zach. These are fixture
demo accounts on our own platform (apex/summit pattern), not real-person credentials.

## Verify (before declaring done)

1. Pure suite green (`pytest -q -m "not integration"`) incl. new oracle tests: dept-map closure,
   allowed_agents truth table, roster integrity (38 people, 7 depts, manager edges resolve, colors
   unique).
2. Apply 0015 to Supabase via MCP; deploy api + web (frontend by digest, never :latest).
3. Create the 4 auth users + memberships; pre-warm all 6 agents on canyonridge (analyst can run).
4. **Live E2E smoke via password grant** (Supabase `/auth/v1/token?grant_type=password` + anon key)
   for all 4 logins: /auth/me shape → org overview (seeds on first read) → allowed agent 200 →
   disallowed agent 403 (dispatch login vs financial agent = the money shot).
5. Update MEMORY.md + brain log with credentials location + final state.

## Status ledger (update as you go)

- [x] Spec written (this file)
- [x] Backend: migration 0015 + org module + permissions + routes + deps + tests
- [x] Frontend: OrgBrainView + nav filtering + me wiring (org-linked logins land on Organization)
- [x] Pure suite green — 343 passed (320 baseline + 23 org oracles, 0 regressions)
- [x] Supabase migrated (0015) + deployed by digest: api rev 00010-ljn, web rev 00007-vmg (commit adb4734)
- [x] Auth users + memberships created (4, confirmed + person-linked) + all 6 agents prewarmed 201 on canyonridge
- [x] Live E2E smoke ALL GREEN (backend/scripts/smoke_zach_demo.py --prewarm): 4 logins, me shapes exact,
      org overview 38/7/6 for every login, allowed agents 200, cross-department 403s
      (dispatch→financial, front_office→financial, finance→routing)
- [x] Deployed UI verified in the browser: Org Brain renders (38 people, 7 sectors, 6 agents, profile
      panel w/ AI Access tab); dispatch.demo login shows "Ray Delgado · Dispatch Manager" + nav filtered
      to Organization + Dispatch only, lands on Organization
- [x] Memory + brain updated; committed + pushed (passwords reported to Cory in chat — not stored here)
