# Architecture

This document explains how a request flows through Top Builder AI and how the Workforce agent is wired.
For the *why* behind each choice, read the [ADRs](adr/).

## Layers

| Layer | Tech | Responsibility |
|---|---|---|
| Edge / UI | Next.js, Tailwind, ECharts | Authenticated dashboard; renders recommendations |
| API | FastAPI | AuthN/Z, tenant context, request orchestration, OpenAPI |
| Agents | LangGraph | Stateful workflow: fetch → analyze → reason → persist |
| Compute | pure Python | Deterministic analytics + confidence (the numbers) |
| Reasoning | Anthropic SDK | Natural-language explanation of the numbers (never computes) |
| Integration | adapter (fixture/live) | Read-only ServiceTitan access behind a typed protocol |
| Data | Postgres + pgvector | Tenant data, audit log, RAG-ready vectors; RLS isolation |

## Request lifecycle (trigger a workforce analysis)

```
POST /v1/agents/workforce/runs
  │
  ├─ 1. security.py verifies the JWT → extracts tenant_id, user_id, role
  │
  ├─ 2. db.py opens a transaction and runs:
  │        SET LOCAL app.current_tenant = '<tenant_id>'
  │      (every subsequent query is now RLS-scoped to this tenant)
  │
  ├─ 3. WorkforceService.run():
  │        a. adapter.get_technicians/appointments/timesheets/...   (read-only)
  │        b. analytics.analyze(...)        → deterministic results + confidence
  │        c. reasoning.explain(...)        → LLM narrative (or template if DISABLE_LLM)
  │        d. repositories persist:
  │              agent_runs            (one row per run, inputs hash, status, timings)
  │              agent_recommendations (understaffing + overtime findings)
  │              agent_reasoning_logs  (the deterministic reasoning chain)
  │              audit_events          (append-only)
  │
  └─ 4. returns the structured AgentRunResult (spec-shaped JSON)
```

## The Workforce agent graph (LangGraph)

```
        ┌──────────┐     ┌───────────┐     ┌──────────┐     ┌──────────┐
        │  fetch   │ ──▶ │  analyze  │ ──▶ │  reason  │ ──▶ │ persist  │
        └──────────┘     └───────────┘     └──────────┘     └──────────┘
         adapter →        pure compute      LLM explains      repositories
         WorkforceData    (deterministic)   the numbers       + audit log
```

State (`WorkforceState`) is a typed dict carrying the tenant context, the fetched `WorkforceData`,
the deterministic `WorkforceAnalysis`, the narrative, and the persisted run id. Each node is thin —
all real logic lives in independently testable modules (`analytics.py`, `confidence.py`,
`reasoning.py`, the repositories), so the graph is orchestration only.

## Data model (this slice)

```
tenants(id, name, slug, created_at)
users(id, tenant_id→tenants, email, role, created_at)              -- RLS
servicetitan_connections(id, tenant_id, st_tenant_id, mode, ...)   -- RLS; secrets via Secret Mgr
agent_runs(id, tenant_id, agent, status, inputs_hash,              -- RLS
           started_at, finished_at, duration_ms, created_by)
agent_recommendations(id, tenant_id, run_id→agent_runs, kind,      -- RLS
           payload jsonb, confidence, economic_impact_cents)
agent_reasoning_logs(id, tenant_id, run_id, step, detail)          -- RLS, append-only
audit_events(id, tenant_id, actor, action, target, detail jsonb,   -- RLS, append-only
           created_at)
knowledge_documents(id, tenant_id, source_type, source_ref, ...)   -- RLS (RAG-ready)
knowledge_chunks(id, tenant_id, document_id, content,              -- RLS (RAG-ready)
           embedding vector(3072), metadata jsonb)
```

`knowledge_documents` / `knowledge_chunks` are created now (with a pgvector column) so the "Learn"
module slots in without a migration reshuffle, but ingestion itself is Phase 2
([roadmap](ROADMAP.md)).

## Where it runs

- **API + Web**: containers on **Cloud Run** (see [DEPLOY_CLOUD_RUN.md](DEPLOY_CLOUD_RUN.md)).
- **Postgres**: **Supabase** (RLS + pgvector native) or **Cloud SQL**. The app needs only a
  connection string and the `app_user`/`postgres` role split.
- **Secrets**: GCP Secret Manager (ServiceTitan creds, JWT secret, Anthropic key).
