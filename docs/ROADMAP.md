# Roadmap

This slice ships the secure multi-tenant core + the **Workforce Optimization Agent** end-to-end.
Everything below is *designed-for* but intentionally deferred so the first release is small, secure,
and demoable. Order is indicative, not contractual.

## Phase 2 — second & third agents

- **Inventory & Supply Chain Agent** — truck-stock variance (shrinkage / unbilled materials),
  dynamic reorder thresholds from lead-time + usage velocity, vendor-arbitrage from invoice history.
  Reuses the deterministic-compute + LLM-explains pattern (ADR 0003).
- **Financial Forecasting Agent** — WIP profitability index, 30/60/90 cash-flow projection, margin
  leakage. The calc engine encodes GAAP rules as tested code. Can demo against the **already-connected
  QuickBooks** AR/AP aging data.

## Phase 2 — the "Learn" module (RAG)

- Ingestion pipeline: upload CSV/XLSX/PDF or a URL → parse/clean → chunk (512 tokens, 10% overlap)
  → embed (`text-embedding-3-large`) → store in `knowledge_chunks` (pgvector), tagged with
  `tenant_id`, `source_type`, `agent_assignment`.
- Tenant-scoped retrieval decorates an agent's prompt with a "Vector DB Context Lookup" block.
- Tables already exist; isolation already enforced by RLS (ADR 0002, 0004).

## Phase 3 — live data & scale

- **Live ServiceTitan**: flip `SERVICETITAN_MODE=live`, register the app, store creds in Secret
  Manager. Add webhook receivers (job/appointment/invoice events) → Postgres job queue.
- **Human-in-the-loop approvals**: a signed approval-token service for any future write-back action,
  so "advisory-only" can be relaxed safely and explicitly per action.
- **Streaming backbone** *(only when triggered — ADR 0004)*: Kafka/Redpanda/Kinesis for replayable,
  multi-consumer event streams.
- **External vector store** *(only when triggered — ADR 0004)*: Qdrant/Pinecone, tenant-scoped by
  namespace, if pgvector hits scale/latency limits.

## Hardening backlog (pre-GA)

- IdP integration (Supabase Auth / Auth0 / Entra) replacing the dev JWT issuer.
- Per-tenant rate limits + quota metering (usage-based billing hook).
- Per-tenant encryption keys for stored credentials (envelope encryption via KMS).
- Observability: OpenTelemetry traces across API → graph → DB; per-tenant cost dashboards.
- SOC 2 evidence: the audit log + ADRs are the spine; add access reviews and change management.
