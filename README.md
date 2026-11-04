# topbuilder ai agent platform

> **Portfolio snapshot.** A sanitized, history-free copy of a private repository, published to show the work.
> Credentials, customer and lead data, internal notes and third-party material were removed, and real client
> and people names were replaced with fictional ones, so this copy is not meant to run as-is.

- **What it is:** An enterprise multi-agent decision platform for ServiceTitan contractors (50 to 250+ employees).
- **Stack:** Next.js, React, Tailwind, Supabase, Vitest, Playwright, Remotion, FastAPI, LangGraph, SQLAlchemy, asyncpg, pytest, Pydantic, Anthropic Claude API
- **Languages:** Python, HTML, TypeScript, SQL
- **Private repo history:** 156 commits, 2026-06-06 to 2026-09-05
- **This snapshot:** 1,081 files, 124 test files
- **Built by:** Cory Salisbury, with Claude Code

_All rights reserved. Shared for portfolio review only; no license is granted to copy, modify or redistribute this code._

---

**An enterprise multi-agent decision platform for ServiceTitan contractors (50–250+ employees).**

Top Builder AI ingests operational data from ServiceTitan and turns it into board-grade
recommendations: where you'll be **understaffed** two to four weeks out, which technicians are
drifting into **avoidable overtime**, and what each gap costs in dollars — every figure backed by a
**deterministic reasoning chain** and a **confidence score**, every run written to an
**append-only audit log**, every tenant's data sealed off by **Postgres Row-Level Security**.

> **Product.** Top Builder AI — the contractor AI back-office (topbuilderai.com). ("FieldOps IQ" was
> the earlier placeholder codename.)

---

## What's built

A production-leaning, multi-tenant platform — **121 tests green** (unit, property, and DB integration
incl. RLS isolation, idempotency, vault, webhooks, RAG):

- ✅ **Secure multi-tenant core** — pluggable JWKS/OIDC auth (dev issuer local-only), tenant-scoped
  DB sessions, Postgres RLS enforced by a non-superuser role (fail-closed), append-only audit log.
- ✅ **Three agents** — **Workforce**, **Financial** (GAAP percentage-of-completion), and
  **Inventory & Supply Chain**. Each: fetch → **deterministic analytics** → **LLM explains** →
  persist, orchestrated with LangGraph. The LLM never does arithmetic.
- ✅ **Adapters** — ServiceTitan (workforce/inventory) + QuickBooks (financial), each a fixture
  backend today and a live OAuth2 backend ready to switch on.
- ✅ **RAG "Learn" module** — upload CSV/MD/HTML/URL → chunk → embed (offline hashing or OpenAI) →
  pgvector; agent + tenant scoped semantic search. SSRF-guarded URL ingestion.
- ✅ **Encrypted credential vault** (Fernet) + **idempotent runs** (dedupe by inputs hash).
- ✅ **Signature-verified webhooks** → Postgres event queue.
- ✅ **Production hardening** — error envelope, structured logging, security headers, env CORS +
  trusted hosts, rate limiting, graceful lifespan. CI pipeline + [production-readiness audit](docs/PRODUCTION_READINESS.md).
- ✅ **Premium 3-agent dashboard** (Next.js + ECharts) and **Cloud Run-ready** containers.

### API surface
`/health` · `/auth/dev-token` · `/v1/agents/{workforce|financial|inventory}/runs[/latest|/{id}]` ·
`/v1/knowledge/{agent}/{documents|search}` · `/v1/connections` · `/v1/webhooks/servicetitan/{tenant}`
· `/v1/webhooks/events` — full OpenAPI at `/docs`.

See [`docs/ROADMAP.md`](docs/ROADMAP.md) and [`docs/PRODUCTION_READINESS.md`](docs/PRODUCTION_READINESS.md)
for what remains before GA (live-tenant mappings, per-tenant KMS, IdP wiring, deploy).

---

## Architecture (this slice)

```
                          ┌──────────────────────────┐
        Admin (Tenant A)  │   Next.js dashboard       │   premium UI, ECharts
        ───────────────▶  │   (Cloud Run / Vercel)    │
                          └────────────┬─────────────┘
                                       │ JWT (tenant claim), HTTPS
                                       ▼
                          ┌──────────────────────────┐
                          │   FastAPI  (Cloud Run)    │
                          │  ┌────────────────────┐   │
                          │  │ LangGraph Workforce │  │   fetch → analyze → reason → persist
                          │  │ agent               │  │
                          │  └─────┬──────────┬────┘   │
                          │        │          │        │
                 read-only │        ▼          ▼        │ SET LOCAL app.current_tenant
            ServiceTitan ◀─┼─ adapter   deterministic   │
            (fixture/live) │            analytics engine │
                          └────────────┬─────────────┘
                                       │ as app_user (RLS enforced)
                                       ▼
                          ┌──────────────────────────┐
                          │ Postgres + pgvector       │   tenants, agent_runs,
                          │ (Supabase / Cloud SQL)    │   recommendations, audit_events,
                          │ Row-Level Security        │   knowledge_chunks (RAG-ready)
                          └──────────────────────────┘
```

Why these choices (full rationale in [`docs/adr/`](docs/adr/)):

