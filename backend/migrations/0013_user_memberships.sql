-- 0013: user_memberships — the auth DIRECTORY table mapping an IdP user (Supabase Auth) to a
-- tenant + role. This is the one table the app must read BEFORE any tenant context exists
-- (the brain's "membership directory" pattern): RLS is ENABLED but the policy is permissive for
-- the app role, because membership resolution happens pre-GUC. It contains routing data only
-- (no customer business data); write access is enforced at the API layer (operator-only + 2FA).

CREATE TABLE IF NOT EXISTS user_memberships (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    auth_user_id  uuid,                          -- Supabase auth.users.id; NULL until first login (email invite)
    email         text NOT NULL,                 -- invite key; matched lower(email)
    tenant_id     uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    role          text NOT NULL DEFAULT 'analyst' CHECK (role IN ('admin', 'analyst', 'viewer')),
    status        text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled')),
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS user_memberships_email_tenant_uq
    ON user_memberships (lower(email), tenant_id);
CREATE INDEX IF NOT EXISTS user_memberships_auth_user_idx ON user_memberships (auth_user_id);

ALTER TABLE user_memberships ENABLE ROW LEVEL SECURITY;

-- Directory policies: resolution runs before a tenant GUC exists, so the app role may read the
-- whole directory; writes go through the operator-only admin API (require_admin + aal2).
DROP POLICY IF EXISTS membership_directory_read ON user_memberships;
CREATE POLICY membership_directory_read ON user_memberships FOR SELECT USING (true);
DROP POLICY IF EXISTS membership_directory_write ON user_memberships;
CREATE POLICY membership_directory_write ON user_memberships FOR ALL USING (true) WITH CHECK (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON user_memberships TO app_user;

-- Seed the platform operator (Cory) as admin on the apex demo tenant under both candidate emails;
-- auth_user_id backfills automatically on first real login.
INSERT INTO user_memberships (email, tenant_id, role)
SELECT e.email, t.id, 'admin'
FROM (VALUES ('cory.salisbury@gmail.com'), ('support@topbuilderai.com')) AS e(email)
CROSS JOIN (SELECT id FROM tenants WHERE slug = 'apex' LIMIT 1) AS t
ON CONFLICT DO NOTHING;
