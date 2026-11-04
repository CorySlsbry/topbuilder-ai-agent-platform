-- 0028_support_requests.sql
-- Operator reporting: capture the operational signals Cory wants to be notified about —
--   new signups, chatbot (assistant) requests, and user-submitted bug / feature / question reports.
--
-- POSTURE: this is Top Builder AI's OWN operational data at the PLATFORM-OPERATOR layer, NOT
-- tenant/customer data, so it carries NO tenant_id — identical to the Ads-CRM tables (ADR 0009).
-- Access is fail-closed and gated in two independent layers:
--   (1) APP LAYER  — GET /v1/support requires require_admin (admin role + aal2/2FA); the notifier
--       fan-out is fire-and-forget best-effort.
--   (2) DB LAYER (defense in depth) — RLS grants access ONLY under an operator session: the app opens
--       these via db.operator_session(), which sets `app.operator='on'` (transaction-local). A normal
--       tenant_session (app.current_tenant set, app.operator unset) sees ZERO rows. The GUC defaults
--       to '' -> policy false -> no access. ENABLE (not FORCE) so the migration owner may seed; the
--       app connects as the non-superuser app_user and IS subject to the policy.

CREATE TABLE IF NOT EXISTS support_requests (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  kind         text NOT NULL CHECK (kind IN ('signup','chatbot','bug','feature','question')),
  name         text,
  email        text,
  message      text,
  source       text,                                 -- 'in_app' | 'assistant' | 'membership' | ...
  meta         jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at   timestamptz NOT NULL DEFAULT now(),
  notified_at  timestamptz                           -- set once the Slack/email fan-out has run
);
CREATE INDEX IF NOT EXISTS idx_support_requests_kind ON support_requests (kind, created_at DESC);

ALTER TABLE support_requests ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS operator_read ON support_requests;
CREATE POLICY operator_read ON support_requests FOR SELECT TO app_user
  USING (current_setting('app.operator', true) = 'on');
DROP POLICY IF EXISTS operator_write ON support_requests;
CREATE POLICY operator_write ON support_requests FOR ALL TO app_user
  USING (current_setting('app.operator', true) = 'on')
  WITH CHECK (current_setting('app.operator', true) = 'on');
GRANT SELECT, INSERT, UPDATE, DELETE ON support_requests TO app_user;
