-- 0011_learning_governance.sql
-- Phase C/D: GOVERNANCE for the self-learning layer. A learned rule no longer auto-activates at
-- quorum — it becomes a CANDIDATE that must clear a golden-set eval gate + human approval before it
-- goes ACTIVE, and even then it rolls out behind a canary %. Adds the nightly consolidation's
-- outputs (eval runs, drift snapshots) and a bandit-tuned threshold/param store.
-- ADR 0003/0008 still hold: governance only ever touches narration RULES, never a deterministic figure.

-- 1) agent_preferences governance lifecycle -------------------------------------------------------
--    status flow is now: quarantined -> candidate -> active | rejected ; active -> retired|superseded
ALTER TABLE agent_preferences ADD COLUMN IF NOT EXISTS eval_score   real;
ALTER TABLE agent_preferences ADD COLUMN IF NOT EXISTS eval_total   integer NOT NULL DEFAULT 0;
ALTER TABLE agent_preferences ADD COLUMN IF NOT EXISTS eval_passed  integer NOT NULL DEFAULT 0;
ALTER TABLE agent_preferences ADD COLUMN IF NOT EXISTS proposed_by  text NOT NULL DEFAULT 'edit';  -- edit|nightly|cluster
ALTER TABLE agent_preferences ADD COLUMN IF NOT EXISTS reviewed_by  uuid;
ALTER TABLE agent_preferences ADD COLUMN IF NOT EXISTS reviewed_at  timestamptz;
ALTER TABLE agent_preferences ADD COLUMN IF NOT EXISTS rollout_pct  integer NOT NULL DEFAULT 100;  -- canary rollout %
ALTER TABLE agent_preferences ADD COLUMN IF NOT EXISTS activated_at timestamptz;

-- 2) Golden-set regression cases (the eval gate's truth set) --------------------------------------
CREATE TABLE IF NOT EXISTS golden_cases (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id          uuid REFERENCES tenants(id) ON DELETE CASCADE   -- NULL = GLOBAL (product-wide)
                       DEFAULT NULLIF(current_setting('app.current_tenant', true), '')::uuid,
  agent              text NOT NULL,
  situation_text     text NOT NULL,
  situation_features jsonb NOT NULL DEFAULT '{}'::jsonb,
  must_include       text[] NOT NULL DEFAULT '{}',   -- tokens/figures the narrative MUST keep
  must_avoid         text[] NOT NULL DEFAULT '{}',   -- phrases the narrative must NOT contain
  note               text,
  created_by         uuid,
  created_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_golden_agent ON golden_cases (agent);

-- 3) Eval runs (append-only audit of every golden-set evaluation) ----------------------------------
CREATE TABLE IF NOT EXISTS eval_runs (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE
                  DEFAULT NULLIF(current_setting('app.current_tenant', true), '')::uuid,
  preference_id uuid REFERENCES agent_preferences(id) ON DELETE CASCADE,
  agent         text NOT NULL,
  golden_total  integer NOT NULL DEFAULT 0,
  golden_passed integer NOT NULL DEFAULT 0,
  score         real,
  invariant_ok  boolean NOT NULL DEFAULT true,    -- the ADR-0003 figure-preservation invariant held
  verdict       text NOT NULL,                    -- pass | fail
  detail        jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_eval_runs_pref ON eval_runs (preference_id, created_at DESC);

-- 4) Tunable threshold/param store (bandit-tuned knobs — thresholds, NEVER figures) ---------------
CREATE TABLE IF NOT EXISTS learning_params (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid REFERENCES tenants(id) ON DELETE CASCADE   -- NULL = GLOBAL default
                DEFAULT NULLIF(current_setting('app.current_tenant', true), '')::uuid,
  agent       text,                                            -- NULL = all agents
  name        text NOT NULL,                                   -- quorum|edit_threshold|auto_approve_on_eval|...
  value       real NOT NULL,
  updated_by  uuid,
  updated_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, agent, name)
);

-- 5) Drift snapshots (agent-health monitor) -------------------------------------------------------
CREATE TABLE IF NOT EXISTS drift_snapshots (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE
                      DEFAULT NULLIF(current_setting('app.current_tenant', true), '')::uuid,
  agent             text NOT NULL,
  window_days       integer NOT NULL,
  sample_size       integer NOT NULL,
  edit_rate         real,
  reject_rate       real,
  avg_effectiveness real,
  flagged           boolean NOT NULL DEFAULT false,
  created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_drift_agent ON drift_snapshots (tenant_id, agent, created_at DESC);

-- RLS (tenant-scoped; golden_cases + learning_params also expose the NULL global tier on read) ----
ALTER TABLE golden_cases ENABLE ROW LEVEL SECURITY; ALTER TABLE golden_cases FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON golden_cases;
CREATE POLICY tenant_isolation ON golden_cases
  USING (tenant_id IS NULL OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

ALTER TABLE eval_runs ENABLE ROW LEVEL SECURITY; ALTER TABLE eval_runs FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON eval_runs;
CREATE POLICY tenant_isolation ON eval_runs
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

ALTER TABLE learning_params ENABLE ROW LEVEL SECURITY; ALTER TABLE learning_params FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON learning_params;
CREATE POLICY tenant_isolation ON learning_params
  USING (tenant_id IS NULL OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

ALTER TABLE drift_snapshots ENABLE ROW LEVEL SECURITY; ALTER TABLE drift_snapshots FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON drift_snapshots;
CREATE POLICY tenant_isolation ON drift_snapshots
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

GRANT SELECT, INSERT, UPDATE, DELETE ON golden_cases TO app_user;
GRANT SELECT, INSERT ON eval_runs TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON learning_params TO app_user;
GRANT SELECT, INSERT ON drift_snapshots TO app_user;
