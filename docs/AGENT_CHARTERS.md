# Agent Charters — internal source of truth

One charter per agent. A charter is the code-grounded, single-page answer to "what is this agent,
who approves it, and how far along is it really" — derived from the actual routers, engines,
permission tables, and adapters, not from marketing copy. **These charters are deliberately honest:
they state fixture-only status, unmapped reads, and open bugs plainly. When editing, never soften a
gap.** The public page (`landing/agents.html`) is derived from these and must never claim more than
the "Platform coverage" line of the corresponding charter.

## What each field means

- **Mission** — the one-sentence job, in outcome terms.
- **Department + approver** — where the agent sits in `DEPT_AGENTS` and who approves its gated
  actions under the per-employee lead-approval model (migration 0026: `role='lead'`,
  `require_lead_or_admin`, dept-scoped My Approvals inbox; money/legal kinds are lead-required,
  approve/execute requires 2FA aal2). Operator agents sit outside `DEPT_AGENTS` entirely and are
  gated on `require_admin` + `PLATFORM_OPERATOR_EMAILS`.
- **Inputs** — adapters, `*_MODE` flags, and inbound sync events (ADR 0010 event-detection spine).
- **Deterministic outputs** — figures from pure, tested code (ADR 0003 firewall); the LLM only
  narrates and can never compute a number.
- **Gated actions + ALWAYS_HITL** — action kinds owned via `KIND_OWNER`, flowing through the ADR
  0007 propose → approve → execute gate. ALWAYS_HITL kinds queue for a human lead even when the
  agent's autonomy is `auto`.
- **Autonomy default** — per-agent `off|hitl|auto`; a missing policy row resolves to `hitl`;
  the master switch `ACTIONS_ENABLED` is OFF in the public demo.
- **KPIs** — what "working" looks like, measurably.
- **What it learns** — the CBR case bank + CIPHER preference distillation (ADR 0008),
  narration-side only; distilled rules are quorum-gated candidates that must pass the golden-set
  eval gate and human approval, then roll out behind a canary %.
- **Platform coverage (honest)** — demo-ready vs connect-ready vs live, per platform
  (ServiceTitan / QuickBooks / Procore / Buildertrend). This line is the ceiling for all sales copy.

## Summary

| Agent | Department | Approver | Gated kinds | Autonomy default | Platform coverage |
|---|---|---|---|---|---|
| Workforce | field | field lead/admin, 2FA | `payroll_adjustment` (ALWAYS_HITL) | hitl | ST demo-ready; only appointments+timesheets live-mapped; Procore/BT jobs-model demo only |
| Financial | finance | finance lead/admin, 2FA | none self-proposed; receives `create_ap_draft` (ALWAYS_HITL, owner=documents) | hitl | QBO nearest-to-live (3/5 reads real); `get_jobs`/`get_payment_velocity` best-effort so live runs complete; ST/Procore/BT fixture |
| Inventory | warehouse | N/A (advisory) | none | N/A (advisory) | ST fixture-only (5/5 reads unmapped); NO Procore/BT inventory domain |
| Booking (24/7) | front_office + sales | any front-office/sales approver | `book_appointment`, `create_estimate` (auto-eligible with undo) | hitl (auto designed safe) | ST-only; live intake 4/4 unmapped; no construction intake domain |
| Routing / Dispatch | dispatch | N/A (advisory) | none | N/A (advisory) | ST fixture; Procore/BT jobs-model demo; no live feed anywhere |
| Documents | front_office + finance | dept lead/admin, 2FA | `file_document`, `request_signature` (auto-eligible); `create_ap_draft`, `register_warranty` (ALWAYS_HITL) | hitl (academic — nothing proposes its kinds yet) | ST fixture (best-effort lanes); Procore/BT declared, mappers raise |
| Collections | front_office + finance | dept LEAD or admin only, 2FA | `send_dunning_email`, `send_dunning_sms`, `place_dunning_call` (ALL ALWAYS_HITL) | hitl (effectively permanent for its kinds) | fixture-only everywhere; live client unbuilt; QBO the natural first source |
| Pricebook | finance + warehouse | finance/warehouse lead/admin, 2FA | `update_pricebook_item` (ALWAYS_HITL) | hitl (permanent for its kind) | price-file upload LIVE today (platform-independent); ST reads/write unmapped; no Procore/BT pricebook domain |
| Email (operator) | platform operator | operator (admin + 2FA) | `delete_emails`, `send_email_reply`, `rewrite_workflow`, `send_outreach_email` (operator-gated, none ALWAYS_HITL) | hitl behind operator gate | N/A to field platforms; inbox fixture; Resend built, blocked on API key |
| SEO (operator) | platform operator | operator (admin + 2FA) | `publish_blog_post`, `post_comment` (operator-gated) | hitl behind operator gate | N/A to field platforms; publishing executors fixture-fenced |
| Ads (operator) | platform operator | operator, 2FA | `ads.create_campaign`, `ads.update_budget`, `ads.activate_campaign` (ALWAYS_HITL) + `ads.pause_campaign`, `ads.sync_conversion` (auto-eligible) | hitl behind double operator gate | N/A to field platforms; fixture-only; no live ad account |

