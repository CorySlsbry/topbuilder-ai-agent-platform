# Engineering log — Top Builder AI

A running record of **what worked, what didn't, the bugs hit, and how to avoid them**. Written for
the next contributor (human or agent) so the next stretch is faster and we don't repeat mistakes.

---

## What worked (keep doing)

- **Deterministic compute + LLM-explains** (ADR 0003). The single best decision. Every dollar/hour
  figure comes from pure, tested code; the model only narrates. Made everything reproducible,
  auditable, and offline-testable. Reuse this for every new agent.
- **Adapter pattern** (fixture client + live skeleton, config-selected). The whole pipeline runs and
  is tested offline; going live is a config flip, not a rewrite.
- **RLS for tenancy — and an integration test that PROVES it.** The test caught a real policy bug
  (`''::uuid`). Don't trust isolation you haven't tested with two tenants + a fail-closed check.
- **Per-agent module template** (`models, analytics, confidence?, prompts, reasoning, schemas, data,
  graph, service`) + **agent-agnostic persistence** (`add_recommendations`/`add_reasoning`). Agent #1
  took a day; #2 and #3 were hours each because the shape was fixed. **#4 (Booking)** — with a brand-new
  data source (voice/telephony intake, not ServiceTitan) — went green in one session: TDD the engine,
  clone the inventory module shape, add the `booking_intake/` adapter (fixture + live skeleton) +
  fixtures, wire routes + `main.py` + dashboard tab. `agent` is free-text → **no migration to add a 4th
  agent.** Engineer fixtures to a hand-computed oracle and assert it in a no-DB test (`test_booking_data.py`)
  so the demo numbers ($3,260 recovered / $2,895 after-hours) can't silently drift.
- **TDD with hand-computed oracles** on the pure engines (`_scenario()` builders). Fast green, and
  the asserts are independent of the implementation.
- **Deterministic fixture generator** (`generate_fixtures.py`) — realistic 275-row data without
  hand-authoring, and regenerates identically.
- **Tight verify loops**: run tests → preview script → container smoke after every chunk. Caught
  every bug within minutes of introducing it.
- **Clean-DB session fixture** for deterministic integration tests (truncate run/audit/vault/event/
  knowledge tables at session start — like a fresh CI DB).

## Bugs hit → root cause → fix (avoid these)

1. **RLS policy crashed with `invalid input syntax for type uuid: ""`.** A transaction-local
   `set_config(..., true)` reverts the GUC to an empty string (not unset) after the txn, so
   `current_setting(...)::uuid` blew up. **Fix:** `NULLIF(current_setting('app.current_tenant', true), '')::uuid`
   everywhere (fail-closed). Surfaced by the RLS isolation test.
2. **`/runs/latest` returned 404 right after a successful run.** The RLS test inserts
   `status='succeeded'` rows with NULL result; once idempotency stopped inserting duplicates, the most
   recent succeeded row was one of those NULLs. **Fix:** `AND result IS NOT NULL` in the latest/dedupe
   queries + the clean-DB fixture.
3. **Flaky integration tests ("attached to a different loop").** `@lru_cache` bound one async engine
   to the first test's event loop; pytest-asyncio gives each test its own loop. **Fix:** make the
   engine **loop-aware** (keyed by `id(running_loop)`) in `db.py`.
4. **`assert 429 == 404` late in the suite.** All tests hit the API from one client host → shared
   per-IP rate-limit bucket exhausted. **Fix:** raise limits in the test/CI env. **Prod note:** per-IP
   limiting is wrong behind a load balancer — move to per-tenant + gateway.
5. **`asyncpg.AmbiguousParameterError`** on `WHERE (:agent IS NULL OR agent = :agent)`. **Fix:**
   `CAST(:agent AS text) IS NULL OR agent = :agent`.
