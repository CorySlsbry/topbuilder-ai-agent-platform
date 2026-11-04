-- 0009_feedback.sql
-- The feedback / training loop: humans rate, edit, and correct agent output. Corrections are the
-- training signal the agents' reasoning layer learns from (and can be ingested into the Learn/RAG
-- knowledge base per agent). Tenant-isolated by RLS.

CREATE TABLE IF NOT EXISTS agent_feedback (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE
                DEFAULT NULLIF(current_setting('app.current_tenant', true), '')::uuid,
  agent       text NOT NULL,
  run_id      uuid REFERENCES agent_runs(id) ON DELETE SET NULL,
  target_kind text NOT NULL,            -- run | recommendation | action
  target_ref  text,                      -- recommendation/action/doc id the feedback is about
  rating      text NOT NULL,            -- up | down | edit
  correction  text,                      -- the human's corrected output (the training signal)
  note        text,
  created_by  uuid,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_agent_feedback_tenant_agent
  ON agent_feedback (tenant_id, agent, created_at DESC);

ALTER TABLE agent_feedback ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_feedback FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON agent_feedback;
CREATE POLICY tenant_isolation ON agent_feedback
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

GRANT SELECT, INSERT, UPDATE, DELETE ON agent_feedback TO app_user;
