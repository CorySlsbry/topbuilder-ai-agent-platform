-- 0027_outreach_authority.sql
-- Outreach go-live hardening (closes the executor param-trust hole): the authoritative store the
-- send_outreach_email executor resolves compliance facts from, plus the send ledger that makes the
-- warm-up daily cap enforceable. Proposer-supplied consent/country/suppression params are now IGNORED
-- at execute time — facts come ONLY from these tables (unresolvable contact => HELD, fail-safe).

-- 1) The authoritative contact facts (server-written, never from action params).
CREATE TABLE IF NOT EXISTS outreach_contacts (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE
                      DEFAULT NULLIF(current_setting('app.current_tenant', true), '')::uuid,
  email_normalized  text NOT NULL,               -- lower(trim(email))
  country           text,                        -- ISO-2; NULL = unknown (cold send will be HELD)
  consent           boolean NOT NULL DEFAULT false,
  consent_basis     text,                        -- e.g. 'opt_in_form:2026-06-01', 'existing_customer'
  bounced           boolean NOT NULL DEFAULT false,
  unsubscribed      boolean NOT NULL DEFAULT false,
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, email_normalized)
);
ALTER TABLE outreach_contacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE outreach_contacts FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON outreach_contacts;
CREATE POLICY tenant_isolation ON outreach_contacts
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);
GRANT SELECT, INSERT, UPDATE, DELETE ON outreach_contacts TO app_user;

-- 2) The suppression list (unsubscribes, hard bounces, manual do-not-contact).
CREATE TABLE IF NOT EXISTS email_suppression (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE
                      DEFAULT NULLIF(current_setting('app.current_tenant', true), '')::uuid,
  email_normalized  text NOT NULL,
  reason            text,                        -- 'unsubscribed' | 'hard_bounce' | 'manual' | ...
  created_at        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, email_normalized)
);
ALTER TABLE email_suppression ENABLE ROW LEVEL SECURITY;
ALTER TABLE email_suppression FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON email_suppression;
CREATE POLICY tenant_isolation ON email_suppression
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);
GRANT SELECT, INSERT, UPDATE, DELETE ON email_suppression TO app_user;

-- 3) The send ledger: what actually left, per sending subdomain — the warm-up cap's source of truth
--    (sent-today counts + the subdomain's first-send date give its age).
CREATE TABLE IF NOT EXISTS outreach_sends (
  id                        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                 uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE
                              DEFAULT NULLIF(current_setting('app.current_tenant', true), '')::uuid,
  contact_email_normalized  text NOT NULL,
  subdomain                 text NOT NULL,       -- the sending domain, e.g. send.topbuilderai.com
  action_id                 uuid,                -- the agent_actions row that authorized this send
  sent_at                   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_outreach_sends_subdomain ON outreach_sends (tenant_id, subdomain, sent_at DESC);
ALTER TABLE outreach_sends ENABLE ROW LEVEL SECURITY;
ALTER TABLE outreach_sends FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON outreach_sends;
CREATE POLICY tenant_isolation ON outreach_sends
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);
GRANT SELECT, INSERT, UPDATE, DELETE ON outreach_sends TO app_user;
