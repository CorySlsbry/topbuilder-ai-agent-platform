-- 0003_seed_dev.sql
-- Two demo tenants for local dev / the dashboard. Runs as the admin (superuser) connection,
-- which bypasses RLS, so explicit tenant_ids are required.
-- IDs MUST match app/demo.py.

INSERT INTO tenants (id, name, slug) VALUES
  ('11111111-1111-1111-1111-111111111111', 'Apex Mechanical', 'apex'),
  ('22222222-2222-2222-2222-222222222222', 'Summit HVAC',     'summit')
ON CONFLICT (id) DO NOTHING;

INSERT INTO users (id, tenant_id, email, role) VALUES
  ('1a000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'person1@example.com',   'admin'),
  ('2b000000-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222', 'person2@example.com', 'admin')
ON CONFLICT (id) DO NOTHING;

INSERT INTO servicetitan_connections (id, tenant_id, st_tenant_id, mode) VALUES
  ('c1000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'st-apex-001',   'fixture'),
  ('c2000000-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222', 'st-summit-001', 'fixture')
ON CONFLICT (id) DO NOTHING;
