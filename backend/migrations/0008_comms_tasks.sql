-- 0008_comms_tasks.sql — Operating Layer front-desk data: communications + tasks. RLS-isolated.

CREATE TABLE IF NOT EXISTS communications (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE
                    DEFAULT NULLIF(current_setting('app.current_tenant', true), '')::uuid,
  channel         text NOT NULL,                 -- call | sms | email | voicemail | web
  direction       text NOT NULL,                 -- inbound | outbound
  contact_name    text,
  contact_phone   text,
  contact_email   text,
  subject         text,
  body            text,
  status          text NOT NULL DEFAULT 'new',   -- new | handled | sent
  occurred_at     timestamptz NOT NULL DEFAULT now(),
  customer_ref    text,
  related_job_ref text,
  agent_handled   boolean NOT NULL DEFAULT false,
  created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_comms_tenant_occurred ON communications (tenant_id, occurred_at DESC);

CREATE TABLE IF NOT EXISTS tasks (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE
                  DEFAULT NULLIF(current_setting('app.current_tenant', true), '')::uuid,
  title         text NOT NULL,
  detail        text,
  department    text NOT NULL DEFAULT 'front_desk',
  status        text NOT NULL DEFAULT 'open',     -- open | in_progress | done
  priority      int  NOT NULL DEFAULT 3,
  source_agent  text,
  related_ref   text,
  assignee_role text,
  due_at        timestamptz,
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_tasks_tenant_created ON tasks (tenant_id, created_at DESC);

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['communications', 'tasks'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY;', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY;', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I;', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I '
      'USING (tenant_id = NULLIF(current_setting(''app.current_tenant'', true), '''')::uuid) '
      'WITH CHECK (tenant_id = NULLIF(current_setting(''app.current_tenant'', true), '''')::uuid);', t);
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON %I TO app_user;', t);
  END LOOP;
END $$;
