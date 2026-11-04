# Production-readiness audit

Audited the Top Builder AI platform against the pre-launch checklist (no fake data in user flows,
per-account isolation, fail-closed security, idempotency, secrets hygiene, smoke-tested). Status as
of the overnight build.

## ✅ Passing

| Area | Evidence |
|---|---|
| **Tenant isolation** | Postgres RLS on every tenant table, `FORCE` + fail-closed `NULLIF(...)`. App connects as non-superuser `app_user` (no `BYPASSRLS`). Proven by `test_rls_isolation.py` (cross-tenant read blocked, unscoped = 0 rows) and isolation assertions in every agent/connection/webhook/knowledge API test. |
| **Fresh start per tenant** | A new tenant has zero runs/knowledge/events; nothing is shared. No global mutable user data. |
| **No fake data in real mode** | Fixtures are clearly *demo adapters* (`REDACTED`). Flipping to `live` uses real APIs. No hard-coded results in the agent logic — every figure is computed deterministically. |
| **Auth** | Pluggable JWKS/OIDC verification; `/auth/dev-token` is disabled outside `ENV=dev`. Role-gated run endpoints. |
| **Secrets hygiene** | No secrets in code. ServiceTitan/QBO tokens are Fernet-encrypted at rest in the vault; key from Secret Manager. JWT/DB/Anthropic via env/Secret Manager. |
| **Fail-closed** | RLS returns no rows when unscoped; webhooks reject without a valid HMAC signature; auth rejects missing/invalid tokens. |
| **Idempotency** | Agent runs dedupe by deterministic `inputs_hash` (with a `force` override). `test_idempotency.py`. |
| **SSRF** | RAG URL ingestion blocks loopback/private/link-local/reserved/metadata addresses and non-http(s) schemes; redirects disabled. `test_parsing.py`. |
| **Advisory-only** | Agents never write back; adapters request read scopes. No money/schedule mutation path. |
| **Error handling** | Consistent JSON error envelope; no stack traces leaked; unhandled errors logged with a request id. |
| **Input validation** | Pydantic models on every body; query bounds (`ge/le`). |
| **Rate limiting** | Per-IP token bucket on mutating routes. |
| **Migrations** | Tracked + idempotent (`schema_migrations`), applied as a one-off Cloud Run Job (not per-instance). |
| **Observability** | Structured JSON logs with request-id + tenant binding; health + readiness probes. |
| **Tests / CI** | 110 tests (unit, property, integration incl. RLS/idempotency/vault/webhooks/RAG). GitHub Actions runs lint + the full suite against a Postgres service + builds both images. |

## ⚠️ Gaps to close before GA (tracked)

1. **Rate limiting is per-IP and per-instance.** Behind a load balancer every request shares the LB
   IP. Move enforcement to the gateway and add **per-tenant** quotas/metering. (In-process limiter is
   a first line only.)
2. **Single Fernet vault key.** Move to **per-tenant envelope encryption** via KMS; support key
   rotation (`MultiFernet`).
3. **IdP not yet wired.** `AUTH_MODE=jwks` is implemented and unit-tested but needs a real issuer
   (Supabase Auth/Auth0/Entra) configured; add per-tenant SSO + webhook secrets.
4. **Live ServiceTitan mappings incomplete.** Appointments/timesheets are mapped + tested; technician
   economics, job-duration aggregation, and demand signals need a real tenant to finish (ADR 0005).
5. **PDF/XLSX ingestion** not yet implemented (text/markdown/CSV/HTML/URL are). Add
   unstructured.io / pdfminer.
6. **No deploy yet.** Cloud Run + Supabase + Secret Manager wiring is documented
   (`DEPLOY_CLOUD_RUN.md`) but not executed — needs the GCP/Supabase accounts.
7. **Observability depth.** Add OpenTelemetry traces (API → graph → DB) and per-tenant cost/usage
   dashboards.
8. **Pre-GA hardening backlog.** Load test, dependency/security scan in CI, SOC 2 evidence (the audit
   log + ADRs are the spine).

## Smoke test (run before declaring an environment live)

```bash
API=<base-url>
curl -s $API/health
# obtain a JWT from your IdP (or /auth/dev-token in dev), then:
curl -s -X POST "$API/v1/agents/workforce/runs?horizon_days=21" -H "Authorization: Bearer $JWT"
curl -s -X POST "$API/v1/agents/financial/runs"  -H "Authorization: Bearer $JWT"
curl -s -X POST "$API/v1/agents/inventory/runs"  -H "Authorization: Bearer $JWT"
```
Verify each returns a populated `totals` block, that a second identical call returns the same
`run_id` (idempotency), and that a second tenant cannot read the first tenant's runs.
