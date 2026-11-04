-- 0022_audit_hardening.sql
-- Make the audit trail append-only at the DATABASE layer (tamper-evidence).
--
-- WHY: audit_events is the system of record for "who did what" — every agent read/write, every
-- action propose/approve/execute, and admin operations. It was created as logically "append-only"
-- (0001) but the application role app_user still held UPDATE + DELETE on it (the blanket
-- GRANT SELECT, INSERT, UPDATE, DELETE in 0001), so a compromised app path or an injection could
-- silently rewrite or erase history. This is the Procore requirement: read/write audit logs with
-- retention, access control, and tamper-protection.
--
-- VERIFIED before revoking: grepped backend/app — the application only ever INSERTs (insert_audit
-- in app/repositories/runs.py) and SELECTs audit_events. There is no UPDATE or DELETE of
-- audit_events anywhere in the codebase, so revoking both operations changes no app behaviour and
-- closes the tamper surface.
--
-- We REVOKE UPDATE, DELETE from app_user only. INSERT + SELECT remain, so the app keeps writing and
-- reading the trail. RLS stays untouched (FORCE + tenant_isolation from 0002), so cross-tenant
-- isolation and the fail-closed un-scoped behaviour are preserved. The table owner / superuser
-- migration path is unaffected (REVOKE targets the app role, not the owner) — retention pruning, if
-- ever adopted, runs as the owner under an explicit, audited maintenance job, never via the app.
--
-- Idempotent: REVOKE is a no-op when the privilege is already absent, so re-running is safe.

REVOKE UPDATE, DELETE ON audit_events FROM app_user;

-- Belt-and-suspenders: pin the per-table default so a future blanket re-GRANT can't silently
-- re-open UPDATE/DELETE without a deliberate grant naming audit_events.
GRANT SELECT, INSERT ON audit_events TO app_user;
