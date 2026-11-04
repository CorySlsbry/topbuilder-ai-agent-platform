-- 0025_event_sync.sql
-- Universal event-detection -> auto-act spine (ADR 0010). Adds the durable change-detection cursor,
-- a poison-event dead-letter, and the QBO realmId->tenant map; extends event_queue with retry/backoff.
-- Reuses the existing event_queue inbox + its (tenant_id, source, external_id) dedupe (migration 0017):
-- producers now always supply a NON-NULL natural key, so the partial-unique dedupe never bypasses.

-- 1) Per-(tenant, source, entity) durable resume point — the poll-backbone completeness guarantee.
--    cursor_token holds whichever resume primitive the source uses: ST /export `continueFrom`, a QBO
--    CDC `changedSince` timestamp, or a `modifiedOn` watermark for the modified-since fallback.
CREATE TABLE IF NOT EXISTS sync_cursor (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE
                    DEFAULT NULLIF(current_setting('app.current_tenant', true), '')::uuid,
  source          text NOT NULL,            -- servicetitan | quickbooks
  entity          text NOT NULL,            -- bill | invoice | payment | po_receipt | attachment | ...
  cursor_token    text,                     -- continueFrom | changedSince | modifiedOn watermark (null = from origin)
  cadence_seconds integer NOT NULL DEFAULT 900,
  last_run_at     timestamptz,
  last_status     text NOT NULL DEFAULT 'idle',   -- idle | ok | error
  last_error      text,
  updated_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, source, entity)
);
ALTER TABLE sync_cursor ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_cursor FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON sync_cursor;
CREATE POLICY tenant_isolation ON sync_cursor
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);
GRANT SELECT, INSERT, UPDATE, DELETE ON sync_cursor TO app_user;

-- 2) Poison-event quarantine: an event that fails routing/propose past the retry ceiling lands here
--    (not back to pending) so it can never head-of-line block a tenant's drain. Operator-replayable.
CREATE TABLE IF NOT EXISTS sync_dead_letter (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE
                 DEFAULT NULLIF(current_setting('app.current_tenant', true), '')::uuid,
  event_id     uuid,                        -- the originating event_queue row (may be purged)
  source       text NOT NULL,
  event_type   text NOT NULL,
  external_id  text,
  payload      jsonb NOT NULL DEFAULT '{}'::jsonb,
  attempts     integer NOT NULL DEFAULT 0,
  last_error   text,
  dead_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_sync_dead_letter_tenant ON sync_dead_letter (tenant_id, dead_at DESC);
ALTER TABLE sync_dead_letter ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_dead_letter FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON sync_dead_letter;
CREATE POLICY tenant_isolation ON sync_dead_letter
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);
GRANT SELECT, INSERT, UPDATE, DELETE ON sync_dead_letter TO app_user;

-- 3) QBO realmId -> tenant map (+ encrypted refresh token). The QBO webhook/CDC paths resolve the
--    tenant from the VERIFIED realmId, never a session. Tenant-scoped for normal use; an operator
--    SELECT policy lets the (session-less) webhook resolve realmId->tenant via operator_session().
CREATE TABLE IF NOT EXISTS qbo_connection (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE
                      DEFAULT NULLIF(current_setting('app.current_tenant', true), '')::uuid,
  realm_id          text NOT NULL,
  refresh_token_enc text,                   -- encrypted via app/crypto.py (never plaintext)
  connected_at      timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (realm_id)
);
ALTER TABLE qbo_connection ENABLE ROW LEVEL SECURITY;
ALTER TABLE qbo_connection FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON qbo_connection;
CREATE POLICY tenant_isolation ON qbo_connection
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);
-- Operator read-only: the session-less QBO webhook resolves realmId->tenant before it can scope.
DROP POLICY IF EXISTS operator_read ON qbo_connection;
CREATE POLICY operator_read ON qbo_connection
  FOR SELECT
  USING (current_setting('app.operator', true) = 'on');
GRANT SELECT, INSERT, UPDATE, DELETE ON qbo_connection TO app_user;

-- 4) event_queue: retry/backoff columns for the drain dead-letter policy (a crashed worker must not
--    strand a row 'pending' forever — the drainer bounds attempts and quarantines poison events).
ALTER TABLE event_queue ADD COLUMN IF NOT EXISTS retry_count integer NOT NULL DEFAULT 0;
ALTER TABLE event_queue ADD COLUMN IF NOT EXISTS next_attempt_at timestamptz;
