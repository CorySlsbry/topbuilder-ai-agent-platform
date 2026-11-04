-- 0004_credentials.sql
-- Encrypted per-tenant credential vault (ServiceTitan / QuickBooks tokens) + idempotency index.

CREATE TABLE IF NOT EXISTS tenant_credentials (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE
                      DEFAULT NULLIF(current_setting('app.current_tenant', true), '')::uuid,
  provider          text NOT NULL,                  -- servicetitan | quickbooks
  secret_ciphertext text NOT NULL,                  -- Fernet-encrypted JSON blob
  metadata          jsonb NOT NULL DEFAULT '{}'::jsonb,
  updated_at        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, provider)
);

ALTER TABLE tenant_credentials ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_credentials FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON tenant_credentials;
CREATE POLICY tenant_isolation ON tenant_credentials
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

GRANT SELECT, INSERT, UPDATE, DELETE ON tenant_credentials TO app_user;

-- idempotency: fast lookup of a prior succeeded run by its deterministic inputs hash
CREATE INDEX IF NOT EXISTS idx_agent_runs_idem
  ON agent_runs (tenant_id, agent, inputs_hash);
