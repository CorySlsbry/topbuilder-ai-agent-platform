-- 0005_event_queue.sql
-- Inbound webhook event queue (ServiceTitan job/appointment/invoice events -> Postgres).
-- A streaming bus replaces this only when volume demands it (ADR 0004).

CREATE TABLE IF NOT EXISTS event_queue (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE
                 DEFAULT NULLIF(current_setting('app.current_tenant', true), '')::uuid,
  source       text NOT NULL,                  -- servicetitan
  event_type   text NOT NULL,
  external_id  text,
  payload      jsonb NOT NULL DEFAULT '{}'::jsonb,
  status       text NOT NULL DEFAULT 'pending', -- pending | processed | failed
  received_at  timestamptz NOT NULL DEFAULT now(),
  processed_at timestamptz,
  error        text
);
CREATE INDEX IF NOT EXISTS idx_event_queue_tenant_status
  ON event_queue (tenant_id, status, received_at DESC);

ALTER TABLE event_queue ENABLE ROW LEVEL SECURITY;
ALTER TABLE event_queue FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON event_queue;
CREATE POLICY tenant_isolation ON event_queue
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

GRANT SELECT, INSERT, UPDATE, DELETE ON event_queue TO app_user;
