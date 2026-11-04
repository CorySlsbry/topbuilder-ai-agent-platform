-- 0010_agent_memory.sql
-- The SELF-LEARNING layer (extends the feedback loop, 0009). Every agent run becomes a CASE; every
-- approve/edit/reject/undo becomes its OUTCOME label; edits distill into per-tenant PREFERENCES.
-- Retrieved memory is injected into the LLM NARRATION prompt only — never the deterministic numbers
-- (ADR 0003). Tenant-isolated by RLS; an optional tenant_id-NULL GLOBAL tier holds product-level rules.

-- 1) Case bank (CBR / experience replay) ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent_cases (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE
                     DEFAULT NULLIF(current_setting('app.current_tenant', true), '')::uuid,
  agent            text NOT NULL,
  task_type        text NOT NULL DEFAULT 'run',
  run_id           uuid REFERENCES agent_runs(id) ON DELETE SET NULL,
  target_ref       text,                                      -- recommendation/action id, if scoped
  problem_text     text NOT NULL,                             -- the situation (NEVER the computed numbers)
  problem_features jsonb NOT NULL DEFAULT '{}'::jsonb,
  embedding        vector(3072),                              -- matches knowledge_chunks; brute-force kNN
  recommendation_kind    text NOT NULL DEFAULT '',
  recommendation_summary text NOT NULL DEFAULT '',
  outcome          text NOT NULL DEFAULT 'pending',           -- pending|accepted|edited|rejected|undone
  effectiveness    real,                                      -- 1.0 win .. 0.0 loss (NULL while pending)
  edit_cost        real,                                      -- normalized token-Levenshtein when edited
  model_version    text,
  created_at       timestamptz NOT NULL DEFAULT now(),
  resolved_at      timestamptz
);
CREATE INDEX IF NOT EXISTS idx_agent_cases_tenant_agent ON agent_cases (tenant_id, agent, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_cases_run ON agent_cases (run_id);

-- 2) Learned preferences (CIPHER — human-readable, per-tenant, quorum-gated) ----------------------
CREATE TABLE IF NOT EXISTS agent_preferences (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        uuid REFERENCES tenants(id) ON DELETE CASCADE   -- NULL allowed = GLOBAL tier
                     DEFAULT NULLIF(current_setting('app.current_tenant', true), '')::uuid,
  agent            text NOT NULL,
  task_type        text,
  preference_text  text NOT NULL,
  embedding        vector(3072),
  support_count    integer NOT NULL DEFAULT 1,                -- corroborating cases (quorum guard)
  helpful_count    integer NOT NULL DEFAULT 0,
  harmful_count    integer NOT NULL DEFAULT 0,
  status           text NOT NULL DEFAULT 'quarantined',       -- quarantined|active|retired|superseded
  superseded_by    uuid REFERENCES agent_preferences(id) ON DELETE SET NULL,
  approved_by      uuid,
  last_confirmed_at timestamptz NOT NULL DEFAULT now(),
  created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_agent_preferences_tenant_agent ON agent_preferences (tenant_id, agent, status);

-- 3) Append-only audit of every learning write (this is an audited product) -----------------------
CREATE TABLE IF NOT EXISTS learning_events (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE
                     DEFAULT NULLIF(current_setting('app.current_tenant', true), '')::uuid,
  agent            text NOT NULL,
  operation        text NOT NULL,                             -- record_case|label|pref_add|pref_update|pref_activate
  target_table     text,
  target_id        uuid,
  rationale        text,
  created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_learning_events_tenant_agent ON learning_events (tenant_id, agent, created_at DESC);

-- RLS: each tenant sees its own rows; preferences additionally expose the tenant_id-NULL GLOBAL tier.
ALTER TABLE agent_cases ENABLE ROW LEVEL SECURITY;  ALTER TABLE agent_cases FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON agent_cases;
CREATE POLICY tenant_isolation ON agent_cases
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

ALTER TABLE agent_preferences ENABLE ROW LEVEL SECURITY;  ALTER TABLE agent_preferences FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON agent_preferences;
CREATE POLICY tenant_isolation ON agent_preferences
  USING (tenant_id IS NULL OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

ALTER TABLE learning_events ENABLE ROW LEVEL SECURITY;  ALTER TABLE learning_events FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON learning_events;
CREATE POLICY tenant_isolation ON learning_events
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

GRANT SELECT, INSERT, UPDATE, DELETE ON agent_cases TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON agent_preferences TO app_user;
GRANT SELECT, INSERT ON learning_events TO app_user;
