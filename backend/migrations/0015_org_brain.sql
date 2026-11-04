-- 0015: org brain — the seeded enterprise org model (departments + people) behind the
-- Organization Brain view and department-scoped agent permissions (the Zach demo). The roster
-- itself is seeded on first read from app/org/seed.py (the comms/tasks pattern) — this migration
-- ships the schema, the membership department/person link, and the canyonridge demo tenant.

CREATE TABLE IF NOT EXISTS org_departments (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id  uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE
               DEFAULT NULLIF(current_setting('app.current_tenant', true), '')::uuid,
  key        text NOT NULL,
  name       text NOT NULL,
  color      text NOT NULL,
  sort       int NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, key)
);
CREATE INDEX IF NOT EXISTS idx_org_departments_tenant ON org_departments (tenant_id);

CREATE TABLE IF NOT EXISTS org_people (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE
                  DEFAULT NULLIF(current_setting('app.current_tenant', true), '')::uuid,
  department_id uuid NOT NULL REFERENCES org_departments(id) ON DELETE CASCADE,
  full_name     text NOT NULL,
  title         text NOT NULL,
  role_tier     text NOT NULL DEFAULT 'ic' CHECK (role_tier IN ('owner', 'exec', 'manager', 'ic')),
  manager_id    uuid NULL REFERENCES org_people(id) ON DELETE SET NULL,
  email         text NULL,
  ai_context    text NOT NULL DEFAULT '',
  sort          int NOT NULL DEFAULT 0,
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_org_people_tenant ON org_people (tenant_id);

ALTER TABLE org_departments ENABLE ROW LEVEL SECURITY;  ALTER TABLE org_departments FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON org_departments;
CREATE POLICY tenant_isolation ON org_departments
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

ALTER TABLE org_people ENABLE ROW LEVEL SECURITY;  ALTER TABLE org_people FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON org_people;
CREATE POLICY tenant_isolation ON org_people
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

GRANT SELECT, INSERT, UPDATE, DELETE ON org_departments TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON org_people TO app_user;

-- Membership directory gains the department scope + the org-person link (NULL = unrestricted /
-- executive view; resolution stays pre-GUC, see 0013).
ALTER TABLE user_memberships
  ADD COLUMN IF NOT EXISTS department text NULL,
  ADD COLUMN IF NOT EXISTS person_id uuid NULL;

-- The canyonridge demo tenant (IDs MUST match app/demo.py + app/org/seed.py).
INSERT INTO tenants (id, name, slug) VALUES
  ('33333333-3333-3333-3333-333333333333', 'Canyon Ridge Mechanical', 'canyonridge')
ON CONFLICT (id) DO NOTHING;

INSERT INTO tenant_settings (tenant_id, fsm_provider) VALUES
  ('33333333-3333-3333-3333-333333333333', 'servicetitan')
ON CONFLICT (tenant_id) DO NOTHING;
