-- 0018: generic daily usage counters (cost/abuse guardrails).
--   daily_counters  — PER-TENANT, RLS-forced. Buckets like 'feedback', 'knowledge_ingest'.
--   global_counters — NOT tenant data (operational metering by opaque key: per-IP, global). No RLS;
--                     holds only integer counters keyed by strings, never customer business data.

CREATE TABLE IF NOT EXISTS daily_counters (
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE
              DEFAULT NULLIF(current_setting('app.current_tenant', true), '')::uuid,
    day       date NOT NULL DEFAULT CURRENT_DATE,
    bucket    text NOT NULL,
    used      integer NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, day, bucket)
);
ALTER TABLE daily_counters ENABLE ROW LEVEL SECURITY;
ALTER TABLE daily_counters FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON daily_counters;
CREATE POLICY tenant_isolation ON daily_counters
    USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);
GRANT SELECT, INSERT, UPDATE ON daily_counters TO app_user;


CREATE TABLE IF NOT EXISTS global_counters (
    day    date NOT NULL DEFAULT CURRENT_DATE,
    bucket text NOT NULL,
    used   integer NOT NULL DEFAULT 0,
    PRIMARY KEY (day, bucket)
);
GRANT SELECT, INSERT, UPDATE ON global_counters TO app_user;
