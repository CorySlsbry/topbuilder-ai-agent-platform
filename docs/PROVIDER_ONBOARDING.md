# Provider onboarding — taking any of the 10 field systems live

How a customer on any registered platform goes from **demo** to **live data**. The registry
(`app/integrations/providers/registry.py`) is the machine-readable version of this doc; the
dashboard's "Your field system" panel surfaces each platform's connect requirements from it.

## The three readiness tiers

| Tier | What it means | Where each platform stands |
|---|---|---|
| **Demo-ready** | The full pipeline (all agents, every screen, narration in the platform's language) runs on built-in sample data. Switching the tenant's provider adapts the whole product immediately. | ✅ All 10 platforms, today |
| **Connect-ready** | The setup path is encoded in the product: auth model, the credential the customer hands over, and where it goes (the encrypted credential vault). | ✅ All 10 platforms (this doc + registry `auth_kind`/`connect`) |
| **Live** | A real API client maps that platform's endpoints onto our canonical domain models, verified against a real tenant, fail-closed. | ✅ ServiceTitan only. Others: built per first customer (see recipe) |

## Why "live" is per-customer work, not a checkbox

Agents never talk to a platform directly — they consume **canonical domain models** (jobs,
intake, inventory, documents, accounting) served by domain adapters (`app/integrations/{booking_intake,
dispatch,documents,inventory,accounting}`). Taking a platform live means writing its client that
fills those models, exactly as `app/integrations/servicetitan/` does. That requires **real API
credentials**, which (for most platforms) only a customer account or a partner agreement can grant.
So the honest sequencing is: sell the install → use the customer's account to obtain credentials →
build + verify their adapter during the install window. The $8k Back-Office Command Install covers
this — it's the "Install" in the name.

## Per-platform connection sheet

> Auth details below come from each platform's public developer docs; **re-verify at onboarding** —
> plans and partner terms change.

| Platform | Segment | Auth | The customer hands over | Gate |
|---|---|---|---|---|
| ServiceTitan | Home services | OAuth2 | App authorization from their ServiceTitan account (client ID/secret + app key via developer.servicetitan.io) | **LIVE** — flagship |
| Housecall Pro | Home services | API key | API key from their account (API access on supported plans) | None known |
| Jobber | Home services | OAuth2 | Authorize our app via the Jobber Developer Center (GraphQL API) | Public dev program |
| FieldEdge | Home services | Partner | — | **Partner program** (Xplor) — apply before promising live data |
| Service Fusion | Home services | OAuth2 | Authorize our API client | Public API |
| Workiz | Home services | API key | API token from account settings | None known |
| JobNimbus | Home services | API key | Bearer API key from settings | None known |
| AccuLynx | Home services | API key | API key generated from their AccuLynx account | Customer account required |
| Buildertrend | Construction | Partner | — | **Partnership agreement** required |
| Procore | Construction | OAuth2 | Install/authorize our app from the Procore marketplace (developer.procore.com) | Public dev program |

## The go-live recipe (any platform)

1. **Credentials into the vault** — the encrypted credential vault (Phase 2a) stores the key/OAuth
   tokens per tenant; secrets never land in env files or code.
2. **Write the live client** — clone the ServiceTitan client's shape: one module per domain the
   platform serves (`domains` in the registry), mapping its endpoints onto the canonical models.
   Construction platforms (Buildertrend, Procore) serve jobs/documents/accounting only — the
   booking-intake and inventory agents stay on their existing sources for those tenants.
3. **Fail-closed contract tests** — recorded/documented response shapes drive tests; a live-mode
   adapter that can't reach its API must raise, never fabricate (`test_go_live_failclosed.py`
   pattern).
4. **Verify against the customer's tenant** — read-only smoke on real data; compare counts/totals
   with what the customer sees in their platform.
5. **Flip the tenant** — `tenant_settings.fsm_provider` (already done at demo time) + the relevant
   `*_MODE=live` for that tenant; registry `status` moves to `live` once verified.
6. **Standard go-live gate** — everything in `docs/GO_LIVE_RUNBOOK.md` still applies (advisory-only
   default, action gate off until trust is earned, RLS isolation already enforced).

## Pre-selling order (if we choose to build ahead of customers)

Highest-leverage platforms to pre-build (no partner gate + biggest market): **Housecall Pro,
Jobber, AccuLynx** (roofing wedge), then **Procore** (commercial construction wedge). FieldEdge and
Buildertrend require partner applications — start those conversations early because approval is on
their clock, not ours.

## Construction platforms — endpoint → canonical mapping (fill-in-the-blanks)

The construction adapters live in **`app/integrations/construction/`** and mirror the ServiceTitan
adapter's fidelity exactly — a fail-closed live skeleton, not a full live integration:

- `buildertrend_client.py` — `LiveBuildertrendClient` (partner/API-key auth + paginator + fail-closed
  `_require_credentials`; read methods raise `NotImplementedError` with the documented endpoint).