| Decision | Rationale |
|---|---|
| **Postgres RLS for isolation** | One enforced boundary for rows *and* (future) vectors. App connects as a non-superuser role so RLS can't be bypassed. |
| **pgvector, not Pinecone/Qdrant (yet)** | Co-locate embeddings with tenant data → the same RLS boundary protects them. External vector DB is a scale optimization, not a day-one dependency. |
| **Deterministic math, LLM explains** | "Zero calculation drift / GAAP-aligned" is incompatible with an LLM doing arithmetic. Numbers come from tested code; the model narrates. |
| **Advisory-only, structurally** | The adapter exposes read-only ServiceTitan scopes. Write-back is out of scope by construction, not by prompt. |
| **No Kafka yet** | A 50–250-employee contractor doesn't emit millions of events/sec. Webhooks → API → Postgres covers it; a streaming bus is Phase 2. |

---

## Quickstart

### Option A — full stack with Docker (closest to production)

```bash
cp .env.example .env          # optionally add ANTHROPIC_API_KEY; leave DISABLE_LLM=1 to skip the LLM
docker compose up --build
# API  → http://localhost:8000  (OpenAPI docs at /docs)
# Web  → http://localhost:3000
```

The `api` container runs database migrations on boot (creating the `app_user` role, schema, RLS
policies, and two demo tenants), then serves.

### Option B — run the tested core right now, no Docker

The analytics engine is pure Python with no database or network dependency:

```bash
cd backend
python -m venv .venv && .venv\Scripts\activate      # PowerShell:  .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest -q                                            # unit + property tests, all green
```

### Local notes

- **Frontend → API base URL:** the dashboard reads `NEXT_PUBLIC_API_BASE_URL` (default
  `http://localhost:8000`). For local dev, create `frontend/.env.local` with the API's address,
  e.g. `NEXT_PUBLIC_API_BASE_URL=http://localhost:8088`.
- **Port already in use?** Override the published host ports:
  `API_HOST_PORT=8088 WEB_HOST_PORT=3001 docker compose up`.
- **DB integration tests** (RLS isolation) run only when opted in:
  `RUN_DB_TESTS=1 DATABASE_URL=… APP_PG_DSN=… pytest -q` (see `backend/tests/conftest.py`).

---

## Project layout

```
.
├── docker-compose.yml          # local stack: db + api + web
├── .env.example                # the full environment contract
├── docs/
│   ├── ARCHITECTURE.md         # how the pieces fit + data flow
│   ├── ROADMAP.md              # what's deferred and why
│   └── adr/                    # architecture decision records (buyer-review ready)
├── backend/
│   ├── pyproject.toml
│   ├── Dockerfile
│   ├── migrations/             # raw SQL: schema, RLS policies, app_user role, dev seed
│   ├── scripts/migrate.py      # transparent migration runner
│   ├── app/
│   │   ├── config.py           # pydantic-settings
│   │   ├── db.py               # async engine + tenant-scoped sessions (SET LOCAL)
│   │   ├── security.py         # JWT verify + tenant context
│   │   ├── api/                # FastAPI routes
│   │   ├── integrations/servicetitan/   # adapter: protocol + fixture + live + fixtures/
│   │   ├── agents/workforce/   # analytics, confidence, graph, prompts, schemas, service
│   │   └── repositories/       # persistence (runs, recommendations, audit)
│   └── tests/                  # unit, property, and RLS-isolation integration tests
└── frontend/                   # Next.js + Tailwind + ECharts dashboard
```

---

## Security model (the short version)

1. **Authentication** — every request carries a JWT. The tenant id lives in the token, signed by
   the IdP (HS256 dev issuer here; swap to Supabase/Auth0 JWKS in prod — see `app/security.py`).
2. **Tenant context** — each request opens a transaction and runs
   `SET LOCAL app.current_tenant = '<tenant-uuid>'` before any query.
3. **Row-Level Security** — every tenant-scoped table has
   `USING (tenant_id = current_setting('app.current_tenant')::uuid)`. The app connects as
   `app_user`, which is **not** a superuser and does **not** have `BYPASSRLS`, so the policy is
   always in force. Migrations (which must create policies) run as `postgres`.
4. **Advisory-only** — the ServiceTitan adapter requests read scopes. There is no write-back path
   in this slice.
5. **Auditability** — every agent run, its inputs hash, the deterministic outputs, and the
   reasoning chain are written to append-only tables.

The RLS guarantee is **tested**: `tests/test_rls_isolation.py` proves Tenant B cannot read
Tenant A's rows. See [`docs/adr/0002`](docs/adr/0002-multitenancy-via-postgres-rls.md).

---

## Deploying to Cloud Run

See [`docs/DEPLOY_CLOUD_RUN.md`](docs/DEPLOY_CLOUD_RUN.md) for the full runbook (build, push,
secrets via Secret Manager, Supabase/Cloud SQL wiring, and the migration job).

---

## Testing

```bash
cd backend
pytest -q                       # everything; RLS integration tests self-skip without TEST_DATABASE_URL
pytest -q -m "not integration"  # pure unit + property tests only
```

The project follows the house rules in `CLAUDE.md`: TDD for the analytics core, property-based
tests for math invariants, and integration tests for anything touching the database.
