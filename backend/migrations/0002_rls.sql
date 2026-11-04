-- 0002_rls.sql
-- Enable + FORCE Row-Level Security and attach tenant-isolation policies.
--
-- NULLIF(current_setting('app.current_tenant', true), '')::uuid:
--   * returns NULL when the GUC is unset OR has reverted to '' after a transaction-local SET
--     (Postgres leaves placeholder GUCs as '' rather than truly unset),
--   * so an un-scoped connection sees NO rows (fail-closed) and never errors on ''::uuid.
-- See ADR 0002.

ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenants FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_self ON tenants;
CREATE POLICY tenant_self ON tenants
  USING (id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'users',
    'servicetitan_connections',
    'agent_runs',
    'agent_recommendations',
    'agent_reasoning_logs',
    'audit_events',
    'knowledge_documents',
    'knowledge_chunks'
  ]
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY;', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY;', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I;', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I '
      'USING (tenant_id = NULLIF(current_setting(''app.current_tenant'', true), '''')::uuid) '
      'WITH CHECK (tenant_id = NULLIF(current_setting(''app.current_tenant'', true), '''')::uuid);',
      t
    );
  END LOOP;
END
$$;
