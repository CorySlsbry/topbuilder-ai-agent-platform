# Procore Marketplace Partner Application — page-by-page fill sheet

Copy/paste each answer into the matching page of the form (signed in as **support@salisburybookkeeping.com**).
Pages **1–7 are already filled in the draft** — verify them, then do **8–18** from here. **Do not submit until you've reviewed everything.**
Every answer is true and backed by what we built; the only soft ones are the GTM page (16) — tweak to taste.

Form: https://docs.google.com/forms/d/e/1FAIpQLSfygvXmaQPUsc0800Sb8XylMJqaq1kax2fzyrcfYCO2NvQKvg/viewform?authuser=1

---

## Page 1 — Contact  ✅ (already filled)
- Email: `support@salisburybookkeeping.com`
- Your Name: `Cory Salisbury`
- Job Title: `Founder`

## Page 2 — Sanctioned countries?  ✅ → **No**
## Page 3 — AES-256 at rest?  ✅ → **Yes**
## Page 4 — TLS 1.2 in transit?  ✅ → **Yes**

## Page 5 — Security narratives  ✅ (verify these 4 saved)
1. **Subprocessor geographies + contractual:** `All customer data is processed and stored in the United States. Subprocessors and regions: Supabase (managed PostgreSQL) on AWS us-east-2 (USA); Google Cloud Platform (Cloud Run, Cloud Logging, Secret Manager) us-central1 (USA); Anthropic (LLM inference, USA); ElevenLabs (telephony voice, USA). No offshore processing. We ensure equivalent security contractually via each provider's Data Processing Addendum (DPA) and published commitments — AES-256 at rest, TLS 1.2+ in transit, and SOC 2 / ISO 27001 attestations — which we review and accept before use, and we restrict configuration to US regions only.`
2. **Incidents (3 yrs):** `None. No data security incidents — no unauthorized access, ransomware, regulatory notifications, or material service disruptions — affecting our organization or subprocessors in the past three years. Top Builder AI is pre-launch with no production customer data to date.`
3. **Regulatory inquiries:** `None. No pending or ongoing regulatory inquiries, data-privacy compliance reviews, or material security audits, and therefore no associated operational impact.`
4. **RTO/RPO + validation:** `RTO <= 4 hours and RPO <= 24 hours today (Supabase automated daily backups + stateless redeploy from immutable images), tightening to RPO ~5 minutes via Point-in-Time Recovery before live customer data. Validation: we capture a recovery-point snapshot (row counts across all tables) and perform a restore rehearsal, comparing counts. Most recent exercise 2026-06-14 — recovery point captured and restore rehearsal performed; result PASS (source rows = restored rows; database ACTIVE_HEALTHY). Cadence: quarterly and before each major release.`

## Page 6 — Company info  ✅ (already filled)
- Company Legal Name: `Salisbury Bookkeeping, LLC`
- Company Website: `https://topbuilderai.com`
- Dev status: **Active in Developer Portal**

## Page 7 — Dev app URL  ✅ (already filled)
- `https://developers.procore.com/developer_apps/15d5cbcf-ade6-47e2-8e78-f9a248840702`

---

## Page 8 — Company Profile  ⬜ (paste these)
- Total Global Employee Count: `2`
- Total Active Customer Count: `Top Builder AI is pre-launch - 0 active product customers to date. (The parent firm, Salisbury Bookkeeping, LLC, serves a small base of bookkeeping and advisory clients.)`
- Staff by region: `All staff are based in the United States (Utah). Total headcount: 2.`
- Developers/engineers for this integration: `2 (founder-led engineering).`
- Strongest commercial presence: `United States - we serve U.S. specialty and general contractors; the company is based in Utah.`
- Industry verticals / buyer personas: `Specialty Contractors and General Contractors (residential and commercial), plus field-service contractors. Buyer personas: owner/operators and back-office leadership (finance, operations, dispatch).`
- Mutual customers interested: `None on Procore yet - the Procore integration is pre-launch, so we have no mutual Procore customers to name at this time.`

## Page 9 (≈) — Integration Vision, Product Scope & Complementarity  ⬜
- **Vision / use case / user journey:** `Top Builder AI is the AI back office for contractors: six self-learning agents (Booking, Dispatch/Routing, Financial, Inventory, Workforce, Documents) that turn a contractor's system-of-record data into deterministic, audited recommendations and human-approved actions. With Procore, we read project, financial, and document data and surface live margin/cash, materials, labor forecasting, and document filing. User journey: the contractor authorizes our app from Procore (OAuth), we read the relevant project/financial/document data, our deterministic engine computes the numbers, and the back-office team reviews recommendations in our dashboard and approves any write-back. Advisory by default; every action is proposed, approved, audited, and reversible.`
- **Which Procore products/tools:** `Across our six agents and our mobile field-ops app, we integrate (read) with: Project Management (Projects, Schedule, RFIs, Submittals, Drawings, Daily Log, Directory/Contacts, Correspondence); Project Financials (Budget, Prime Contracts, Commitments/POs, Change Orders, Direct Costs, Invoicing, Forecasting); Field Productivity / field tools (Daily Logs, Timesheets, Crews, Production Quantities); and the Documents tool. By agent: Financial -> Project Financials; Inventory -> Commitments/POs + Direct Costs + Documents; Workforce -> Timesheets / Field Productivity + Schedule; Routing & Dispatch (field operations) -> Daily Logs + Schedule + Field Productivity; Documents -> Documents + RFIs + Submittals; Booking -> Directory/Contacts + Schedule. Our mobile field-ops app reads the field (Daily Logs, Timesheets) for technicians on site. Read-only by default; any write-back is human-approved.`
- **Gap filled + differentiation:** `Procore is the construction system of record; we run the AI back-office analysis it isn't built to do - live margin and cash, materials/inventory, labor forecasting, and automated document filing - surfacing money leaks and risk early. We never replace Procore's PM workflows; we complement them. Differentiation: our figures are computed by deterministic, unit-tested code (the LLM only narrates, never computes a number), the agents self-learn from the contractor's own corrections (per-tenant, isolated), and every write is human-approved and reversible.`