6. **`SET LOCAL` can't bind parameters.** **Fix:** `SELECT set_config('app.current_tenant', :tid, true)`.
7. **SSRF** in RAG URL ingestion (could hit `169.254.169.254` / internal hosts). **Fix:**
   `assert_safe_url` blocks loopback/private/link-local/reserved/metadata + non-http(s) + disables redirects.
8. **Host port 8000 already in use** on this machine. **Fix:** configurable `API_HOST_PORT`/`WEB_HOST_PORT`.

### Self-learning layer session (2026-06-06)

9. **`docker compose run api python scripts/X.py` ran the *server*, not the script.** The Dockerfile
   `ENTRYPOINT ["/entrypoint.sh"]` doesn't `exec "$@"` — it runs migrations then unconditionally
   `exec uvicorn`, so the passed command became ignored args and the container hung forever (the
   verification pipeline stalled on the migrate step). **Fix:** override the entrypoint for one-off
   commands: `docker compose run --rm --entrypoint python api scripts/X.py`. (Migrations still applied,
   because the entrypoint runs `migrate.py` when `RUN_MIGRATIONS=1` — that part was a happy accident.)
10. **A best-effort write silently returned `None`, and the failure surfaced as a *downstream* logic
    bug.** `agent_cases.run_id` is an FK to `agent_runs(id)`; a standalone verification harness passed a
    random `run_id` with no matching run → FK violation → `record_case` (wrapped best-effort) swallowed it
    and returned `None` → every subsequent assertion (label/retrieve) failed, and a "quarantined after 1
    edit" check *falsely passed* (empty list == empty list). **Root cause:** the test harness, not the
    product — production `service.py` always creates the run immediately before `record_case`. **Fix:** the
    harness/integration test creates a real `agent_runs` row first. **Lesson:** when verifying a
    swallow-on-error path, satisfy ALL FK parents in the harness, or a silent insert failure masquerades as
    a logic error three steps later. Consider a debug flag that re-raises in test mode.
11. **Workflow script: parameter shadowed the `agent()` builtin.** A `pipeline()` stage callback written
    `(agent) => agent(prompt(agent), …)` shadowed the workflow's `agent()` function with the string item →
    "agent is not a function" for every item. **Fix:** name loop/stage params anything but `agent`
    (used `name`). General rule for these scripts: never shadow `agent`/`parallel`/`pipeline`/`phase`/`log`.
12. **Webhook integration test 401'd under compose-default env.** `test_webhooks.py` hardcodes
    `SECRET = "test-webhook-secret"` to sign its payload; the app verifies with `WEBHOOK_SIGNING_SECRET`,
    which compose defaults to `dev-webhook-secret` → signature mismatch → 401. **Not a regression** — an
    env-coupling. **Fix:** run the suite with `-e WEBHOOK_SIGNING_SECRET=test-webhook-secret` (as the
    documented test command already does). Suite then 204/204.

**Verification recipe that worked (no image rebuild needed):** pipe a host script straight into the
container — `MSYS_NO_PATHCONV=1 docker compose run --rm -T --entrypoint python api - < scripts/verify_learning.py`
— and run the full pytest suite by mounting the source read-write and installing only pytest:
`docker compose run --rm -T --user root -v "$(pwd)/backend:/work" -w /work -e RUN_DB_TESTS=1
-e APP_PG_DSN=…app_user@db… -e WEBHOOK_SIGNING_SECRET=test-webhook-secret -e RATE_LIMIT_PER_MINUTE=1000000
--entrypoint sh api -c "pip install -q pytest pytest-asyncio hypothesis && python -m pytest -q"`.
`MSYS_NO_PATHCONV=1` stops Git Bash from mangling the container-side `/work` path.

### Self-learning design notes (what worked — keep doing)

- **Learn on the narration side of the ADR-0003 firewall, never the numbers.** Cases/preferences/lessons
  feed the LLM prompt only; the deterministic engine still computes every figure and the persona forbids
  recomputation. Reward-hacking the dollars is impossible *by construction*. This is the load-bearing call.
