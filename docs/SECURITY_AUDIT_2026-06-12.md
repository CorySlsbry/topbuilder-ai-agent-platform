# Security Audit — Top Builder AI (2026-06-12)

Four-lens adversarial audit (authn/authz · tenancy/data · LLM/agent surface · edge/infra/frontend)
of the live agent platform, plus live black-box probes against the deployed services. Method: read
the actual code + attack the running system; every finding carries a realistic attack path and a
file:line. Two postures judged: **NOW** (public sales demo) and **BEFORE-REAL-DATA** (the go-live
gate, the moment real customer ServiceTitan/QuickBooks data flows).

## Verdict

The platform was **architected security-first** and it shows: tenant isolation is enforced in the
database (RLS FORCE on every table, a non-superuser app role, a regression test proving it), figures
never pass through the LLM (ADR-0003 firewall), every write goes through an approval gate, secrets
are encrypted at rest, and the assistant's tools re-check permissions server-side. The audit found
**one critical code-level authorization bug (now fixed)** and a set of hardening gaps — most of which
are config-posture items the go-live runbook already planned, plus a few cheap defense-in-depth wins
that have been shipped.

**Bottom line:** safe to keep running as a public demo (the critical bug is closed). NOT yet cleared
for real customer data until the BEFORE-REAL-DATA section below is worked through — that is the
enterprise go-live gate.

## What's genuinely strong (verified, with evidence)

- **Tenant isolation is real and database-enforced.** Every tenant table (migrations 0001–0016) has
  `ENABLE + FORCE ROW LEVEL SECURITY` with the fail-closed `tenant_id = NULLIF(current_setting(
  'app.current_tenant',true),'')::uuid` policy — an unset GUC yields zero rows. The app connects as
  `app_user` (no SUPERUSER, no BYPASSRLS; asserted in `test_rls_isolation.py`). Tenant scope is set
  transaction-local (`set_config(...,true)` inside `session.begin()`), so a pooled connection can't
  leak scope across requests. **Live-probed:** an apex token reading `/v1/org/overview` saw 0 of
  canyonridge's 38 people.
- **No SQL injection surface.** Every query across all 16 repositories uses bound parameters;
  jsonb/vector casts are in-SQL. The only string-built SQL is migration DO-blocks over a hard-coded
  table list.
- **Auth is sound on the Supabase path.** The token signature is verified, then tenant + role +
  department are resolved from the `user_memberships` directory — client-supplied role/tenant claims
  are ignored (the correct defense). JWT algorithms are pinned per mode (no alg-confusion); audience
  and issuer are checked. **Live-probed:** a forged `alg=none` admin token → 401.
- **Every route is authenticated.** Only health/root, `/auth/config` (publishable anon key only),
  the ENV-gated `/auth/dev-token`, and the HMAC-signed webhook are open. **Live-probed:** all data
  routes → 401 without a token.
- **The write path is gated and reversible.** propose → approve → execute (ADR-0007), admin-only,
  master switch, per-kind allowlist, idempotent, audited, with undo. Every executor is fixture-only
  and fail-closes in live mode — even with `ACTIONS_ENABLED=true` nothing can write to a real
  ServiceTitan/QBO/email system today.
- **The agents can't be tricked into leaking or computing.** Figures come from tested code; the LLM
  only narrates (ADR-0003). The assistant's tool registry is closed, fails closed on unknown tools,
  re-checks role/department/2FA per call inside the tenant session, and defuses id-smuggling
  (workflow writes must target an id the agent itself produced). LLM/agent text renders through
  React's auto-escaping — no `dangerouslySetInnerHTML` touches model output. SSRF guards exist on
  the URL-ingest and connection-test paths.
- **Secrets handled correctly.** Fernet encryption at rest with a Secret-Manager key (raises if
  unset); the API never returns ciphertext. Unhandled exceptions return a generic envelope — no
  stack traces, PII, or internal paths leak to clients. **Live-probed:** assistant cost cap enforced
  server-side (9000-char message → 422; per-tenant daily ceiling holds).

