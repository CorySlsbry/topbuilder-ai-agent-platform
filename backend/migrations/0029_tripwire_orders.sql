-- 0029_tripwire_orders.sql
-- Tripwire order capture: three Stripe Payment Links (test mode) sell the low-ticket tripwire
-- products (Margin Leakage X-Ray $97, Collections Sprint $97, Scorecard Trial $27). Stripe POSTs
-- checkout.session.completed to POST /v1/tripwires/stripe/webhook (signature-verified); each paid
-- session lands here exactly once (UNIQUE stripe_session_id + INSERT .. ON CONFLICT DO NOTHING).
--
-- POSTURE: these are Top Builder AI's OWN sales at the PLATFORM-OPERATOR layer, NOT tenant/customer
-- data, so the table carries NO tenant_id — the RLS pattern mirrors 0028_support_requests.sql
-- EXACTLY. Access is fail-closed and gated in two independent layers:
--   (1) APP LAYER  — GET /v1/tripwires/orders requires require_admin (admin role + aal2/2FA) PLUS
--       the PLATFORM_OPERATOR_EMAILS allowlist; the webhook writes via db.operator_session().
--   (2) DB LAYER (defense in depth) — RLS grants access ONLY under an operator session: the app
--       opens these via db.operator_session(), which sets `app.operator='on'` (transaction-local).
--       A normal tenant_session (app.current_tenant set, app.operator unset) sees ZERO rows. The
--       GUC defaults to '' -> policy false -> no access. ENABLE (not FORCE) so the migration owner
--       may seed; the app connects as the non-superuser app_user and IS subject to the policy.

CREATE TABLE IF NOT EXISTS tripwire_orders (
  id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  product_key            text NOT NULL CHECK (product_key IN ('xray','collections_sprint','scorecard_trial')),
  stripe_session_id      text NOT NULL UNIQUE,
  stripe_payment_intent  text,
  stripe_event_id        text,
  email                  text,
  name                   text,
  amount_cents           int,
  currency               text DEFAULT 'usd',
  status                 text NOT NULL DEFAULT 'paid' CHECK (status IN ('paid','refunded','fulfilled')),
  intake                 jsonb NOT NULL DEFAULT '{}',
  crm_synced_at          timestamptz,                       -- set once the Salisbury-CRM sync landed
  created_at             timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_tripwire_orders_product ON tripwire_orders (product_key, created_at DESC);

ALTER TABLE tripwire_orders ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS operator_read ON tripwire_orders;
CREATE POLICY operator_read ON tripwire_orders FOR SELECT TO app_user
  USING (current_setting('app.operator', true) = 'on');
DROP POLICY IF EXISTS operator_write ON tripwire_orders;
CREATE POLICY operator_write ON tripwire_orders FOR ALL TO app_user
  USING (current_setting('app.operator', true) = 'on')
  WITH CHECK (current_setting('app.operator', true) = 'on');
GRANT SELECT, INSERT, UPDATE, DELETE ON tripwire_orders TO app_user;