- **Every learning read/write in its OWN isolated `tenant_session`, best-effort.** A learning hiccup
  (even an unapplied migration) degrades to byte-identical pre-learning behavior — zero blast radius on the
  run path or the suite. This is why 186→204 had 0 regressions despite touching all 6 agents.
- **Quorum gate before a learned rule goes live** (`quarantined` → `active` at support ≥ 3). One angry
  edit can't move behavior. Tenant-scoped by RLS; the global tier is operator-seed-only (`WITH CHECK`
  forbids `app_user` writing a NULL-tenant row) → no cross-tenant preference leak.
- **Prove ONE agent's loop end-to-end, then replicate in parallel.** Financial was the verified template;
  a parallel workflow wired the other 5 (disjoint files, no conflicts) in ~2 min — all compiled, uniform
  markers, suite green. The shared engine (`memory.py`/`service.py`/`scoring.py`) is verified once for all.

## Tooling / process gotchas

- **Edit tool "File has not been read yet."** After many operations the harness drops a file's read
  state; `Edit` then refuses. **Avoid:** Read immediately before editing a file you last touched many
  turns ago (especially `main.py`, edited ~6×). Batch a file's edits together when possible.
- **Claude Preview screenshots flaked** on the headless renderer (repeated 30s timeouts). **Use**
  `preview_snapshot` (a11y tree) or `preview_eval` instead. Clicks race async fetches — `preview_eval`
  with an explicit `setTimeout` wait before reading the DOM is the reliable pattern.
- **pytest-asyncio + SQLAlchemy async**: function-scoped loops + any cached engine/sessionmaker =
  cross-loop errors. Make async resources loop-aware (or pin a session-scoped loop).
- **A stale `docker compose` `api` container shadows a fresh local server on the same port.** After
  editing code and starting a fresh `uvicorn` on 8088, the live smoke hit an OLD container
  (`servicetitanagentplatform-api-1`, a pre-booking image) still bound to `0.0.0.0:8088` from a prior
  session — and `localhost`→`::1` (IPv6) resolved to the container's proxy, not my IPv4 uvicorn.
  **Symptom:** brand-new routes return `404` while the old ones return `201`. **Fix:** `docker stop`
  the stale container (or `docker compose up --build` to rebuild it) before smoke-testing; verify with
  `GET /openapi.json`; prefer `http://127.0.0.1:PORT` over `localhost` to force IPv4 to your process.
- **Docker Desktop can die mid-session (esp. after the machine sleeps).** Postgres went unreachable and
  `docker` reported `dockerDesktopLinuxEngine` pipe-not-found; relaunching the exe + polling left the WSL2
  engine hung well past 3 min. **Effect:** with `RUN_DB_TESTS=1` and no DB, the autouse `_clean_run_tables`
  session fixture fails at setup, so the **whole** suite errors (not just the integration tests). **When
  blocked:** run the pure suite (`pytest -m "not integration"`, which skips that fixture) to keep a green
  signal, and lean on GitHub Actions CI (a real Postgres *service* container, independent of Docker
  Desktop) to validate the DB-integration tests.

## What worked (booking + actions phases — keep doing)

- **Human-approved action gate (ADR 0007)** as the answer to "read-only vs. does things": `propose →
  approve → execute`, off by default (`ACTIONS_ENABLED`), admin-gated, idempotent (`UNIQUE(tenant_id,
  idempotency_key)` + status-guarded `UPDATE ... WHERE status = <expected> RETURNING *`), executor
  registry with a deterministic fixture path (offline-testable) + a fail-closed live skeleton. Split
  execution into claim (committed `executing`) → external write (outside any txn) → record, so a
  transaction is never held across an upstream call. New action types = a new `kind` + executor, no new
  pipeline.

## asyncpg / Postgres / pgvector cheat-sheet (this stack)

