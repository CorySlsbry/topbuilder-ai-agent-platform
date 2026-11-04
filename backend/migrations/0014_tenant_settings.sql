-- 0014: tenant_settings — per-tenant platform configuration, starting with the field-system
-- provider the tenant runs (the dynamic multi-provider layer). RLS fail-closed like every tenant
-- table; missing row = defaults (fsm_provider 'servicetitan').

CREATE TABLE IF NOT EXISTS tenant_settings (
    tenant_id     uuid PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE
                  DEFAULT NULLIF(current_setting('app.current_tenant', true), '')::uuid,
    fsm_provider  text NOT NULL DEFAULT 'servicetitan',
    updated_at    timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE tenant_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_settings FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON tenant_settings;
CREATE POLICY tenant_isolation ON tenant_settings
    USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

GRANT SELECT, INSERT, UPDATE ON tenant_settings TO app_user;