## Fixed NOW (shipped this session — commit a6c56d2)

1. **CRITICAL — cross-tenant admin injection (account takeover).** `routes_admin._resolve_tenant`
   trusted a caller-supplied `tenant_id`/`tenant_slug` with no scope check, and `user_memberships`
   has a permissive write RLS policy by design (resolution runs pre-GUC) — so the API authorization
   was the *only* control, and it was missing. A per-tenant admin (or anyone minting a dev-token on
   the demo) could `POST /v1/admin/memberships {role:'admin', tenant_id:<any tenant>}` and plant an
   admin row into another tenant's directory; on Supabase login that email resolves to admin on the
   victim tenant → full cross-tenant read/write. **Fix:** a cross-tenant target now requires a
   platform-operator email (`PLATFORM_OPERATOR_EMAILS` allowlist, empty by default → no one);
   ordinary tenant admins are forced to their own tenant. `list_memberships` scoped identically.
   Regression-locked in `test_admin_tenant_scope.py`.
2. **Dashboard clickjacking / no CSP.** The Next.js dashboard shipped with zero security headers, so
   the gated approve/execute/2FA controls could be framed and clickjacked. Added CSP
   (`frame-ancestors 'none'`), `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy`,
   `Permissions-Policy`, HSTS via `next.config.js headers()`.
3. **Rate limiter keyed on the wrong IP.** Keyed on `request.client.host` (the Google front-end hop
   behind Cloud Run) → ineffective per-client throttling. Now keys on the first `X-Forwarded-For`
   hop; `/docs` is no longer exempt from throttling.
4. **Cron secret timing side-channel.** Three cron endpoints compared the shared secret with `!=`
   → `hmac.compare_digest`.
5. **`/docs` reconnaissance.** `/docs`, `/redoc`, `/openapi.json` are now suppressed at `ENV=prod`
   (kept on for the dev demo).

## BEFORE-REAL-DATA — the go-live gate (✅ ALL RESOLVED 2026-06-12, commits 04d9887 + 2967a71)

> **UPDATE 2026-06-12:** every item below was implemented, tested (399 pure tests + the new SQL
> validated directly against Supabase + full live smoke ALL GREEN), and deployed (api rev built from
> `sec3`, web from `sec2`). The table is kept as the record of what each fix was. The platform has
> now cleared its own go-live security gate at the code level; the remaining go-live steps are pure
> config posture (ENV=prod, rotate secrets, set the operator allowlist) listed at the bottom.