- Tenant scoping (per request): `SELECT set_config('app.current_tenant', :tid, true)` inside a txn.
- RLS predicate (fail-closed): `col = NULLIF(current_setting('app.current_tenant', true), '')::uuid`.
- `:p IS NULL OR col = :p` → `CAST(:p AS text) IS NULL OR col = :p`.
- jsonb param: `CAST(:p AS jsonb)` with `json.dumps(...)`.
- vector param: `CAST(:e AS vector)` with `'[' + ','.join(map(repr, vec)) + ']'`; cosine via `<=>`.
- Multi-statement `.sql` migrations: `await conn.execute(sql)` (no args → simple protocol).
- Runtime role must NOT be superuser / NOT have `BYPASSRLS`, or RLS is silently bypassed.

## Context checkpoint protocol (don't lose memory)

When the context window approaches the thresholds below, **stop building and save**:

- **~90%** — write a checkpoint: current state, the in-flight task, the next concrete steps, and any
  decisions not yet in a doc → update the project memory + this log. Then reflect briefly.
- **~98–99%** — emergency minimal save: a 3–5 line "where we are / what's next" so the next session
  resumes cleanly, before auto-compaction.

Triggers: the harness's low-context/compaction reminders, or a self-check after any large multi-file
phase. Better to checkpoint early than lose the thread.


## Governance layer (Phase C/D, 2026-06-06)

Bugs + fixes:
13. `python scripts/X.py` imported the INSTALLED `app`, not mounted `/work/app` (sys.path[0] = script dir).
    Fix: run with `PYTHONPATH=/work` (pytest + migrate.py already self-insert). New scripts importing `app`
    should `sys.path.insert(0, BACKEND_DIR)` like migrate.py.
14. `curl -X POST` with no body -> `411 Length Required` from Cloud Run (no Content-Length). Fix: send `-d '{}'`.
    Not a server bug (httpx in the suite is fine).

What worked (keep doing):
- The eval gate runs on the HUMAN approve path too: `POST /preferences/{id}/approve` calls
  `evaluate_candidate` and 409s a rule that fails safety / golden / the ADR-0003 figure invariant;
  `force=true` overrides and is audited via reviewed_by.
- Gate, don't auto-activate: one line (quorum -> `candidate`, not `active`) flipped "trust the quorum" to
  "quorum proposes, eval+human dispose." Retrieval injects only `active` rules, only to their canary %.
- Offline the gate leans on the deterministic `rule_safety_check`; the golden narration eval is the richer
  online layer (DISABLE_LLM -> `_render` returns situation text, figures preserved by construction). Every
  evaluation is audited in `eval_runs`.
- Tune THRESHOLDS, never figures: the bandit tuner moves `edit_threshold` (learning_params) by recent
  effectiveness; the deterministic numbers stay untouchable (ADR 0003). Drift snapshots FLAG a degrading
  agent for a human rather than silently "fixing" it.

## Friendly errors + provider readiness (2026-06-12, commit ef218d3)

Bugs hit → root cause → fix:

