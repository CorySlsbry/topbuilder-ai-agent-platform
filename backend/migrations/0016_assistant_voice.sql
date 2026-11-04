-- 0016: in-app assistant + booking-agent phone voice
--   assistant_usage           — per-tenant daily message counter (cost guardrail for the Sonnet loop)
--   email_workflow_overrides  — admin-applied copy for an outbound e-mail sequence (the assistant's
--                               update_email_workflow tool writes here; the Email agent surfaces it
--                               as applied_rewrite on its next run)
--   tenant_settings.booking_voice — which of the phone voices answers this tenant's calls

CREATE TABLE IF NOT EXISTS assistant_usage (
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE
              DEFAULT NULLIF(current_setting('app.current_tenant', true), '')::uuid,
    day       date NOT NULL DEFAULT CURRENT_DATE,
    used      integer NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, day)
);

ALTER TABLE assistant_usage ENABLE ROW LEVEL SECURITY;
ALTER TABLE assistant_usage FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON assistant_usage;
CREATE POLICY tenant_isolation ON assistant_usage
    USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

GRANT SELECT, INSERT, UPDATE ON assistant_usage TO app_user;


CREATE TABLE IF NOT EXISTS email_workflow_overrides (
    tenant_id   uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE
                DEFAULT NULLIF(current_setting('app.current_tenant', true), '')::uuid,
    workflow_id text NOT NULL,
    subject     text NOT NULL,
    preview     text NOT NULL,
    rationale   text NOT NULL DEFAULT '',
    updated_by  text NOT NULL,
    updated_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, workflow_id)
);

ALTER TABLE email_workflow_overrides ENABLE ROW LEVEL SECURITY;
ALTER TABLE email_workflow_overrides FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON email_workflow_overrides;
CREATE POLICY tenant_isolation ON email_workflow_overrides
    USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

GRANT SELECT, INSERT, UPDATE, DELETE ON email_workflow_overrides TO app_user;


ALTER TABLE tenant_settings ADD COLUMN IF NOT EXISTS booking_voice text NOT NULL DEFAULT 'riley';
