# Go-Live Runbook — flipping a client onto live ServiceTitan

The platform runs identically on fixtures (the sales demo) and on a client's live ServiceTitan +
QuickBooks. Going live is a **config flip + the per-client onboarding**, not a rewrite. This is the
white-glove step that justifies the $50k price — do it *for* the client, not as a self-serve form.

## The load-bearing safety guarantee (tested)

`SERVICETITAN_MODE=live` (and the live action executors) **fail closed**: until the real integration is
wired and verified against the client's tenant, every write *refuses* rather than fabricating a success.
Proven by `tests/test_go_live_failclosed.py` (all 4 write executors + the live adapters raise). A client
can never get a fake booking, filing, estimate, or schedule change.

## 1. Provision the per-client ServiceTitan developer app

ServiceTitan requires a **custom developer app per client** (non-marketplace path):
1. We (the developer) create the app in the ServiceTitan developer portal → obtain the **App Key**.
2. The client's ServiceTitan admin authorizes our app → generates the **Client ID + Client Secret**
   (this is why "there's no API key to find in ServiceTitan yet" — the client mints it on authorize).
3. The client needs **"The Works"** subscription for full API access. OAuth2 client-credentials only.
4. Start in the **Integration (sandbox) environment**, then production.

## 2. Store the credentials (encrypted vault — never in code or env files)

Per-tenant secrets go through the encrypted credential vault (Fernet, RLS-scoped), never in source:

```
PUT /v1/connections   { "provider": "servicetitan", "secret": { "client_id": "...", "client_secret": "...", "app_key": "...", "st_tenant_id": "..." }, "metadata": { "env": "integration" } }
PUT /v1/connections   { "provider": "quickbooks",   "secret": { ... } }
```

Required handover from the client: ServiceTitan app creds, QuickBooks OAuth, an embeddings key
(OpenAI/Voyage) if RAG is on, and the IdP choice (Supabase Auth / Auth0 / Entra).

## 3. Flip the modes + deploy

Set live modes + secrets via env / Secret Manager (not code):
`SERVICETITAN_MODE=live` · `ACCOUNTING_MODE=quickbooks` · `INVENTORY_MODE=servicetitan` ·
`DISPATCH_MODE=servicetitan` · `DOCUMENTS_MODE=servicetitan` · `BOOKING_INTAKE_MODE=live` ·
`AUTH_MODE=jwks` (+ OIDC vars) · `ACTIONS_ENABLED=true` only after the per-agent autonomy policy is set.
Then: run the migrate job, deploy (`docs/DEPLOY_CLOUD_RUN.md`), and complete the live ServiceTitan
mappers (the `servicetitan_*_client.py` skeletons) against the sandbox tenant.

## 4. The go-live readiness gate (the $50k bar — clear ALL before "ready")

- [ ] **No static/demo data in the live product.** Fixtures serve only the demo. Every client starts
      clean and isolated; the dashboards show real per-tenant data via the adapters.
- [ ] **Per-account isolation proven.** RLS two-tenant tests pass; the runtime role is non-superuser /
      no `BYPASSRLS`.
- [ ] **Writes are gated.** Per-agent autonomy policy set (Off / Approve / Auto); `ACTIONS_ENABLED`
      intentional; every action signed, logged, idempotent, reversible.
- [ ] **Fail-closed verified.** `test_go_live_failclosed.py` green; no executor/adapter fabricates a write.
- [ ] **Secrets** only in the vault / Secret Manager; the dev Fernet + JWT secrets are NOT used in prod.
- [ ] **Smoke on the DEPLOYED instance** with a real, cleared tenant — every router, then one HITL
      action end-to-end (propose → approve → execute) against the sandbox.
- [ ] Run `production-readiness-audit` and clear its checklist (`docs/PRODUCTION_READINESS.md`).

## 5. Smoke (deployed)

`python backend/scripts/smoke.py` against the deployed URL (hits every router), then drive one booking
and one document filing through propose → approve → execute on the sandbox tenant and confirm the
ServiceTitan-side result. Only then flip an agent's autonomy from Approve to Auto.
