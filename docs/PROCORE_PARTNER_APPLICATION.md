# Procore Marketplace — Complete Requirement Map & Answer Pack (Top Builder AI)

The FULL 3-phase Procore Technology Partner Journey, every question, each marked
**✅ met** (built + true today) · **🔨 build** (gap to close before we answer) · **[CORY]** (your
business/legal fact). Principle: **we don't fabricate — every "yes" is backed by something built.**

Submitting under **support@salisburybookkeeping.com**. Confirmed by Cory (2026-06-14): no security
incidents (3 yrs), no regulatory inquiries, **pre-launch (no real customer data in production yet)**.

Built this session: **AES-256-GCM** vault (`backend/app/crypto.py`), **TLS 1.2 floor**
(`backend/app/db.py`), **DR runbook + validated restore** (`docs/DISASTER_RECOVERY.md`). Deployed:
api rev 00022-jc7.

---

# PHASE I — Partner Application (the 18-page form)

### Mandatory Compliance Gates (fail = auto-reject)
1. **Serve sanctioned countries (Balkans, Belarus, China, Cuba, Iran, N. Korea, Russia, Syria, Crimea…)?** → **No.** US-only contractors. ✅
2. **AES-256 at rest (DB, backups, logs, non-prod)?** → **Yes.** ✅ (Supabase/AWS + GCP infra AES-256; app-layer vault now AES-256-GCM)
3. **TLS 1.2+ in transit?** → **Yes.** ✅ (Cloud Run HTTPS 1.2/1.3; DB pinned ≥TLS 1.2; outbound HTTPS)
4. **Subprocessor geographies + equivalent-security contracts** → Supabase (AWS us-east-2), Google Cloud (us-central1), Anthropic, ElevenLabs — all US. ✅ answer / **[CORY]** countersign DPAs.
5. **Security incidents (3 yrs)?** → **None.** ✅ (Cory-confirmed)
6. **Pending regulatory inquiries/audits?** → **None.** ✅ (Cory-confirmed)
7. **RTO/RPO + validation (date+results)?** → RTO ≤4h / RPO ≤24h→PITR; **validated 2026-06-14, PASS.** ✅

### Company Profile & Market Presence  ✅ (Cory-confirmed 2026-06-14)
- **Company Legal Name:** Salisbury Bookkeeping, LLC
- **Headquarters / address:** 7835 N. Escalante Dr, Eagle Mountain, UT 84005, USA
- **Total Global Employee Count:** 2  ·  **Developers/engineers for this integration:** 2 (founder-led)
- **Company age:** just over 1 year (founded 2025)
- **Total Active Customer Count:** a small book of bookkeeping/advisory clients; **0 Procore-integration
  customers yet** (the Procore integration is pre-launch)
- **Mutual customers interested in this integration:** none on Procore yet
- **Strongest commercial presence:** United States (Utah-based)
- **Website:** topbuilderai.com (product) / salisburybookkeeping.com (firm)  ·  **Dev status:** Active in
  Developer Portal (app `15d5cbcf-…`, email being verified)  ·  **Verticals:** Specialty + General Contractors.

### Integration Vision, Product Scope & Complementarity  — ✅ author-ready
- Vision/use-case/journey; Procore products = **Project Management, Project Financials, Documents, RFIs**; GTM gap = the AI back office (money/materials/people/paperwork) Procore doesn't automate. ✅

### Technical Mechanics & Infrastructure
- **Bi-directional?** → read-first; writes only via human-approved gate. ✅
- **Bulk export?** → No. ✅ · **Permanent migration off Procore?** → No (Procore stays SoR). ✅
- **Multi-tenant isolation + cross-customer aggregation?** → Postgres RLS FORCE, non-superuser role, per-tenant; **no cross-tenant aggregation**; figure-firewall. ✅
- **High-level technical diagram** → 🔨 **BUILD** (optional now, mandatory in Phase II).
- **Procore for Government / FedRAMP?** → No. ✅

### AI Strategy & Architecture
- **Uses AI/ML?** → Yes; narration + governed self-learning; figures are deterministic (firewall). ✅
- **Procore data in training vs. inference-only?** → **inference-only; never trains a model.** ✅ answer — 🔨 **BUILD** the explicit no-train guarantee (Anthropic API zero-retention/no-train config + doc).
- **Do agents retain Procore data beyond a session? Deletion controls?** → system persists in RLS DB; LLM is stateless. 🔨 **BUILD** customer-data **retention + deletion** controls.
- **Agent-to-agent / MCP?** → 🔨 **BUILD** (or answer "MCP planned 6–12 mo"; we already ship WebMCP on marketing + an in-app tool registry).
- **Agents take write actions w/ Procore data + HITL?** → Yes; propose→approve→execute, audited + reversible. ✅ (ADR 0007)

### Strategic Alignment & GTM  — [CORY]
- **[CORY]** one-sentence joint value · ideal joint-sale customer · opportunity size · committed executives · dedicated resources · co-invest GTM activities · anything else.

---

# PHASE II — Technical Feasibility (invitation-only, after App clears)
- Integration type: **Agentic + Data Connector**. ✅
- **MCP implementation?** → 🔨 **BUILD** or "planned 6–12 mo".
- Data flows in/out of Procore (tools/modules) → ✅ author-ready (projects/RFIs/dailies/budgets…).
- **Auth strategy** → OAuth2 (Authorization Code + Client Credentials). ✅
- **Service-account credential rotation + compromise process** → 🔨 **BUILD** credential rotation (vault key rotation; today crypto.py notes rotation as "future").
- **OAuth token storage + controls** → AES-256-GCM vault + IAM. ✅
- **Persisted Procore data + retention + minimization/field-filtering** → 🔨 **BUILD** data minimization + retention policy.
- **Code security: SAST/DAST, dependency scanning, code review** → 🔨 **BUILD** SAST/DAST + dependency scanning in CI.
- **Integration workflow diagram + "Better Together" deck (mandatory)** → 🔨 **BUILD** diagram + deck. · UI/UX prototype (optional) → have the dashboard.
- Customer feedback on concept → **[CORY]**.