---

## Tenant agents

### Workforce Agent

- **Mission:** Prevent understaffing and avoidable overtime by converting timesheet, capacity, and
  demand data into deterministic staffing, OT-mitigation, and payroll-accuracy recommendations.
- **Department:** field (`DEPT_AGENTS: field={workforce}`; leadership sees all agents).
- **Approver:** Field department lead or tenant admin, 2FA (aal2) required to approve/execute.
  `payroll_adjustment` is ALWAYS_HITL — a plain in-department analyst can propose but only a
  lead/admin approves. Lands in the lead's My Approvals inbox.
- **Inputs:** ServiceTitan appointments + timesheets (the ONLY two live-mapped ST reads; OAuth2
  client-credentials + hasMore/continueFrom paginator verified), technicians / trade-economics /
  job-durations / demand-signals (fixture-only, live raises NotImplementedError). Sync events in
  (ADR 0010, advisory): `timesheet`, `gross_pay_item`, `payroll_adjustment`.
- **Deterministic outputs:** Per-trade-week understaffing gaps (booked-hours-x-demand vs capacity;
  technician-weeks to close; `economic_impact_cents`), per-tech OT projections with avoidable
  premium in cents, same-trade mitigation candidates (<90% slack), trade utilization, BC ESA / CA
  payroll (8-12h=1.5x, >12h=2x, weekly>40=1.5x no pyramiding; hourly/piece-rate/commission
  classes), claimed-vs-clocked payroll-gap flags, recency-weighted (60d half-life) per-(tech,
  job-type) duration model. Every analysis carries a SHA-256 `inputs_hash` (replayable audit).