- `procore_client.py` — `LiveProcoreClient` (marketplace OAuth2 refresh-token flow + paginator +
  fail-closed `_require_credentials`; read methods raise `NotImplementedError` with the endpoint).
- `mappers.py` — the documented source-field → canonical-field functions (raise until verified live).
- `dispatch.py` — `get_construction_client(slug, settings)` /  `get_fsm_live_client(slug, settings)`:
  the one adapter-layer dispatcher (the FSM variant also routes `servicetitan`).

Config knobs (mirror the `servicetitan_*` style, fixture by default; `app/config.py`):
`BUILDERTREND_MODE`, `BUILDERTREND_API_KEY`, `BUILDERTREND_PARTNER_TOKEN`, `BUILDERTREND_BASE_URL`;
`PROCORE_MODE`, `PROCORE_CLIENT_ID`, `PROCORE_CLIENT_SECRET`, `PROCORE_REFRESH_TOKEN`,
`PROCORE_COMPANY_ID`, `PROCORE_BASE_URL`, `PROCORE_AUTH_URL`.

Construction platforms serve **jobs / documents / accounting** only (NOT intake/inventory — those
tenants keep their existing sources). To take a platform live, fill the mapper bodies below and verify
field names/units against the customer's real tenant (ADR 0005 / the ADR-0003 figure firewall — never
guess a number). The fail-closed contract is locked by `tests/test_construction_adapters.py`.

### Buildertrend (partner API)

| Canonical domain | Buildertrend endpoint(s) | Source field → canonical field | Mapper |
|---|---|---|---|
| **jobs** | `GET /v1/jobs`, `GET /v1/schedules` | `id`→id, `jobName/title`→customer_name, `jobType`→job_type, `jobsiteAddress`→(x,y) zone coords, `estimatedDurationMinutes`→duration_min, `priority`→priority, `requiredTrade`→required_skill, `scheduledStart/End`→window_start/end_min, `status`→status | `map_buildertrend_job_to_job` |
| **documents** | `GET /v1/documents`, `GET /v1/selections`, `GET /v1/customers` (owners) | doc: `id`, `fileName`→filename, `contentType`→mime_type, `documentType`→declared_type, `ownerName`→customer_hint, `amountCents`→amount_cents, `dueInDays`→due_in_days, `coiExpiresInDays`→expiry_in_days, `isSigned`→signed, `jobId`→related_job_ref · customer: `id`→ref, `displayName`→name | `map_buildertrend_document_to_document`, `map_buildertrend_customer_to_customer` |
| **accounting** | `GET /v1/invoices` (AR), `GET /v1/purchase-orders` + budgets (AP) | invoice→AR: `id`, `ownerSegment`→customer_segment, `totalAmount`→amount, `invoiceDate`→issued, `dueDate`→due, `status=='paid'`→paid · PO→AP: `id`, `vendorName`→vendor, `amount`→amount, `dueDate`→due, `status=='paid'`→paid | `map_buildertrend_invoice_to_accounting`, `map_buildertrend_po_to_accounting` |

### Procore (marketplace REST v1.0)

| Canonical domain | Procore endpoint(s) | Source field → canonical field | Mapper |
|---|---|---|---|
| **jobs** | `GET /rest/v1.0/projects?company_id={company}` | `id`, `name/display_name`→customer_name, `project_type`→trade, `address`→(x,y) zone coords, `duration`→duration_min, `flag/priority`→priority, `trade`→required_skill, `start_date/completion_date`→window_start/end_min, `active/status`→status | `map_procore_project_to_job` |
| **documents** | `GET /rest/v1.0/projects/{project}/rfis`, `/submittals`, `/daily_logs`, `GET /rest/v1.0/companies/{company}/vendors` | doc: `id`, `subject/title`→filename, `'application/pdf'`→mime_type, `'rfi'/'submittal'`→declared_type, `assignee/contact`→customer_hint, `cost_impact_cents`→amount_cents, `due_date`→due_in_days, `expiration`→expiry_in_days, `signed/approved`→signed, `project_id`→related_job_ref · vendor: `id`→ref, `name/company_name`→name | `map_procore_rfi_to_document`, `map_procore_vendor_to_customer` |
| **accounting** | `GET /rest/v1.0/projects/{project}/prime_contracts` (AR), `/commitments` + change orders (AP) | prime-contract→AR: `id`, `owner_segment`→customer_segment, `grand_total`→amount, `created_at`→issued, `due_date`→due, `status=='paid'`→paid · commitment→AP: `id`, `vendor.name`→vendor, `grand_total`→amount, `due_date`→due, `status=='paid'`→paid | `map_procore_prime_contract_to_accounting`, `map_procore_commitment_to_accounting` |

> Procore rotates the refresh token on each token exchange — persist the new `refresh_token` from the
> auth response into the credential vault so the next exchange uses the current one (noted in
> `procore_client.py::_access_token`).
