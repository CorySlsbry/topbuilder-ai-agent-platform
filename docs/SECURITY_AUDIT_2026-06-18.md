# Security + Production-Readiness Re-Audit — 2026-06-18

Enterprise-grade ("Procore-level") re-audit before a real customer install (Sam/Summit via Alex).
5-lens adversarial audit over the current code, re-verifying the 2026-06-12 gate + everything added since
(Pricebook, Collections+dunning, Capacity, payroll write-back, AP-draft, warranty, dept-scoped propose,
Google/QBO OAuth, the assistant). **IP constraint:** the platform code stays Cory's IP and is resold to many
contractors, so **tenant isolation IS the IP moat** — a cross-tenant read/write would be an existential failure.

## Verdict: STRONG. The IP-moat holds; no cross-tenant break. 1154 pure tests pass.

**Confirmed strong (verified, not assumed):**
- **Tenant isolation is database-enforced on EVERY tenant table** (incl. all new ones — pricebook/collections/
  capacity/grants/usage/audit): `ENABLE + FORCE ROW LEVEL SECURITY` + the fail-closed
  `tenant_id = NULLIF(current_setting('app.current_tenant',true),'')::uuid` policy. `app_user` is **live-confirmed**
  `rolsuper=false / rolbypassrls=false` — RLS genuinely applies to the app role. This is the IP moat, and it holds.
- Role + tenant resolved ONLY from the membership directory (never self-asserted token claims); JWT alg pinned per
  mode; `aal` defaults to the weakest aal1, aal2 only on positive MFA evidence; admin = role+aal2.
- Assistant tool registry is a closed set whose permission gate mirrors the REST bars exactly; write targets are
  validated against ids the agent itself produced (anti-injection).
- Every write is propose→approve→execute, admin-gated, audited, reversible; **every live data client + write
  executor FAILS CLOSED** (raises, never fabricates). Deterministic figures never pass through the LLM (ADR-0003).
- Webhook MAC binds tenant+timestamp+body (constant-time, 300s replay window, per-tenant secret, dedupe).
- OAuth `state` is a tenant-bound HMAC (constant-time, TTL, UUID-validated, fail-closed exchange).
- ENV=prod cleanly disables the dev-token + /docs + /openapi.

## Fixed NOW (7 — code-level, each test-locked; 1154 pass)
| Sev | Fix |
|---|---|
| HIGH | **Rate-limit XFF spoofing** (`middleware.py`) — was keyed on the client-most (spoofable) X-Forwarded-For entry; now keys on the proxy-appended hop (`trusted_proxy_hops`), so a caller can't mint unlimited buckets. |
| HIGH | **Action kind↔agent binding** (`routes_actions.py`) — the generic `/v1/actions` propose now checks the KIND's owning agent (KIND_OWNER map), so a finance/collections runner can't hand-craft a workforce `payroll_adjustment`. |
| HIGH | **HS256 dev-token coupled to ENV** (`deps.py`) — a prod service that forgot `AUTH_MODE` no longer falls through to HS256 verification (which would accept a token signed with a leaked/default secret). |
| MED | **Feedback/knowledge dept scope** (`routes_feedback.py`, `routes_knowledge.py`) — both took `agent` as a free param; now enforce `can_use_agent`, so a dept-scoped login can't rate/correct/ingest another dept's agent (closes a cross-department learning-loop bypass). |
| MED | **Fail-fast prod boot guard** (`main.py` `_assert_production_config`) — refuses to boot if ENV!=dev with dev AUTH_MODE, the default/short JWT secret, or wildcard CORS/TrustedHost. |
| LOW | **Grant/revoke audit attribution** (`routes_org.py`) — used a non-existent `subject` attr (empty actor); now `email or user_id`. |
| LOW | **SSRF IPv6 bracket** (`rag/parsing.py`) — pinned netloc now brackets IPv6 literals. |

## BEFORE-REAL-DATA go-live gate (config/posture flip per customer — NOT exploitable on the fixture demo)
1. **CRITICAL (wiring): thread `tenant_id` into every LIVE client factory + load that tenant's secret from the
   vault.** Only fires when `*_MODE=live` is wired with real per-tenant creds — today the live clients fail closed
   (raise) before any secret load, so it can't fire on the demo. **This is the #1 go-live engineering task** and is
   the IP-moat in live mode (one customer must never read another's ServiceTitan/QBO). Build + lock with a 2-tenant test.
2. **OAuth `state` → session-bound / PKCE** (Google + QBO + Procore, one fix) before live provider connections.
3. **Config flip:** `ENV=prod`, `AUTH_MODE=jwks/supabase`, rotate `JWT_SECRET` + `app_user` pw, lock `ALLOWED_ORIGINS`/
   `TRUSTED_HOSTS` to the real origins (now enforced by the boot guard), `DB_SSL_VERIFY=true` + pin the pooler CA, `HSTS_ENABLED=true`.
4. **Defense-in-depth:** a new migration with `ALTER ROLE app_user NOSUPERUSER NOBYPASSRLS` (self-healing); validate
   `person_id` belongs to the tenant on membership create; lock the dunning executors' fail-closed contract with a test
   (like `test_go_live_failclosed.py`); persist rotated refresh tokens back to the vault on refresh.

## Install + learning readiness
Ready to install per-customer once the go-live gate above is closed: the stack is containerized (`docker compose up`),
100% env-configured (own keys + own DB), standard Postgres + pgvector, RLS-isolated, fail-closed live paths, and the
self-learning loop is governed (eval-gate + canary + human approval + the figure firewall, distinct-author quorum).
A new tenant starts fresh (seed is operator-gated). The owner can resell safely because the multi-tenant boundary is
DB-enforced and the code never leaves.