- **"set provider 403" raw error in the UI.** The deployed API wraps ALL errors as
  `{"error": {"code", "message", "request_id"}}` (`app/errors.py`), but frontend error paths read
  `body.detail` (FastAPI's default) → fell back to bare status text. Fix: ONE shared error layer in
  `frontend/lib/api.ts` (`ApiError` + `toApiError` reads BOTH shapes + `friendly()` maps status +
  server detail to plain language). RULE: any new fetch goes through `apiRequest`/`apiGetOrNull` and
  passes a "doing" phrase; never render `res.status` to a user.
- **ExecutiveView detected 403 by regex-ing the error MESSAGE** (`/\b403\b/`) — broke the moment
  messages became human. Fix: `e instanceof ApiError && e.status === 403`. RULE: never encode status
  codes in display strings; carry them as data on the error object.
- **Optimistic UI with no catch = silent fake success.** AgentControls' autonomy pills flipped
  locally even when the server 403'd (analyst clicking Auto saw it "work"). FrontDeskView's load had
  no try/catch → eternal spinner on any failure. Fix: revert-on-reject + per-agent in-flight Set +
  error surfaced. RULE: every optimistic mutation needs a revert path and a visible message.
- **403 ≠ "you lack permission".** The action gate returns 403 for "autonomy is off" /
  "ACTIONS_ENABLED=false" / "dev-token disabled" — a blanket "admins only" message blames the wrong
  cause. The friendly() mapper branches on the server detail string. (Caught by adversarial review,
  not by tests — the suite can't judge copy.)
- **CORS pins local preview out of the deployed API** (`ALLOWED_ORIGINS` = the deployed web origin
  only) → the local dev server can't sign in against prod. Verify UI changes ON the deployed site
  (browser MCP), or run the full local stack.

Provider readiness shipped: registry (`integrations/providers/registry.py`) now carries
`auth_kind` ('oauth2'|'api_key'|'partner') + customer-facing `connect` copy per platform, surfaced
via `/v1/providers` and rendered under the field-system selector ("Fully supported — …" for live,
"Demo data today — …" for adapter_ready). `docs/PROVIDER_ONBOARDING.md` = the per-platform go-live
playbook (3 tiers: demo-ready ✅ all 10 / connect-ready ✅ all 10 / live = ServiceTitan only;
FieldEdge + Buildertrend are partner-gated). Verified LIVE: operator switch ServiceTitan→AccuLynx→
back on canyonridge; analyst 403 renders the friendly copy; pill revert works. api rev 00012-t4x,
web rev 00010-k49.

## In-app assistant + email-workflow admin + phone voices (2026-06-12, commit 5775480)

Bugs hit → root cause → fix (most found by the pre-deploy adversarial review, not tests):

- **Assistant tools as a permission bypass.** First cut gated only the write tool by role. Review
  found: viewer could create_task (route bar = runner roles), email/seo agent reads leaked to
  non-admins (routes are require_admin), and admin-at-aal1 could read via chat what the route 403s.
  FIX + RULE: for every assistant tool, find the equivalent REST route and copy its exact auth bar
  (role + aal + dept scope) — `tools.can_call` + `needs_operator_2fa` encode this; pure-tested.
- **Prompt-injection → unconfirmed write chain.** list_communications returns untrusted inbox
  content into the same loop where update_email_workflow writes real outbound copy. FIX:
  validate workflow_id against the latest email run''s known ids (fail closed), audit every write,
  admin+2FA only; the operator''s explicit chat request = the ADR-0007 human approval.
- **`*.mp3` .gitignore ate the shipped voice previews.** Local docker builds worked (dirty
  worktree); any git-sourced build would 404 all three previews. FIX: `!frontend/public/voices/*.mp3`
  negation + commit the files. RULE: `git check-ignore` every new binary product asset.
- **Claude 4.6 rejects assistant-final-turn prefills.** A client history ending with an assistant
  message would 400→502 and still burn a cap unit. FIX: sanitize_history drops leading AND trailing
  non-user turns.
- **Audio preview AbortError mislabel.** pause()/src-swap during a pending play() rejects with
  AbortError; the catch marked working previews "unavailable" forever. FIX: ignore AbortError,
  ignore stale-src events, clear the failed flag on retry.
- **Vendor voice ids from memory were wrong.** One "well-known" ElevenLabs id wasn''t in the account
  library and two voices mismatched their persona copy. FIX: list /v1/voices and pick by LABELS
  (Bella/Brian/Hope for Riley/Marcus/Jade); previews are real synthesized greetings so the picker
  plays exactly what callers will hear.
- **Email override overlay initially baked into the persisted run.** Moved to read-time overlay
  (latest + idempotent early-return paths) so run history stays the pure engine output.

What worked: pinned contracts in lib/api.ts FIRST, then a background frontend agent built
AssistantDock + the voice picker against them while the backend was hand-built — zero integration
conflicts, both compiled first try. Two-lens review (backend security + frontend contracts) on the
uncommitted diff before deploy: 1 blocker + 12 real findings.

## Full production sweep (2026-06-12, commit 1795d0f; api rev 00016-zjd)

Every route x 3 roles + every UI section/button + every pipeline tested on the LIVE stack.
Harness: `backend/scripts/full_production_smoke.py` (74 checks, state-restoring) — keep running it
after every deploy. Results: API smoke ALL GREEN; Supabase login smoke (Alex + 3 dept) ALL GREEN;
nightly cron verified 200 (forced + last night''s real 08:00 run); 13/13 UI sections render clean;
zero browser console errors; field PWA quote->submit works.

Bugs found -> fixed:
- **Dead action blocked redo forever (real bug).** An ''undone''/''failed'' action kept the
  idempotency key, so re-proposing the same intake returned the corpse and approve 409''d —
  Front Desk ''Approve & book'' was permanently broken for any undone booking. FIX:
  `propose_action` tombstones the dead action''s key (`key::status::id`, audited w/ supersedes)
  and proposes fresh. Verified live: the previously-dead row booked (ref st-appt-B01).
  TODO: add the redo-after-undo case to test_actions_api in the next Docker suite run.
- **ACTIONS_ENABLED was false on prod** — the marquee demo button couldn''t execute. Flipped to
  true (fixture executors are deterministic + undoable; the gate was built for this).
- Smoke-harness bugs (binary mp3 through the JSON reader -> status 0; policies list returns only
  explicitly-set rows; booking figures live under `totals`, not `summary`).

Triage lesson: a 403 in cron logs was MY unauthenticated probe, not the scheduler — always check
userAgent before declaring a pipeline regression. Red text in views (urgent chips, $ leakage,
EMERGENCY badges) matches `[class*=text-red]` — a UI error-sweep must whitelist design accents.

## Security audit + hardening (2026-06-12, commit a6c56d2; api rev sec-a6c56d2, web rev sec-a6c56d2)

Four-lens adversarial audit (authn/authz, tenancy/data, LLM surface, edge/infra) + live black-box
probes. Full report: docs/SECURITY_AUDIT_2026-06-12.md. Verdict: architected security-first
(RLS FORCE everywhere, non-superuser app role, ADR-0003 figure firewall, approval-gated writes,
encrypted secrets, server-side assistant permission gate) — ONE critical code bug, now fixed.

CRITICAL bug found+fixed -> cross-tenant admin injection: routes_admin._resolve_tenant trusted a
caller-supplied tenant_id, and user_memberships has a permissive write RLS policy by design, so the
API gate was the only control and it was missing. Any per-tenant admin (or any dev-token on the demo)
could plant an admin membership into ANY tenant -> account takeover on Supabase login. FIX: cross-
tenant target now requires a platform-operator email (PLATFORM_OPERATOR_EMAILS allowlist, empty by
default); tenant admins forced to own tenant; list_memberships scoped same. Regression-locked
(test_admin_tenant_scope.py). VERIFIED live: canyonridge admin -> apex target = 403; own-tenant
invite still 201.

Also shipped: dashboard security headers (CSP frame-ancestors none + XFO/nosniff/Referrer/HSTS via
next.config) closing clickjacking of the gated controls; rate limiter now keys on X-Forwarded-For
(was request.client.host = the GFE hop behind Cloud Run, ineffective); cron secret -> hmac.compare_
digest (3 endpoints); /docs+/redoc+/openapi suppressed at ENV=prod. 383 pure tests.

LESSON (reusable): a permissive-write directory table (user_memberships USING(true)) means the API
authz is the ONLY tenant boundary on that table — audit those endpoints HARD; a per-tenant "admin"
role is NOT a platform operator. The 12 BEFORE-REAL-DATA items (aal2 default no-op off the Supabase
path, JWKS claim trust, learning-loop poisoning, per-tenant webhook secret+replay, feedback/ingest
length caps, SSRF DNS-rebinding, org dept-scope, connections require_admin, non-root frontend
container) are the enterprise go-live gate -> docs/SECURITY_AUDIT_2026-06-12.md.

## Full security-gate hardening (2026-06-12, commits 04d9887 + 2967a71)

Worked the entire BEFORE-REAL-DATA gate from the audit (docs/SECURITY_AUDIT_2026-06-12.md) — all 12
items + the learning-tier note. Shipped, tested (399 pure tests; new SQL validated directly on
Supabase; full live smoke ALL GREEN incl. Alex + 3 dept logins), deployed (api sec3, web sec2).

- SEC-1 aal: Principal.aal defaults aal1; dev god-token opts into aal2 explicitly; OIDC aal mapped
  from real amr/acr/aal (security.py).
- SEC-2 JWKS: _principal_from_jwks resolves tenant+role from the directory, never the token claims
  (deps.py); pure tests rewritten to lock the identity-only contract.
- SEC-3 learning poisoning: distinct-author quorum (migration 0019 supporters table; threaded
  created_by from the feedback route); offline eval refuse-by-default (eval_verdict evaluatable flag
  — an unevaluatable candidate can't auto-pass); auto-approve gated by settings.learning_auto_approve_
  enabled (deploy flag, not a tenant param); safety denylist extended to financial-instruction /
  social-engineering injection (wire/bank/gift-card/links/without-review/etc).
- SEC-4 webhooks: verify_webhook binds tenant_id+timestamp (no cross-tenant or stale replay),
  per-tenant secret from the vault (provider 'webhook'), event dedupe (migration 0017 partial unique +
  ON CONFLICT) => idempotent replays. Pure + integration tests updated.
- SEC-5 caps: Field(max_length) on feedback/knowledge inputs; per-tenant daily caps (migration 0018
  daily_counters + repositories/usage.py); clamp the embedded slice in ingest.
- SEC-6 SSRF: rag/parsing.py resolves the host once, pins the connection to a validated public IP
  (Host header + SNI => defeats DNS rebinding), caps the body, allowlists ports 80/443.
- SEC-7 org: person-profile ai_context + email redacted for department-scoped logins (routes_org).
- SEC-8 connections: PUT + /test now require_admin (was require_runner).
- SEC-9 frontend container: non-root USER + npm ci (Dockerfile).
- SEC-10 CORS/host: ALLOWED_ORIGINS + TRUSTED_HOSTS env-locked on the API service at deploy.
- SEC-11 assistant cost: per-IP + global DB-backed daily ceilings (global_counters) in addition to
  per-tenant — DB-backed so they hold across Cloud Run instances (covers SEC-12: the in-process rate
  limiter stays best-effort; the real cost controls are the DB caps).
- Learning-tier note: /v1/learning/* reads now require_unrestricted (leadership/operator) — a
  dept-scoped login can't browse governance; mutations stay admin-only. Verified: Alex 200, finance
  login 403.

LESSON (reusable, -> central brain): a permissive-write directory table means API authz is the ONLY
boundary on it; security flags default to the WEAKEST value and upgrade only on positive evidence;
resolve authorization from YOUR directory, never the IdP token's self-asserted claims; DB-backed
caps (not in-process limiters) are what hold cost ceilings across autoscaled instances; offline an
unevaluatable learned rule must refuse-by-default, never auto-pass.

## Current state — Admin Ads-CRM Phase 1 (2026-06-22, ADR 0009)

Built the operator-global Ads-CRM spine, fully offline + advisory (`ADS_MODE=fixture`,
`ACTIONS_ENABLED=false` — nothing spends). NOT yet committed/deployed; pure tests green.

- **Storage + two-layer operator gate.** Migration `0023_ads_crm.sql`: nine operator-global tables
  (no `tenant_id`) — `operator_credentials` (ad-token vault, separate from the tenant vault), CRM
  (`crm_contacts/_leads/_activities`), ad engine (`ad_accounts/_campaign_templates/_campaigns/_metrics`,
  `conversion_syncs`). Integer cents, text+CHECK enums. RLS fail-closed on `app.operator='on'` (set by
  `db.operator_session()`) — a normal `tenant_session` sees zero rows. App layer: every `/v1/crm` +
  `/v1/ads` route = `require_admin` (admin + aal2) + `_require_platform_operator` (PLATFORM_OPERATOR_EMAILS,
  empty→nobody). Two boundaries: a bug in either alone can't leak.
- **Writes reuse the ADR-0007 action gate (no parallel path).** Five kinds `ads.{create_campaign,
  update_budget,activate_campaign,pause_campaign,sync_conversion}` in `app/agents/ads/executors.py`,
  registered in `app/actions/executors.py`, allowlisted in `config.actions_allowed_kinds`. **Create-PAUSED**
  (engine sets `status='PAUSED'`); `activate_campaign` is the ONLY spend-starting step. create/update/
  activate are in `ALWAYS_HITL_KINDS` (auto-mode queues, never self-fires) and require aal2 to approve;
  pause/sync are auto-safe. All five are undoable (create→delete, budget→restore-prior, activate→pause,
  pause→activate, sync→retract); every result carries a stable `external_ref`. `conversion_syncs` is also
  DB-idempotent on `UNIQUE (platform, dedupe_key)`.
- **Determinism firewall (ADR 0003).** All budget/bid/cents/schedule math in pure `app/ads/engine.py` +
  `schemas.py` (no I/O, oracle-testable). Meta `daily_budget`=cents-as-string; Google
  `amount_micros = cents*10_000`. LLM never computes a figure → ad-spend reward-hacking impossible by
  construction.
- **Fixture-first / fail-closed live.** `ads_mode` (one gate, both platforms): fixture clients
  (`integrations/ads_meta|ads_google/client.py`) deterministic + offline; live path RAISES until verified
  (never fabricates a launched campaign).
- **PII hashing.** `app/ads/pii.py` — pure, no-log normalize→SHA-256 (email trim+lower; phone E.164
  digits). `conversion_syncs.payload` holds only the hex digest; plaintext PII never persisted/logged.
- **OAuth closes the open-state gap.** `routes_ads_oauth.py` adds PKCE (S256) + a state→HttpOnly-session
  cookie (HMAC over the JWT secret, constant-time compare, 600s TTL) — operator-scoped (`require_admin` +
  operator allowlist on `/connect`; `/callback` no-auth, the signed cookie+state IS the proof). Tokens →
  operator vault (AES-256-GCM) bound to `ad_accounts.vault_credential_id`; Google refresh_token required
  (force `prompt=consent`) or fail closed; exchange errors → generic 502 (never echo the code).

GOTCHA (the single most common miss, reconfirmed): registering an executor is necessary but NOT
sufficient — `is_executable_kind` also requires the kind in `actions_allowed_kind_set`, so the five
`ads.*` kinds had to be added to `config.actions_allowed_kinds`. Forget it → propose works, execute 403s
(ActionDisabled).

External go-live gates (Meta App Review / Business verification / pixel+CAPI; Google Ads developer-token
approval / OAuth client / MCC; the Secret-Manager list; the `ENV=prod`/`AUTH_MODE=jwks`/`ADS_MODE=live`/
`ACTIONS_ENABLED=true`/`PLATFORM_OPERATOR_EMAILS` flips) are enumerated in `docs/ADS_INTEGRATION_GOLIVE.md`.
Design rationale in `docs/adr/0009-ads-crm.md`.
