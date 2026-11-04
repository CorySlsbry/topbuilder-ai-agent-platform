-- 0007_agent_policies.sql
-- Per-agent autonomy switch (Operating Layer): off | hitl | auto. One row per (tenant, agent).
-- `auto` = autonomous-with-undo (system approves + executes on propose); `hitl` = propose -> human
-- approve -> execute; `off` = advisory only (no writes). Default when no row exists is 'hitl'.

CREATE TABLE IF NOT EXISTS agent_policies (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE
                DEFAULT NULLIF(current_setting('app.current_tenant', true), '')::uuid,
  agent       text NOT NULL,
  mode        text NOT NULL DEFAULT 'hitl',   -- off | hitl | auto
  updated_by  uuid,
  updated_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, agent)
);

ALTER TABLE agent_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_policies FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON agent_policies;
CREATE POLICY tenant_isolation ON agent_policies
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

GRANT SELECT, INSERT, UPDATE, DELETE ON agent_policies TO app_user;
