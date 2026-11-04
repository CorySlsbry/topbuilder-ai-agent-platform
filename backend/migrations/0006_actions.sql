-- 0006_actions.sql
-- Human-approved action execution (ADR 0007): the gated write path.
-- An action is PROPOSED by a run, APPROVED by a human (admin), then EXECUTED (only if ACTIONS_ENABLED).
-- Tenant-isolated by RLS, idempotent by (tenant_id, idempotency_key), every transition audited.

CREATE TABLE IF NOT EXISTS agent_actions (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE
                    DEFAULT NULLIF(current_setting('app.current_tenant', true), '')::uuid,
  run_id          uuid REFERENCES agent_runs(id) ON DELETE SET NULL,  -- provenance (the run that proposed it)
  agent           text NOT NULL,                       -- 'booking' | 'financial' | ...
  kind            text NOT NULL,                        -- 'book_appointment' | 'categorize_transaction' | ...
  status          text NOT NULL DEFAULT 'proposed',     -- proposed|approved|executing|executed|failed|rejected
  params          jsonb NOT NULL DEFAULT '{}'::jsonb,    -- the typed write payload
  idempotency_key text NOT NULL,                         -- stable per logical action; blocks duplicates
  result          jsonb,                                 -- executor result (external ref, etc.)
  error           text,
  requested_by    uuid,                                  -- who/what proposed it
  approved_by     uuid,                                  -- the human approver (NULL until approved)
  approved_at     timestamptz,
  executed_at     timestamptz,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_agent_actions_tenant_created ON agent_actions (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_actions_run ON agent_actions (run_id);

-- RLS: same fail-closed tenant isolation as every other tenant table (see 0002_rls.sql).
ALTER TABLE agent_actions ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_actions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON agent_actions;
CREATE POLICY tenant_isolation ON agent_actions
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

GRANT SELECT, INSERT, UPDATE, DELETE ON agent_actions TO app_user;
