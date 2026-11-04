-- 0019: distinct-author quorum for learned preferences (SEC-3 anti-poisoning).
-- Quorum must count DISTINCT corroborating users, not raw edit volume — otherwise one actor
-- submitting the same correction 3x can promote a poisoned rule to 'candidate' alone. Each distinct
-- supporter is recorded here; agent_preferences.support_count is reconciled to COUNT(DISTINCT).

CREATE TABLE IF NOT EXISTS agent_preference_supporters (
    tenant_id     uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE
                  DEFAULT NULLIF(current_setting('app.current_tenant', true), '')::uuid,
    preference_id uuid NOT NULL REFERENCES agent_preferences(id) ON DELETE CASCADE,
    supporter     text NOT NULL,             -- the corroborating user id (or 'system' for nightly proposals)
    created_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, preference_id, supporter)
);
ALTER TABLE agent_preference_supporters ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_preference_supporters FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON agent_preference_supporters;
CREATE POLICY tenant_isolation ON agent_preference_supporters
    USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);
GRANT SELECT, INSERT, DELETE ON agent_preference_supporters TO app_user;