| # | Severity | Finding | Required fix |
|---|---|---|---|
| 1 | High | **`require_admin`'s 2FA (aal2) is a no-op on the dev & JWKS paths** — `Principal.aal` defaults to `aal2`, so on any non-Supabase path every admin token is treated as 2FA-verified. | Default `Principal.aal='aal1'`; only set `aal2` from a verified factor. On JWKS, map a real `amr`/`acr` claim. |
| 2 | Med | **JWKS path trusts token-supplied role + tenant_id** (no directory resolution, unlike Supabase). | If `AUTH_MODE=jwks` is ever used, resolve role+tenant from `user_memberships` keyed by the verified subject (mirror the Supabase path). Recommended: **stay on Supabase auth** at go-live. |
| 3 | Med | **Learning-loop poisoning can survive the gate** — quorum counts a single actor's repeated edits; the offline (DISABLE_LLM) eval passes any rule trivially; `auto_approve_on_eval` is a tenant-settable param that removes the human. Inert now (DISABLE_LLM=1). | Require DISTINCT authors for quorum; make offline eval refuse-by-default; gate auto-approve behind deploy config (not a tenant param); add an LLM-judge content check on candidate rules. Do before turning the LLM on for narration. |
| 4 | Med | **Per-tenant webhook secret + replay.** One shared `webhook_signing_secret`; the signed body doesn't bind the path `tenant_id`, and there's no timestamp/nonce or dedupe → a legit signed event can be replayed cross-tenant. | Per-tenant secret in the vault selected by path tenant_id; sign the tenant_id + a timestamp; reject stale; UNIQUE `(tenant_id,source,external_id)` for idempotency. Do before any live webhook. |
| 5 | Med | **No length cap on feedback `correction`/`note` or knowledge-ingest `content`**, and no per-tenant daily cap on those endpoints → with live embeddings (OpenAI key), direct uncapped spend + DB bloat. | `Field(max_length=…)` (4–8 KB), clamp the embedded slice, add per-tenant daily caps like the assistant has. Do before `EMBEDDING_PROVIDER=openai`. |
| 6 | Med | **Knowledge-ingest SSRF is check-then-fetch (DNS-rebinding TOCTOU)**, no response-size cap. (GCP metadata needs a header this GET doesn't send, so SA-token exfil specifically is blocked; other internal services aren't.) | Resolve host once, connect to the pinned validated IP; cap response body; allowlist ports. Do before knowledge ingest is exposed to real users. |
| 7 | Low | **Org directory reads ignore department scope** — any in-tenant login can read every employee's profile + `ai_context`. | Filter org reads by caller scope, or restrict person-profile/`ai_context` to managers (mirror the executive-KPI gate). Do before real org data. |
| 8 | Low | **Credential-vault writes gated by `require_runner` (analyst), not `require_admin`.** An analyst can overwrite their own tenant's ServiceTitan/QBO creds (sabotage; no exfil — secrets are encrypted and never returned). | Gate `PUT /v1/connections` + `/test` behind `require_admin` (+aal2). |
| 9 | Low | **Frontend container runs as root**; base images pinned by tag; `npm install` not `npm ci`. | Add a non-root `USER` to the runner stage; pin bases by digest; `npm ci`. |
| 10 | Low | **CORS/TrustedHost default `*`.** Acceptable now (bearer auth, no cookies); Host header unvalidated. | Set `ALLOWED_ORIGINS` to the dashboard origin and `TRUSTED_HOSTS` to the API host at prod (already in the go-live runbook). |
| 11 | Low | **Assistant denial-of-wallet.** Per-tenant 150/day cap holds the absolute $ bound, but there's no per-IP/global ceiling, so an abuser can exhaust the demo tenant's budget for the day. | Add a per-IP/session sub-cap + a global daily ceiling; optionally a lightweight challenge on the public demo. (Mostly closes at `ENV=prod` when dev-token is disabled.) |
| 12 | Low | **Rate limiter is in-process per-instance** → N Cloud Run instances multiply the effective limit. | Back the buckets with Redis/Memorystore or front with Cloud Armor before real load. |

## The known, intentional demo posture (closes at `ENV=prod`)

`ENV=dev` keeps `/auth/dev-token` open — anyone on the internet can mint an admin token for the demo
tenant. This is by design for a public sales demo (fixture data only, advisory-only, no real
secrets reachable). The go-live runbook already flips `ENV=prod` (dev-token off) + `AUTH_MODE`
to the real IdP + locks CORS. **The critical bug above was a code-level hole that survived that
cutover — which is why it was fixed now, not deferred.**

## Recommended go-live sequence (the enterprise gate)

1. Work the BEFORE-REAL-DATA table (items 1–9 are the hard gates; 1, 3, 4, 5, 6 are the
   security-critical ones).
2. `ENV=prod` (dev-token off, `/docs` off), keep `AUTH_MODE=supabase` (don't switch to raw JWKS
   unless item 2 is done), lock `ALLOWED_ORIGINS`/`TRUSTED_HOSTS`, rotate `app_user` + all secrets,
   set `PLATFORM_OPERATOR_EMAILS` to the real operator list, ensure `CRON_SECRET` is ≥32 random bytes.
3. Per the go-live runbook: flip `*_MODE` to live per customer, vault their creds, smoke-test.
4. Re-run this audit against the prod posture before the first real customer.
