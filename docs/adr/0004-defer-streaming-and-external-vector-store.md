# ADR 0004 — Defer Kafka/Kinesis and the external vector store

- **Status:** Accepted
- **Date:** 2026-06-02
- **Related:** [0002](0002-multitenancy-via-postgres-rls.md)

## Context

The original blueprint specified Apache Kafka / AWS Kinesis for "millions of operational data
points" and Qdrant / Pinecone for embeddings. Both are excellent at scale. Both also add standing
operational cost, a second data boundary to secure, and engineering lead time.

Reality check on the target customer: a service contractor with 50–250 employees generates on the
order of **hundreds to low-thousands of business events per day** (job dispatches, completions,
invoices) — not millions per second. And the document corpus for the "Learn" module (price sheets,
SOPs, vendor catalogs) is thousands to low-millions of chunks per tenant, comfortably within
pgvector's range.

## Decision

For the MVP and early customers:

- **Event ingestion:** ServiceTitan **webhooks → FastAPI → Postgres**, with a durable
  Postgres-backed job queue for async work. No streaming bus.
- **Vectors:** **pgvector** inside the same Postgres, so the RLS boundary from ADR 0002 also
  protects embeddings (one boundary, not two).

We will introduce a streaming backbone (Kafka/Redpanda/Kinesis) and/or a dedicated vector store
(Qdrant/Pinecone) when a concrete trigger fires, **not** preemptively.

## Triggers to revisit

- Sustained ingest > ~1k events/sec, or a need for replayable multi-consumer streams → streaming bus.
- > ~10M vectors per tenant, or p95 ANN latency budgets pgvector can't hit → external vector store
  (kept tenant-scoped by namespace).

## Consequences

- Lower fixed cost and faster time-to-value; healthier margin at the early-customer stage.
- A smaller attack surface and a single isolation boundary to certify.
- The adapter and ingestion interfaces are written so swapping in a streaming source later does not
  touch agent logic.