---

# PHASE III — Certification (invitation-only, after Feasibility approved)

### Developer App & Demo
- Dev app URL (`developers.procore.com/developer_apps/15d5cbcf-…`) ✅ **[CORY]** confirm email · **Demo video** in the listing's Showcase → 🔨 produce the Procore-config demo (we have a hero explainer to adapt).

### Integration & Data Overview
- Aligns w/ feasibility diagrams; updated diagram + mapping diagram → 🔨 **BUILD**. · final read/write payload summary ✅ author. · **list all Procore APIs used** ✅ author. · exchange frequency / **est. API calls per customer/day** ✅ author. · **rate-limit management** → ✅ (paginated, backoff) author. · **error handling 401/429/5xx/timeouts** → ✅ (tenacity retry/backoff) author + 🔨 confirm 401-refresh + 429-honor. · **refresh-token handling + storage** → AES-256-GCM ✅.

### Authentication & Compliance
- **OAuth grant types + rationale** → ✅ author. · **least-privilege scopes + per-scope justification** → 🔨 **BUILD** (define the minimal Procore scopes when wiring the app).
- **Data retention policy (duration, deletion triggers, customer deletion requests)** → 🔨 **BUILD** (same as the retention/deletion item).
- **Prod access roles / least-privilege / review cadence / offboarding revocation** → **[CORY]** (document the access policy) + ✅ partial.
- **Audit logs of all Procore read/write (retention, access, tamper-protection)** → ✅ (`audit_events`) + 🔨 document retention + tamper-evidence.
- **SBOM / dependency vuln scanning + cadence** → 🔨 **BUILD**.
- **Accredited (SOC 2/ISO)?** → **[CORY]** not yet (planned). · **Pen test (date/firm/findings)?** → **[CORY]** not yet (internal security audit done; external pen test = your call).

### Webhook Logic
- Uses webhooks; namespace; **validate payload signatures + handle failures** → ✅ (HMAC MAC binding tenant+timestamp, replay-protected, fail-closed) + 🔨 confirm Procore's signature scheme when wiring.
- Processing/retries/failure handling → ✅ author.

### Support & Customer Validation  — [CORY]
- **[CORY]** validating Procore customer (name + company_id) · support model + SLA targets.

### Marketplace Listing Security Checklist
- Legal name / HQ / data-processing locations → **[CORY]**.
- Subprocessors? **Yes** ✅ · sensitive personal data? **No** ✅ · dedicated security function? **[CORY]** (founder-led) · security audits/reviews? ✅ internal · accredited? **[CORY]** not yet · pen testing? **[CORY]** not yet · **breach-notification mechanism?** → 🔨 **BUILD** (policy + process) · **vulnerability disclosure program?** → 🔨 **BUILD** (security.txt + VDP page) · **bug bounty?** No ✅.
- **Encrypted at rest AES-256?** Yes ✅ · **in transit TLS 1.2?** Yes ✅.
- **SSO?** → 🔨 **BUILD** or roadmap · **SAML?** → 🔨 roadmap · **MFA for back-end access?** → ✅ app 2FA (AAL2); **[CORY]** infra MFA (GCP/Supabase).
- **Authenticated request to Procore File Access Service (FAS)?** → 🔨 confirm when wiring Documents.

---

# 🔨 BUILD CHECKLIST — what we must add before finishing (so every answer is true)

**Done this session:** ✅ AES-256-GCM vault · ✅ TLS 1.2 floor · ✅ DR runbook + validated restore.

**To build (product/process gaps):**
1. **Customer data retention + deletion** — retention policy + an endpoint/runbook to purge a tenant's Procore data on request (Phase I AI + Phase III).
2. **Credential / key rotation** — vault key + OAuth token rotation + a compromise-response runbook.
3. **Dependency vuln scanning + SBOM in CI** — e.g. `pip-audit` + `npm audit` + CycloneDX SBOM in the build.
4. **SAST/DAST** — static analysis (ruff/bandit) + a DAST pass wired into CI.
5. **No-training guarantee** — Anthropic API zero-retention/no-train posture, documented; confirm self-learning is inference/retrieval only, never model training.
6. **Vulnerability Disclosure Program** — `/.well-known/security.txt` + a VDP page + intake.
7. **Breach-notification process** — a written incident-response + customer-notification policy.
8. **MCP** — expose the agent toolset via MCP (or formally answer "planned 6–12 mo").
9. **Least-privilege Procore OAuth scopes** — enumerate the minimal scopes + per-scope justification (when wiring the app).
10. **Audit-log retention + tamper-evidence** — document/strengthen `audit_events` (append-only, retention).
11. **SSO/SAML** — build or roadmap for back-office access.
12. **Integration diagram + "Better Together" deck + Procore demo video** — assets (Phase II/III).
13. **global_counters RLS** + enable **leaked-password protection** (from the Supabase advisor).

**[CORY] business/legal:** legal entity + address + HQ · employee/customer counts · regions · # engineers · funding/traction · mutual/validating customers · pricing · GTM/executives/co-invest · support SLA · SOC2/pen-test decision · DPA countersignatures · privacy/terms URLs · confirm the dev-account email.