- **Gated actions:** `payroll_adjustment` — ALWAYS_HITL (writes someone's pay). The live branch
  builds the real ServiceTitan `POST /payroll/v2/.../payroll-adjustments` body (mapping proven in
  `payroll_writeback.py` tests) then fails closed — the send itself is unwired.
- **Autonomy default:** hitl (missing policy row = hitl; per-agent `off|hitl|auto`). Master switch
  `ACTIONS_ENABLED` is OFF in the public demo. Even in auto mode, payroll writes only QUEUE for a
  lead — never self-execute.
- **KPIs:** Avoidable OT premium $ flagged per pay period; understaffing economic impact $ surfaced
  per trade-week; claimed-vs-clocked payroll-gap $ caught before payroll runs; % of payroll
  adjustments approved without edit.
- **What it learns:** CBR case bank + CIPHER preference distillation from lead approvals, edits,
  and rejections — narration-side only (ADR-0003 firewall: the pay math is untouchable). Distilled
  rules are quorum-gated candidates that must pass the golden-set eval gate and human approval,
  then roll out behind a canary %.
- **Platform coverage (honest):** ServiceTitan: demo-ready on fixtures; live = auth + paginator +
  appointments/timesheets reads verified, but the four figure-bearing reads (technicians, trade
  economics, job durations, demand signals) are unmapped and fail closed — no end-to-end live ST
  run yet. Procore/Buildertrend: jobs-domain demo on the canonical model only; every construction
  mapper raises; Buildertrend is partner-application-gated (no self-serve connect).

### Financial Agent

- **Mission:** Give the owner GAAP-correct job profitability, margin-leakage warnings, and a
  30/60/90-day cash-flow forecast computed from books data, never from an LLM.
- **Department:** finance (`DEPT_AGENTS: finance={financial, documents, collections, pricebook}`).
- **Approver:** Finance department lead or admin, 2FA. The agent itself proposes no writes;
  sync-detected bills arrive as `create_ap_draft` proposals (ALWAYS_HITL) whose authorization keys
  on the OWNING agent = documents (`KIND_OWNER`), which finance and front_office both include.
  Ownership is now consistent end to end: the sync spine stores the row as `agent=documents`
  (`app/sync/service.py` `_handle_bill`) and `router.py` routes `bill`/`purchase` to documents, so
  the stored agent, `KIND_OWNER`, the run narration, and the approvals inbox all agree.
- **Inputs:** `ACCOUNTING_MODE fixture|quickbooks`. QBO is the platform's most-live adapter:
  `get_company_financials` (BalanceSheet cash + P&L margin), `get_ar_invoices`, `get_ap_bills`
  fully implemented; `get_jobs` + `get_payment_velocity` remain unmapped for QBO but are now wrapped
  best-effort (`app/agents/financial/data.py` `_best_effort` — an absent method or a fail-closed
  raise yields [] for that lane), so a QBO-connected tenant completes a live run on the available
  lanes (cash, AR, AP) instead of crashing the whole assembly.
  Sync events in: `bill`/`purchase` (→ AP-draft proposal, the only auto-propose handler in the
  platform), `vendor_credit`, `deposit`, `journal_entry`, `vendor`, `job` (advisory).
- **Deterministic outputs:** Percentage-of-completion earned revenue, margin-to-date vs budget
  margin, profitability index, over/under-billing position per job; leakage warnings in cents
  (cost overrun >5% of budgeted-to-date, margin erosion >5pp below target); 30/60/90-day cash flow
  (AR shifted by per-segment payment velocity, AP by due date) with a confidence score; segment
  margins. All figures pure + inputs-hashed.
- **Gated actions:** None self-proposed. Receives `create_ap_draft` (ALWAYS_HITL — posts an A/P
  entry to the books) from the ADR-0010 sync spine; the spine drains under a propose-only SYSTEM
  principal that can never self-approve.
- **Autonomy default:** hitl (effectively advisory-plus-inbox: its only write path is the sync-fed
  AP draft, which is ALWAYS_HITL regardless of autonomy mode).
- **KPIs:** Margin-leakage $ flagged per month; cash-flow forecast error vs 30-day actuals; % of AP
  drafts approved without edit; hours from bill detected to AP draft approved.
- **What it learns:** CBR + CIPHER from finance-lead feedback on run narration and AP-draft edits —
  narration-only, quorum → eval gate → human approval → canary. The GAAP math never learns
  (structurally firewalled).
- **Platform coverage (honest):** QuickBooks: nearest-to-live in the entire platform — 3 of 5 reads
  real; the two unmapped methods (`get_jobs`, `get_payment_velocity`) are guarded best-effort, so a
  live run completes on cash/AR/AP rather than blocking. ServiceTitan: financial reads
  unmapped (trade economics raises). Procore: accounting domain declared but
  `get_ar_invoices`/`get_ap_bills` raise NotImplementedError; Buildertrend same, plus
  partner-gated. Honest tier everywhere except QBO: demo-ready fixtures only.

### Inventory Agent

- **Mission:** Stop stockouts, shrinkage, and unbilled materials by computing dynamic reorder
  points and exact-cents cost attribution from usage data.
- **Department:** warehouse (`DEPT_AGENTS: warehouse={inventory, pricebook}`).
- **Approver:** N/A — fully advisory by design: proposes no gated action kinds. The warehouse lead
  consumes recommendations; any resulting purchase happens in the field-management system.
- **Inputs:** `INVENTORY_MODE fixture|servicetitan` — the ST inventory client is 5/5
  NotImplementedError (fixture-only today). Sync events in (all advisory): `purchase_order`,
  `po_receipt`, `inventory_return`, `inventory_adjustment`, `inventory_transfer`.
- **Deterministic outputs:** Dynamic reorder points (usage x lead time + safety stock; recommended
  qty = 2 replenishment cycles; days-to-stockout; stockout exposure = units-short x billable price
  in cents), truck-stock shrinkage alerts (>= $50), unbilled-material revenue-at-risk,
  vendor-arbitrage annualized savings, consumable-lot cost proration across served jobs (even /
  by-usage-proxy; property-tested exact-cents invariant — allocations always sum to lot cost).
- **Gated actions:** None (zero gated kinds owned). Purely advisory.
- **Autonomy default:** N/A — advisory only; the autonomy switch has nothing to execute.
- **KPIs:** Stockout exposure $ averted (flagged before days-to-stockout hits zero); shrinkage $
  flagged per month; unbilled-material $ recovered; vendor-arbitrage $ identified annually.
- **What it learns:** CBR + CIPHER from feedback on recommendations (narration-only,
  quorum/eval/canary-governed) — the reorder and proration math is firewalled.
- **Platform coverage (honest):** ServiceTitan-only in principle and fixture-only in practice (all
  5 ST inventory reads unmapped, fail-closed). Procore and Buildertrend have NO inventory domain in
  the registry at all — this agent is unavailable on those platforms until a construction inventory
  source is defined. Charters and sales copy must not claim inventory on Procore/Buildertrend.

### Booking Agent (24/7)

- **Mission:** Qualify every intake around the clock, book the soonest matching slot, and recover
  the after-hours revenue a human front desk misses.
- **Department:** front_office + sales (`DEPT_AGENTS: front_office={booking, documents,
  collections}; sales={booking}`).
- **Approver:** Any front-office/sales approver via the Front-Desk "Approve & book" one-click
  (propose → approve → execute). `book_appointment` and `create_estimate` are deliberately NOT in
  ALWAYS_HITL — in auto mode they self-execute with a real undo/compensation executor (explicit
  ADR-0007 decision: customer-touching but reversible; money/legal kinds are not auto-eligible).
- **Inputs:** `BOOKING_INTAKE_MODE fixture|live` — the live intake client is 4/4
  NotImplementedError (fixture voice-intake only). Pricebook data feeds the field PWA quote
  builder. Sync events in (advisory): `booking`, `lead`.
- **Deterministic outputs:** Per-intake qualification (intent in {service_request,
  existing_customer}, trade served, zip in service area) + qualification score, soonest open slot
  per trade, estimated job value from per-trade averages, totals including after-hours captured and
  `recovered_revenue_cents`; custom quotes from the /field PWA (pricebook + live total + tax).
- **Gated actions:** `book_appointment` (proposed by a human from Front-Desk) and `create_estimate`
  (proposed from the field PWA quote builder) — both auto-eligible with undo, both fixture-executed
  today; live executors fail closed (never fabricate a ServiceTitan write).
- **Autonomy default:** hitl. The one agent where flipping to auto is designed to be safe:
  bookings/estimates execute with undo. `ACTIONS_ENABLED` off in the public demo.
- **KPIs:** After-hours revenue recovered $ per month; % of qualified intakes booked; median time
  from intake to booked slot; booking undo rate (should stay near zero).
- **What it learns:** CBR + CIPHER from approve/edit/undo signals on bookings and screening
  decisions — narration and screening-explanation side only, quorum/eval/canary-governed.
- **Platform coverage (honest):** ServiceTitan-only: fixture demo works end-to-end; live intake
  reads and the booking write are unmapped/fail-closed. Procore and Buildertrend registry entries
  have NO intake domain — this agent has no data source there even in principle. Honest scope:
  booking is a ServiceTitan-tenant feature until a construction intake source exists.

### Routing / Dispatch Agent

- **Mission:** Hand the dispatcher skill-correct, drive-time-optimized assignments and a
  severity-triaged call board that beats round-robin every day.
- **Department:** dispatch (`DEPT_AGENTS: dispatch={routing}`).
- **Approver:** N/A — advisory by product decision: proposes no gated kinds. The dispatcher accepts
  or overrides suggestions and acts in the field-management system.
- **Inputs:** `DISPATCH_MODE fixture|servicetitan` — the ST dispatch client is 4/4
  NotImplementedError (fixture-only). Sync events in (advisory): `appointment`.
- **Deterministic outputs:** Skill-constrained, arrival-window + shift-capacity-aware nearest-stop
  assignments (Manhattan zone distance x 3 min/unit) with drive-minutes saved vs a naive
  round-robin baseline; P1/P2/P3 keyword severity triage; revenue-weighted tech ranking (basis
  points: skill 3000 / proximity 3000 / revenue 4000); 3-day capacity-vs-booked call board.
- **Gated actions:** None. Purely advisory.
- **Autonomy default:** N/A — advisory only.
- **KPIs:** Drive-minutes saved per day vs baseline (the tested oracle: ~60 min/day); % of
  suggestions accepted by the dispatcher; P1 calls assigned within window.
- **What it learns:** CBR + CIPHER from dispatcher feedback on assignment suggestions —
  narration-only, governed lifecycle (quorum → golden-set eval → approval → canary).
- **Platform coverage (honest):** ServiceTitan: fixture demo; all live dispatch reads unmapped,
  fail-closed. Procore/Buildertrend: jobs-domain demo on the canonical model only (all construction
  mappers raise) — routing can demo on construction data but has no live feed anywhere yet.

### Documents Agent

- **Mission:** Classify, customer-match, and route every inbound document to its owning department
  and folder — flagging e-sign, expiring COIs, and anything a human must touch — and draft the A/P
  entries and warranty registrations buried in the paperwork.
- **Department:** front_office + finance (documents appears in both `DEPT_AGENTS` sets).
- **Approver:** Front-office or finance department lead/admin, 2FA. `file_document` and
  `request_signature` are approvable by any in-department approver; `create_ap_draft` and
  `register_warranty` are ALWAYS_HITL (money / acts-in-a-human-session) — lead or admin only.
  `register_warranty` additionally REFUSES at the executor without a human-established vendor login
  token (the never-sign-in rule is enforced at the write boundary, not in copy).
- **Inputs:** `DOCUMENTS_MODE fixture|servicetitan` — the ST documents client is 5/5
  NotImplementedError; data assembly is best-effort per lane, so an unmapped lane never breaks the
  core run (the same pattern the financial agent now uses for its optional lanes). Feeds: inbound
  docs, open jobs (for bill matching), installed equipment (for warranty packets).
- **Deterministic outputs:** Classification (declared type at 0.95 confidence, filename keywords at
  0.8) → customer match → department + ServiceTitan folder routing → action (file / expiring-COI
  <=30d / needs-signature / needs-human); vendor-bill → open-job match with source-based confidence
  (printed 0.92 auto >= 0.85 threshold; handwritten 0.45 → human) proposing A/P drafts;
  vendor-portal warranty registration packets; extracted dollar totals (fixture oracle: 12 docs →
  9 filed / 1 e-sign / 2 needs-human / $2,920 extracted).
- **Gated actions:** Owns 4 kinds: `file_document` + `request_signature` (auto-eligible with undo),
  `create_ap_draft` + `register_warranty` (ALWAYS_HITL). HONEST GAP: no service or frontend path
  proposes `file_document`/`request_signature`/`register_warranty` today — the auto-file story
  dead-ends at a recommendation row; only a raw `POST /v1/actions` can propose (open task: mirror
  the collections propose endpoint). `create_ap_draft` IS proposed today, by the sync spine, and it
  correctly stores `agent=documents` (matching `KIND_OWNER`), so the ownership mismatch is resolved.
- **Autonomy default:** hitl — currently academic for its own kinds since nothing proposes them;
  the sync-fed AP draft is ALWAYS_HITL regardless.
- **KPIs:** % of docs auto-filed without human touch; expiring COIs flagged >= 30 days out;
  AP-draft match precision (approved-without-edit %); $ extracted and posted per month.
- **What it learns:** CBR + CIPHER from filing corrections and AP-draft edits — routing/narration
  side only, quorum/eval/canary-governed.
- **Platform coverage (honest):** ServiceTitan: fixture demo; all 5 live document reads unmapped
  (best-effort assembly keeps runs alive). Procore/Buildertrend: documents domain is declared in
  the registry and demos on the canonical model, but every construction mapper raises; Buildertrend
  additionally partner-gated. All four write kinds fixture-only, live fails closed.

### Collections Agent

- **Mission:** Work the A/R aging worklist 24/7 — correct aging, honest workflow status per
  customer, and a compliant dunning ladder — so the owner stops financing customers interest-free.
- **Department:** front_office + finance (collections appears in both `DEPT_AGENTS` sets).
- **Approver:** Department LEAD or admin only, 2FA — all three dunning kinds are ALWAYS_HITL
  (outbound customer contact under TCPA/CASL/quiet-hours). An analyst can build the worklist; only
  a lead fires a message. Approvals surface in the lead's My Approvals inbox.
- **Inputs:** `COLLECTIONS_MODE fixture|quickbooks|servicetitan` — honest status: all three modes
  collapse to one unbuilt live skeleton (3/3 reads NotImplementedError); the documented
  QBO-AgedReceivables-primary / ST-cross-check design is not yet in code. Sync events in
  (advisory): `invoice`, `payment`, `customer`.
- **Deterministic outputs:** Due-date A/R aging (Current/1-30/31-60/61-90/91-120/121+);
  per-customer workflow status (reconciled / expecting_money when a covering future promise exists
  / disputed / action_required / write_off_or_collections); 5-step dunning ladder with TCPA/consent
  channel DOWNGRADE computed in code (do-not-call → email; no SMS opt-in → email; no email →
  human); deterministic owner per status; worst-first worklist; portfolio totals (% current, %
  over-30, at-risk 91+); compliant email/SMS/call-script drafts (STOP opt-out, CAN-SPAM address,
  mini-Miranda, quiet hours).
- **Gated actions:** `send_dunning_email` / `send_dunning_sms` / `place_dunning_call` (via the
  dedicated propose endpoint, `routes_collections`) — ALL ALWAYS_HITL. Email live fails closed;
  SMS/call run through the provider-agnostic voice client, fixture-simulated today.
- **Autonomy default:** hitl, and effectively permanent for its kinds: even in auto mode every
  dunning touch queues for a lead. Compliance is code (channel downgrade in the engine, consent
  re-checked inside the executor), not copy.
- **KPIs:** $ collected from the 91+ bucket per month; % of A/R over 30 days (portfolio health);
  promise-to-pay kept rate; compliance violations = 0 (channel-downgrade correctness is a tested
  invariant).
- **What it learns:** CBR + CIPHER from lead edits to dunning drafts and status calls —
  tone/narration only; the aging math, ladder steps, and consent gates never learn.
- **Platform coverage (honest):** Fixture-only everywhere. QuickBooks is the natural first live
  source (its AR reads already exist on the financial agent's adapter) but the collections live
  client itself is unbuilt; ServiceTitan cross-check likewise. Procore/Buildertrend: reachable in
  principle via the accounting domain, demo-only today.

### Pricebook Agent

- **Mission:** Keep materials costs current from vendor price files and re-price every item under
  the sold-hour model, so no job is quoted off stale costs.
- **Department:** finance + warehouse (`DEPT_AGENTS`: both include pricebook).
- **Approver:** Finance or warehouse department lead/admin, 2FA — `update_pricebook_item` is
  ALWAYS_HITL (a wrong figure misprices every job quoted from it); a human confirms each recomputed
  price. Undo deterministically restores `old_price_cents`.
- **Inputs:** Distributor CSV/XLSX price files via upload — the platform's one genuinely
  platform-independent live input, with a REAL production parser (header synonyms,
  net-cost-beats-list priority, $1,234.56 handling, subtotal-row skip, 50k-row cap).
  `PRICEBOOK_MODE fixture|servicetitan` (both live ST reads unmapped). Sync events in (advisory):
  `pricebook_material` / `service` / `equipment`.
- **Deterministic outputs:** Alex's sold-hour reprice model (price = sold_hours x rate + materials
  + materials x markup) in Decimal half-up integer cents: per-item old/new materials cost, price
  delta ($ and %), margin delta, changed-SKU list, beyond-tolerance flags (default 5%), vendor SKU
  coverage.
- **Gated actions:** `update_pricebook_item` (via the dedicated propose endpoint,
  `routes_pricebook`) — ALWAYS_HITL, undoable; the live ServiceTitan write fails closed.
- **Autonomy default:** hitl, permanently for its kind: auto mode still queues every price change
  for a lead.
- **KPIs:** SKUs repriced per vendor-file cycle; margin points recovered on beyond-tolerance items;
  % of price updates approved without edit; days from vendor price file received to approved
  reprice.
- **What it learns:** CBR + CIPHER from lead edits/rejections on proposed prices — narration and
  prioritization only; the reprice arithmetic is firewalled and property-tested.
- **Platform coverage (honest):** Price-file upload works TODAY regardless of field platform — the
  honest cross-platform story. ServiceTitan: pricebook reads and the price write are
  unmapped/fail-closed (fixture demo only). Procore/Buildertrend: no pricebook domain in the
  registry — served exclusively via price-file upload.

---

## Operator agents (internal to the Top Builder AI business — never a tenant surface)

### Email Agent (operator-only)

- **Mission:** Triage the operator inbox, draft replies, detect and rewrite underperforming email
  workflows, and send deliverability- and law-compliant outreach — for the Top Builder AI business
  itself, not tenants.
- **Department:** platform operator (NOT in `DEPT_AGENTS`/`ALL_AGENTS` — gated on `require_admin`;
  email/seo assistant tools additionally require admin + aal2).
- **Approver:** Platform operator (admin role + 2FA). Its kinds are not in ALWAYS_HITL, but the
  operator gate itself is the bar; reply drafts the engine marks `requires_human` are never even
  proposed.
- **Inputs:** Fixture inbox + workflow performance stats today. Outbound rail: Resend on
  send.topbuilderai.com — integration built, fails closed without `RESEND_API_KEY` (live sending
  blocked on the key).
- **Deterministic outputs:** Unread/needs-reply/trash triage totals; reply drafts
  (`requires_human` held for a person); underperforming-workflow detection with proposed
  subject/preview rewrites + rationale (an admin applies them via the in-app assistant;
  `applied_rewrite` overlays at read time, persisted runs stay pure); `email_advisory`
  recommendations.
- **Gated actions:** `delete_emails`, `send_email_reply`, `rewrite_workflow` (none ALWAYS_HITL —
  operator-gated instead), plus the `send_outreach_email` executor with undo, whose compliance core
  runs INSIDE the executor: CAN-SPAM fields, HARD Canada block overriding consent, GDPR/UK
  cold=HELD, suppression list, warm-up cap. The param-trust and warm-up gaps are now closed
  (migration 0027): consent, country, and suppression are resolved server-side from
  `outreach_contacts` + `email_suppression` (proposer-supplied flags are IGNORED; an unknown
  contact is HELD fail-safe), and the warm-up daily cap is enforced against `outreach_sends`. One
  remaining nuance: the warm-up cap counts sends per-tenant while the sending subdomain is shared
  across tenants — a cross-tenant operator-level counter is a future refinement.
- **Autonomy default:** hitl behind the operator gate; `EMAIL_SEND_MODE=fixture` in production
  today.
- **KPIs:** Needs-reply queue cleared per day; open→click lift on workflows after approved
  rewrites; sends to suppressed/Canadian addresses = 0 (executor-enforced invariant); warm-up cap
  adherence once live.
- **What it learns:** Workflow-rewrite acceptance/edit signals feed the same governed learning
  loop; triage rules are deterministic and do not learn.
- **Platform coverage (honest):** N/A to ServiceTitan/Procore/Buildertrend — this agent operates on
  the operator's own inbox and outreach rail. Live status: inbox fixture-only; Resend send path
  built but blocked on the API key; cold outreach has been routed to the separate Salisbury
  CRM/Apollo track.

### SEO Agent (operator-only)

- **Mission:** Keep topbuilderai.com cited and RECOMMENDED by LLMs and search for contractor-AI
  buyer queries across all three field platforms, via advisory analysis and gated publishing.
- **Department:** platform operator (not a tenant agent; admin + aal2 on the assistant surface).
- **Approver:** Platform operator (admin + 2FA). Neither of its kinds is ALWAYS_HITL — the operator
  gate is the control; publishing to owned properties is reversible.
- **Inputs:** Site/content performance fixtures today; composes with the external geo-flywheel
  monthly cron (citation scans, gap prioritization) that runs outside this codebase.
- **Deterministic outputs:** `seo_advisory` recommendations (content gaps, citation-rhythm
  conformance targets: answer-first headings, fact density, buyer-question ladder); proposed blog
  posts and comment placements routed through the action gate.
- **Gated actions:** `publish_blog_post`, `post_comment` — both operator-approved, neither
  ALWAYS_HITL, both fixture-executed today. The `post_comment` `external_ref` is now built from
  `hashlib.sha256` (not salted Python `hash()`), so its fixture confirmation is stable across
  restarts and idempotency comparison holds.
- **Autonomy default:** hitl behind the operator gate; guardrails from the GEO standing rules apply
  (<=1-2 genuinely useful pages/week, outreach human-sent, never auto-post Reddit).
- **KPIs:** LLM citation/recommendation appearances for ServiceTitan/Procore/Buildertrend buyer
  queries (measured monthly by the flywheel); posts published per week within the <=2 guardrail;
  citation lift per monthly cycle.
- **What it learns:** Monthly flywheel measurement feeds re-prioritization (what earned citations
  gets weighted up); in-app learning loop applies to narration of advisory runs.
- **Platform coverage (honest):** N/A to the three field platforms as data sources — this agent
  targets the brand's OWN web properties (blog, FAQ, landing). Publishing executors are
  fixture-fenced; the live GEO work currently ships through the geo-flywheel pipeline, not this
  agent's executors.

### Ads Agent (operator-only)

- **Mission:** Run the operator-global leads pipeline and Meta/Google campaign engine (ADR 0009)
  so Top Builder AI's own customer acquisition is deterministic, gated, and undoable — never a
  tenant surface.
- **Department:** platform operator — deliberately ABSENT from `ALL_AGENTS` and every `DEPT_AGENTS`
  entry (`permissions.py` comment: adding it would wrongly surface it in the tenant org overview).
  Two-layer gate: app (`require_admin` + `PLATFORM_OPERATOR_EMAILS`) and DB (RLS on
  `app.operator='on'` via `operator_session`).
- **Approver:** Platform operator with 2FA (aal2). The three spend-committing kinds are ALWAYS_HITL
  — a person consents before money leaves; campaign activation explicitly requires aal2.
- **Inputs:** Operator CRM leads (9 no-`tenant_id` tables behind the operator gate), Meta/Google
  ad-platform APIs via OAuth with PKCE + state → HttpOnly session. `ADS_MODE=fixture` offline; live
  fails closed. All PII SHA-256-hashed before any platform upload (`app/ads/pii.py`).
- **Deterministic outputs:** Deterministic campaign plans, budget figures, and conversion-sync
  payloads from the pure `app/ads/engine.py` — the LLM never computes a spend figure (ADR-0003
  applies to ads too). Campaigns are always created PAUSED.
- **Gated actions:** 5 kinds, all owned by `ads` in `KIND_OWNER`, all undoable:
  `ads.create_campaign`, `ads.update_budget`, `ads.activate_campaign` (ALWAYS_HITL — they commit
  spend) + `ads.pause_campaign` and `ads.sync_conversion` (deliberately auto-eligible:
  spend-reducing / idempotent hashed upload).
- **Autonomy default:** hitl behind the double operator gate; create-PAUSED invariant means even an
  approved create moves no money until a separately-approved activate.
- **KPIs:** Cost per qualified lead by platform; unapproved spend variance = $0 (structural:
  activation is ALWAYS_HITL + aal2); conversion-sync freshness; pipeline leads advanced per week.
- **What it learns:** Campaign outcome data feeds the operator's manual iteration; the ads engine
  itself is deterministic and does not learn — go-live gates live in
  `docs/ADS_INTEGRATION_GOLIVE.md`.
- **Platform coverage (honest):** N/A to ServiceTitan/Procore/Buildertrend — this is GTM tooling
  for the business. Honest status: fixture-only (`ADS_MODE=fixture`, uncommitted-at-build Phase 1
  per ADR 0009); Meta/Google OAuth flows built but no live ad account connected; every live write
  fails closed.

---

## Known gaps the charters surface

Open items the charters flag, in one place. Each stays on this list until the fix ships and the
corresponding charter line is updated.

1. **Workforce — live ST reads incomplete.** Only appointments + timesheets are live-mapped;
   technicians, trade economics, job durations, and demand signals are unmapped and fail closed, so
   there is no end-to-end live ServiceTitan run yet. The `payroll_adjustment` live send is unwired
   (body-building proven in tests; the POST itself fails closed).
2. **Financial — live QBO run blocked. RESOLVED.** `get_jobs` + `get_payment_velocity` are now
   wrapped best-effort (`app/agents/financial/data.py` `_best_effort`), so a QBO-connected tenant
   completes a live run on the available lanes (cash/AR/AP) instead of crashing the assembly.
3. **`create_ap_draft` ownership mismatch. RESOLVED.** The sync spine now stores the action row as
   `agent=documents` (`app/sync/service.py` `_handle_bill`) and `router.py` routes `bill`/`purchase`
   to documents, matching `KIND_OWNER` — stored agent, narration, and approvals inbox all agree.
4. **Documents — no propose path for its own kinds.** No service or frontend path proposes any of
   its 4 kinds; the auto-file story dead-ends at a recommendation row and only a raw
   `POST /v1/actions` can propose. Open task: mirror the collections dedicated propose endpoint.
5. **Inventory — ST client unbuilt, no construction domain.** All 5 ServiceTitan inventory reads
   raise NotImplementedError; Procore/Buildertrend have no inventory domain in the registry. Sales
   copy must never claim inventory on Procore/Buildertrend.
6. **Booking — live intake and write unbuilt.** The live intake client is 4/4 NotImplementedError
   and the booking write is fixture-executed (live fails closed). No construction intake domain
   exists, so booking is ServiceTitan-only even in principle.
7. **Routing — no live feed anywhere.** The ST dispatch client is 4/4 NotImplementedError;
   construction mappers all raise.
8. **Collections — live client unbuilt.** All three `COLLECTIONS_MODE` values collapse to one
   unbuilt skeleton (3/3 reads NotImplementedError); the documented QBO-AgedReceivables-primary /
   ST-cross-check design is not yet in code.
9. **Pricebook — ST reads/write unmapped.** Both live ServiceTitan pricebook reads are unmapped and
   the price write fails closed; price-file upload is the platform's only live pricebook input.
10. **Email (operator) — param-trust + warm-up gaps RESOLVED.** Migration 0027: consent, country,
    and suppression are resolved server-side from `outreach_contacts` + `email_suppression` (params
    ignored; unknown contact HELD) and the warm-up cap is enforced against `outreach_sends`. Remaining
    nuance: the warm-up cap counts per-tenant while the sending subdomain is shared across tenants (a
    cross-tenant operator-level counter is a future refinement). Resend live sending is still blocked
    on `RESEND_API_KEY`; the inbox is still fixture-only.
11. **SEO (operator) — `post_comment` idempotency bug. RESOLVED.** The executor now builds
    `external_ref` from `hashlib.sha256`, so the fixture confirmation is stable across restarts and
    idempotency comparison holds.
12. **Ads (operator) — fixture-only, uncommitted Phase 1.** `ADS_MODE=fixture`; Meta/Google OAuth
    flows built but no live ad account connected; every live write fails closed. Go-live gates:
    `docs/ADS_INTEGRATION_GOLIVE.md`.
13. **Buildertrend is partner-gated platform-wide.** No self-serve connect exists; every
    Buildertrend claim carries the partner-application dependency.
