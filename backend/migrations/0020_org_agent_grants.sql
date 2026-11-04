-- 0020: per-person AI-agent grants (managers/directors grant/revoke an individual's agent access
-- on the org sphere) + roster-sync columns on org_people so the org auto-populates as people are
-- hired and fired (dynamic reconcile against the connected provider's employee roster).

-- Roster-sync columns. status drives who shows on the sphere (departed people drop off);
-- external_ref is the provider (ServiceTitan/HR) employee id the reconcile matches on.
ALTER TABLE org_people
  ADD COLUMN IF NOT EXISTS status       text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'departed')),
  ADD COLUMN IF NOT EXISTS external_ref text NULL,
  ADD COLUMN IF NOT EXISTS synced_at    timestamptz NULL;

-- One canonical org_people row per provider employee id → idempotent hire/fire reconcile + webhooks.
CREATE UNIQUE INDEX IF NOT EXISTS uq_org_people_external
  ON org_people (tenant_id, external_ref) WHERE external_ref IS NOT NULL;

-- Per-person agent overrides on top of the department default. mode='grant' adds an agent the
-- department wouldn't normally allow; mode='revoke' removes one it would. One row per (person, agent).
CREATE TABLE IF NOT EXISTS org_person_agent_grants (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id  uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE
               DEFAULT NULLIF(current_setting('app.current_tenant', true), '')::uuid,
  person_id  uuid NOT NULL REFERENCES org_people(id) ON DELETE CASCADE,
  agent_key  text NOT NULL,
  mode       text NOT NULL CHECK (mode IN ('grant', 'revoke')),
  set_by     text NULL,        -- email/subject of the manager who set it (audit)
  set_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, person_id, agent_key)
);
CREATE INDEX IF NOT EXISTS idx_org_grants_person ON org_person_agent_grants (tenant_id, person_id);

ALTER TABLE org_person_agent_grants ENABLE ROW LEVEL SECURITY;
ALTER TABLE org_person_agent_grants FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON org_person_agent_grants;
CREATE POLICY tenant_isolation ON org_person_agent_grants
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

GRANT SELECT, INSERT, UPDATE, DELETE ON org_person_agent_grants TO app_user;
