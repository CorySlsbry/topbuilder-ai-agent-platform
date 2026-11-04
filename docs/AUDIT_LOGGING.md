# Audit Logging — Top Builder AI

How the platform records who did what, where it lives, how long it is kept, who can read it, and why
it cannot be silently altered. This is the control behind the Procore requirement: *"audit logs of all
read/write, retention, access, tamper-protection."*

## 1. What is audited

Every state-changing and sensitive-read operation writes an immutable `audit_events` row. The trail
spans the whole platform:

- **Agent runs (read + write).** Each of the six agents (Workforce, Financial, Inventory, Booking,
  Routing, Documents) records the run it executed against ServiceTitan / QuickBooks / voice-intake
  data, the recommendation produced, and the principal that triggered it.
- **The human-approved write path (ADR-0007).** Every `propose → approve → execute` step on an
  action is audited — proposal, the admin who approved (role + `aal2`), execution, idempotent
  re-execution, and any `undo` / compensation. This is the gated path that lets agents act with
  oversight, so each transition is on the record.
- **Admin / operator operations.** Membership administration, credential-vault writes (connections),
  learning-rule approvals, and Email/SEO agent operations — the platform-operator and tenant-admin
  surfaces — are audited with the acting principal.
- **Knowledge ingestion and assistant tool calls** that touch tenant data or invoke privileged tools
  flow through the same `insert_audit` helper.

Each row is `(id, tenant_id, actor, action, target, detail jsonb, created_at)` — *actor* = the
principal (operator / admin / agent / system), *action* = the verb, *target* = the affected object,
*detail* = structured context, *created_at* = server time.

## 2. Where it lives

- **Table:** `audit_events` in the platform Postgres (Supabase project `zoprshhdvvyhbnltttyt`).
  Defined in migration `0001_init.sql` and explicitly designed append-only.
- **Writer:** the single chokepoint `insert_audit(...)` in `backend/app/repositories/runs.py` — the
  only path that writes the trail. It runs inside the per-request `app.db.tenant_session(tenant_id)`,
  so every audit row is automatically stamped with the caller's `tenant_id`.
- **Index:** `idx_audit_tenant_created (tenant_id, created_at DESC)` for fast per-tenant,
  newest-first retrieval.

## 3. Retention

- **Default:** rows are retained indefinitely. The platform never prunes the audit trail in normal
  operation — there is no application code path that deletes or ages out `audit_events`, and (see §5)
  the application database role has **no DELETE privilege** to do so even if asked.
- **If a retention policy is ever adopted** (e.g. a regulated N-year window), pruning runs as the
  table **owner / superuser** under an explicit, scheduled, and itself-audited maintenance job —
  never through the application. Keeping deletion off the app role means retention is a deliberate
  operator decision, not something a runtime bug or injection can trigger.

## 4. Who can access it

- **Tenant isolation (RLS, FORCE, fail-closed).** `audit_events` carries `tenant_id` and the
  `tenant_isolation` policy from `0002_rls.sql`:
  `tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid`. An un-scoped
  connection sees **no rows** (fail-closed). One tenant can never read another tenant's audit trail.
- **Role gate.** Within a tenant, audit reads are an operator / admin concern. Cross-cutting
  governance reads use the existing `require_unrestricted` / `require_admin` dependencies
  (`backend/app/api/deps.py`) — the same operator bar (unrestricted principal, role + `aal2`) used
  for the learning approval queue. Department-scoped logins are refused.
- **No public/anon access.** The app connects as the non-superuser role `app_user`; the PostgREST
  `anon` / `authenticated` roles have no grant on the table.

## 5. Tamper-protection (append-only guarantee)

The trail is **append-only at the database layer**, not merely by convention:

- `audit_events` was created append-only in `0001_init.sql`, but the original blanket
  `GRANT SELECT, INSERT, UPDATE, DELETE ... TO app_user` still let the application role rewrite or
  erase history.
- **Migration `0022_audit_hardening.sql` revokes `UPDATE` and `DELETE` on `audit_events` from
  `app_user`.** The application role can now only `INSERT` and `SELECT`. A compromised app path, a
  bug, or an injection **cannot alter or delete an existing audit row** — the only legal operation is
  appending a new one.
- **Verified safe before revoking:** a full grep of `backend/app` confirmed the application *only*
  INSERTs (`insert_audit`) and SELECTs `audit_events` — there is no UPDATE or DELETE of the trail
  anywhere in the codebase, so the revoke removes a tamper surface without changing any behaviour.
- **RLS is preserved.** The revoke targets table privileges only; the FORCE RLS + tenant-isolation
  policy from `0002` is untouched, so cross-tenant isolation and fail-closed reads still hold.
- **DDL path intact.** REVOKE targets the app role, not the owner, so migrations and any (operator,
  audited) retention job still function.

This gives Procore-grade tamper-evidence: history is structurally immutable to the running
application — anyone reviewing the trail knows rows could only have been added, never edited or
removed by the app.

## 6. Roadmap — cryptographic hash-chaining

Append-only-by-grant proves the *application* cannot tamper, but a sufficiently privileged operator
(owner/superuser) still could in principle. The next hardening step is **hash-chaining** the trail so
*any* alteration — even by a privileged actor — is detectable:

- On each insert, compute `row_hash = H(prev_hash || canonical(row))` and store `row_hash` +
  `prev_hash` columns (a per-tenant or global chain).
- A periodic verifier walks the chain and flags any break; optionally anchor a daily Merkle root in
  an external/WORM store so the chain itself can't be silently rebuilt.
- This turns the guarantee from "the app can't tamper" into "*nobody* can tamper without detection,"
  the strongest tier of audit tamper-evidence. Tracked as a future enhancement; the grant-level
  append-only control in §5 is the current, verified guarantee.
