-- 0026_lead_role.sql
-- Per-employee approval (ADR 0007 extension): add a 4th membership role, 'lead' — a DEPARTMENT LEAD
-- who can APPROVE/execute/undo/reject writes within their own department (including money/legal
-- ALWAYS_HITL kinds), where a plain 'analyst' can propose but not approve. Authorization keys off the
-- existing Principal.role + Principal.department (resolved from this directory, never the token), so a
-- new enum value is the entire schema change — no new column.
--
-- The 0013 role CHECK is an inline, auto-named constraint. Per the security review we must drop the
-- ACTUAL constraint (whatever Postgres/Supabase named it) — a blind DROP ... IF EXISTS of a guessed
-- name would silently no-op and leave the old (admin|analyst|viewer) CHECK in force, so every
-- role='lead' write would still fail. So: discover the role CHECK by introspection, drop it, recreate.

DO $$
DECLARE
  con_name text;
BEGIN
  -- Find the CHECK constraint on user_memberships that references the `role` column.
  SELECT c.conname INTO con_name
  FROM pg_constraint c
  WHERE c.conrelid = 'user_memberships'::regclass
    AND c.contype = 'c'
    AND pg_get_constraintdef(c.oid) ILIKE '%role%'
  LIMIT 1;

  IF con_name IS NOT NULL THEN
    EXECUTE format('ALTER TABLE user_memberships DROP CONSTRAINT %I', con_name);
  END IF;

  ALTER TABLE user_memberships
    ADD CONSTRAINT user_memberships_role_check
    CHECK (role IN ('admin', 'analyst', 'viewer', 'lead'));
END $$;