## Page 10 (≈) — Technical Mechanics & Infrastructure  ⬜
- **Bi-directional? (read + write back):** **No** to start - read-first/advisory. *(If it only offers Yes: choose Yes and add: "Reads first; any write-back is behind a human-approval gate.")* If asked to detail: `We read projects, RFIs, submittals, daily logs, budgets, prime contracts, and change orders. Writes are disabled by default; any future write-back (e.g., a note or document) happens only through an explicit human-approval gate, audited and reversible.`
- **Bulk data export?** → **No**
- **Permanent migration to a separate System of Record?** → **No** (Procore remains the system of record)
- **Multi-tenant architecture + isolation + aggregation:** `Multi-tenant SaaS on Google Cloud Run with PostgreSQL (Supabase). Strict logical isolation via Postgres Row-Level Security (FORCE) on every tenant table; the application connects as a non-superuser role so RLS is enforced, not advisory; the tenant is set per request and is transaction-local. We do NOT aggregate or pool insights across customers - each tenant's data and any self-learning are isolated to that tenant. Tenant isolation is proven by automated two-tenant tests.`
- **High-level technical diagram (optional):** leave blank / "Available on request." *(File upload — skip for now.)*
- **Procore for Government / FedRAMP?** → **No** (no FedRAMP authorization; not pursuing the Government environment at this time)

## Page 11 (≈) — AI Strategy & Architecture  ⬜
- **Uses AI/ML?** → **Yes**
- **How AI is integrated + outcomes:** `We use Anthropic Claude for narration and explanation only. Every business figure is computed by deterministic, unit-tested code - the LLM never computes a number (our "figure firewall," ADR-0003). The agents address concrete back-office problems: margin leakage caught early, materials/inventory tracking, labor/overtime forecasting, after-hours call booking, and automated document classification/filing. Outcomes: earlier visibility into profit and risk, fewer unbilled materials, less avoidable overtime, and far less manual back-office work.`
- **Procore data in training vs inference; boundaries:** `Procore customer data is used strictly for real-time inference, never for model training. The Anthropic API is used for inference only and does not train models on our data. Our self-learning stores per-tenant narration cases (retrieval, RLS-isolated) and is NOT model training. Technical boundary: the LLM is stateless per request; figures come from deterministic code; learning data is per-tenant and never crosses tenants or trains a shared model.`
- **Retain data beyond a session? deletion controls:** `The LLM (Anthropic API) does not retain Procore data beyond the request - calls are stateless. Our system persists the data needed to operate in a per-tenant, RLS-isolated database, encrypted at rest (AES-256). We support data retention limits and deletion on request: a tenant's data can be purged on request, and all data is deleted on offboarding.`
- **Agent-to-agent / MCP:** `We have adopted the agentic-web/WebMCP standard on our marketing surface and use an internal tool registry for our in-app assistant. A formal Model Context Protocol (MCP) server for cross-agent interoperability is on our roadmap (next 6-12 months).`
- **AI write actions + human-in-the-loop:** `Yes, our agents can propose write actions, but they never execute autonomously: every action follows propose -> human approve -> execute, and is audited and reversible. A master switch and per-agent autonomy setting (Off / Approve / Auto) governs this, defaulting to human-in-the-loop. We never auto-apply pricing, code, security, or financial changes from model output.`

## Page 12 (≈) — Strategic Alignment & GTM  ⬜  *(soft answers — tweak to taste)*
- **One-sentence joint value:** `Procore keeps the project's system of record; Top Builder AI turns that data into a real-time AI back office - live margin, materials, labor, and paperwork - so contractors see profit and risk early instead of at month-end.`
- **Ideal joint-sale customer:** `A US specialty or general contractor (roughly $5M-$100M revenue) already standardized on Procore for project management and financials, with a lean back office feeling the strain of manual margin tracking, materials, and document filing.`
- **Opportunity size:** `Every Procore contractor has a back office; our wedge is the recurring AI back-office layer on top of Procore. We see a meaningful per-customer expansion opportunity and a long runway across Procore's contractor base.` *(Cory: adjust if you want a specific number.)*
- **Committed executives:** `Cory Salisbury, Founder, is directly committed to and accountable for this partnership.`
- **Resources dedicated:** `Founder-led engineering and customer success today; we dedicate direct developer time to the integration, hands-on onboarding for each customer, and joint marketing content.`
- **Joint GTM co-invest:** `Co-marketing content and case studies, a Marketplace listing with a demo video, and joint webinars/outreach to shared Procore customers.`
- **Anything else:** `We build security-first (RLS tenant isolation, AES-256 at rest, TLS 1.2+, gated/reversible writes, full audit log, the figure firewall) and we are pre-launch, so we can align to Procore's standards from day one rather than retrofitting.`

> Pages may split across more than 18 screens (some "Yes/No" answers reveal a follow-up). The mapping above covers every question in the Partner Application section of the readiness guide; match each to the on-screen question. Phase II (Technical Feasibility) and Phase III (Certification) are separate, invitation-only forms later — answers for those are in `docs/PROCORE_PARTNER_APPLICATION.md`.

## Before you submit
1. Click **Back** through pages 1–7 and confirm each shows its answer (re-paste from above if any field is blank — page 5's four boxes especially).
2. Confirm the **dev-account email** (the pending Procore confirmation) so the dev-app link is valid.
3. Review every answer, then **Submit**.
