# ADR 0002 — Multi-tenancy via Postgres Row-Level Security

- **Status:** Accepted
- **Date:** 2026-06-02
- **Related:** [0004](0004-defer-streaming-and-external-vector-store.md)

## Context

Each corporate client (tenant) must be **completely** isolated from every other. A single
forgotten `WHERE tenant_id = ...` in application code would be a cross-tenant data breach — the
single most expensive failure mode for this product. We need isolation that does not depend on
every query being written correctly.

Options considered:

1. **Database-per-tenant.** Strongest isolation, but operationally heavy at 50–250 tenants
   (migrations × N, connection-pool sprawl, costly cross-tenant analytics). Revisit only for
   regulated tenants demanding physical separation.
2. **Schema-per-tenant.** Middle ground; still multiplies migration surface and complicates pooled
   connections.
3. **Shared tables + Row-Level Security (RLS).** One schema, one migration path, isolation enforced
   by the database engine regardless of application bugs.

## Decision

Use **shared tables with Postgres RLS**, enforced structurally:

- Every tenant-scoped table has a non-null `tenant_id uuid` and
  `ENABLE ROW LEVEL SECURITY` + `FORCE ROW LEVEL SECURITY`.
- Policy: `USING (tenant_id = current_setting('app.current_tenant')::uuid)` for reads, with a
  matching `WITH CHECK` on writes.
- The application opens a transaction and runs `SET LOCAL app.current_tenant = '<uuid>'`, derived
  from the **validated JWT**, before any query in that request.
- The application connects as **`app_user`** — a role that is **not** a superuser and does **not**
  hold `BYPASSRLS`. Superusers and `BYPASSRLS` roles ignore policies, so the runtime role must be
  neither. Migrations (which create roles and policies) run as `postgres` via a *separate*
  connection string (`MIGRATION_DATABASE_URL`).
- `tenant_id` defaults to `current_setting('app.current_tenant')::uuid` so application code cannot
  accidentally write a row under the wrong tenant.

This maps cleanly to **Supabase** (managed Postgres with RLS as a first-class concept) and to
**Cloud SQL**.

## Consequences

- A missing `WHERE tenant_id` clause is no longer a breach — the engine filters rows.
- The split between the runtime role and the migration role is load-bearing. CI asserts `app_user`
  is not a superuser and lacks `BYPASSRLS`.
- The guarantee is **tested**: `tests/test_rls_isolation.py` seeds two tenants and proves Tenant B
  cannot read Tenant A's rows under the runtime role.
- Connection pooling must reset `app.current_tenant` per checkout. We use `SET LOCAL` inside a
  transaction so it auto-clears on commit/rollback — no leakage across pooled connections.
