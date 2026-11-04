-- 0023_ads_crm.sql
-- Admin Ads-CRM (ADR 0009): operator-only leads pipeline + ad-platform campaign engine.
--
-- POSTURE: these tables hold Top Builder AI's OWN go-to-market data (leads, ad campaigns, spend) at the
-- PLATFORM-OPERATOR layer. They are NOT tenant/customer data and carry NO tenant_id. Access is gated in
-- two independent layers:
--   (1) APP LAYER  — every /v1/crm + /v1/ads route depends on require_admin (admin role + aal2/2FA) AND
--       the platform-operator email allowlist (PLATFORM_OPERATOR_EMAILS). Non-operators/tenants -> 403.
--   (2) DB LAYER (defense in depth) — RLS grants access ONLY under an operator session: the app opens
--       these via db.operator_session(), which sets `app.operator='on'` (transaction-local). A normal
--       tenant_session (app.current_tenant set, app.operator unset) sees ZERO rows. Fail-closed: the GUC
--       defaults to '' -> policy false -> no access. ENABLE (not FORCE) so migrations (run as the table
--       owner) may seed; the app connects as the non-superuser app_user and IS subject to the policy.
-- Money is integer CENTS everywhere. Enums are text + CHECK (codebase convention, cf. agent_actions).

-- ── operator credential vault (ad-platform OAuth tokens) ──────────────────────────────────────────────
-- Separate from the TENANT vault (tenant_credentials, 0004): these are operator/GTM tokens, not customer
-- tokens. secret_ciphertext uses the SAME AES-256-GCM cipher (app/crypto.py). Add this table to
-- scripts/rotate_credentials.py coverage so key rotation still reaches ad credentials.
CREATE TABLE IF NOT EXISTS operator_credentials (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  provider          text NOT NULL,                       -- 'meta' | 'google_ads'
  external_ref      text,                                -- connected business/account id (non-secret)
  secret_ciphertext text NOT NULL,                       -- AES-256-GCM(json{access_token,refresh_token,...})
  metadata          jsonb NOT NULL DEFAULT '{}'::jsonb,  -- non-secret: scopes, connected_email, expiry
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (provider, external_ref)
);

-- ── CRM: contacts / leads / activities ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS crm_contacts (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email       text,
  phone       text,
  full_name   text,
  company     text,
  title       text,
  meta        jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (email)
);

CREATE TABLE IF NOT EXISTS crm_leads (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  contact_id   uuid REFERENCES crm_contacts(id) ON DELETE CASCADE,
  stage        text NOT NULL DEFAULT 'new'
                 CHECK (stage IN ('new','contacted','booked','demoed','won','lost')),
  source       text NOT NULL DEFAULT 'manual'
                 CHECK (source IN ('meta_ads','google_ads','booking','landing','manual','referral','other')),
  value_cents  bigint NOT NULL DEFAULT 0,
  utm          jsonb NOT NULL DEFAULT '{}'::jsonb,   -- utm_source/medium/campaign/term/content
  ad_ref       jsonb NOT NULL DEFAULT '{}'::jsonb,   -- {platform, campaign_id, ad_id, lead_id, show}
  lost_reason  text,
  owner        text,                                 -- operator handling it (free text / email)
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_crm_leads_stage ON crm_leads (stage, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_crm_leads_contact ON crm_leads (contact_id);

CREATE TABLE IF NOT EXISTS crm_activities (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  lead_id     uuid NOT NULL REFERENCES crm_leads(id) ON DELETE CASCADE,
  kind        text NOT NULL,                         -- 'note'|'stage_change'|'email'|'call'|'booking'|'system'
  body        text,
  detail      jsonb NOT NULL DEFAULT '{}'::jsonb,
  actor       text,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_crm_activities_lead ON crm_activities (lead_id, created_at DESC);

-- ── Ad accounts / templates / campaigns / metrics / conversions ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS ad_accounts (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  platform            text NOT NULL CHECK (platform IN ('meta','google')),
  external_account_id text NOT NULL,
  display_name        text,
  vault_credential_id uuid REFERENCES operator_credentials(id) ON DELETE SET NULL,  -- tokens are NOT here
  status              text NOT NULL DEFAULT 'disconnected'
                        CHECK (status IN ('disconnected','connected','error')),
  metadata            jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),
  UNIQUE (platform, external_account_id)
);

CREATE TABLE IF NOT EXISTS ad_campaign_templates (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  slug           text NOT NULL UNIQUE,
  name           text NOT NULL,
  template_type  text NOT NULL DEFAULT 'trade_show_geofence',
  objective      text NOT NULL,                        -- 'traffic' | 'leads'
  geo_spec       jsonb NOT NULL DEFAULT '{}'::jsonb,    -- {custom_locations:[{lat,long,radius_mi}], location_type}
  targeting_spec jsonb NOT NULL DEFAULT '{}'::jsonb,    -- {interests:[...], age_min, age_max, ...}
  schedule_spec  jsonb NOT NULL DEFAULT '{}'::jsonb,    -- {start_at, end_at, tz}
  budget_spec    jsonb NOT NULL DEFAULT '{}'::jsonb,    -- {daily_cents, lifetime_cap_cents}
  creative_spec  jsonb NOT NULL DEFAULT '{}'::jsonb,    -- {headline, primary_text, description, landing_url, image_ref}
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ad_campaigns (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  template_id          uuid REFERENCES ad_campaign_templates(id) ON DELETE SET NULL,
  ad_account_id        uuid REFERENCES ad_accounts(id) ON DELETE SET NULL,
  platform             text NOT NULL CHECK (platform IN ('meta','google')),
  name                 text NOT NULL,
  status               text NOT NULL DEFAULT 'draft'
                         CHECK (status IN ('draft','paused','active','ended','error')),
  external_campaign_id text,
  external_ids         jsonb NOT NULL DEFAULT '{}'::jsonb,  -- {adset_id, adcreative_id, ad_id, budget_id, ...}
  daily_budget_cents   bigint NOT NULL DEFAULT 0,
  lifetime_cap_cents   bigint NOT NULL DEFAULT 0,
  spend_cents          bigint NOT NULL DEFAULT 0,
  start_at             timestamptz,
  end_at               timestamptz,
  last_synced_at       timestamptz,
  created_at           timestamptz NOT NULL DEFAULT now(),
  updated_at           timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ad_campaigns_status ON ad_campaigns (status, created_at DESC);

CREATE TABLE IF NOT EXISTS ad_metrics (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  campaign_id         uuid NOT NULL REFERENCES ad_campaigns(id) ON DELETE CASCADE,
  day                 date NOT NULL,
  impressions         bigint NOT NULL DEFAULT 0,
  clicks              bigint NOT NULL DEFAULT 0,
  landing_page_views  bigint NOT NULL DEFAULT 0,
  leads               bigint NOT NULL DEFAULT 0,
  spend_cents         bigint NOT NULL DEFAULT 0,
  raw                 jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at          timestamptz NOT NULL DEFAULT now(),
  UNIQUE (campaign_id, day)
);

CREATE TABLE IF NOT EXISTS conversion_syncs (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  lead_id     uuid REFERENCES crm_leads(id) ON DELETE SET NULL,
  platform    text NOT NULL CHECK (platform IN ('meta','google')),
  event_name  text NOT NULL,                          -- 'Schedule'|'Lead'|'Purchase' (meta) / conversion action (google)
  dedupe_key  text NOT NULL,                           -- idempotent: one send per (platform, dedupe_key)
  status      text NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending','sent','failed','skipped')),
  payload     jsonb NOT NULL DEFAULT '{}'::jsonb,      -- PII fields ALREADY SHA-256 hashed (never plaintext)
  error       text,
  created_at  timestamptz NOT NULL DEFAULT now(),
  sent_at     timestamptz,
  UNIQUE (platform, dedupe_key)
);

-- ── RLS: operator-only, fail-closed under app.operator='on' (set by db.operator_session) ──────────────
-- Explicit per-table policies (no DO block) so this is safe regardless of how the migration runner splits
-- statements. app_user (the runtime role) is granted access ONLY when app.operator='on'.

ALTER TABLE operator_credentials ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS operator_only ON operator_credentials;
CREATE POLICY operator_only ON operator_credentials FOR ALL TO app_user
  USING (current_setting('app.operator', true) = 'on')
  WITH CHECK (current_setting('app.operator', true) = 'on');
GRANT SELECT, INSERT, UPDATE, DELETE ON operator_credentials TO app_user;

ALTER TABLE crm_contacts ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS operator_only ON crm_contacts;
CREATE POLICY operator_only ON crm_contacts FOR ALL TO app_user
  USING (current_setting('app.operator', true) = 'on')
  WITH CHECK (current_setting('app.operator', true) = 'on');
GRANT SELECT, INSERT, UPDATE, DELETE ON crm_contacts TO app_user;

ALTER TABLE crm_leads ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS operator_only ON crm_leads;
CREATE POLICY operator_only ON crm_leads FOR ALL TO app_user
  USING (current_setting('app.operator', true) = 'on')
  WITH CHECK (current_setting('app.operator', true) = 'on');
GRANT SELECT, INSERT, UPDATE, DELETE ON crm_leads TO app_user;

ALTER TABLE crm_activities ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS operator_only ON crm_activities;
CREATE POLICY operator_only ON crm_activities FOR ALL TO app_user
  USING (current_setting('app.operator', true) = 'on')
  WITH CHECK (current_setting('app.operator', true) = 'on');
GRANT SELECT, INSERT, UPDATE, DELETE ON crm_activities TO app_user;

ALTER TABLE ad_accounts ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS operator_only ON ad_accounts;
CREATE POLICY operator_only ON ad_accounts FOR ALL TO app_user
  USING (current_setting('app.operator', true) = 'on')
  WITH CHECK (current_setting('app.operator', true) = 'on');
GRANT SELECT, INSERT, UPDATE, DELETE ON ad_accounts TO app_user;

ALTER TABLE ad_campaign_templates ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS operator_only ON ad_campaign_templates;
CREATE POLICY operator_only ON ad_campaign_templates FOR ALL TO app_user
  USING (current_setting('app.operator', true) = 'on')
  WITH CHECK (current_setting('app.operator', true) = 'on');
GRANT SELECT, INSERT, UPDATE, DELETE ON ad_campaign_templates TO app_user;

ALTER TABLE ad_campaigns ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS operator_only ON ad_campaigns;
CREATE POLICY operator_only ON ad_campaigns FOR ALL TO app_user
  USING (current_setting('app.operator', true) = 'on')
  WITH CHECK (current_setting('app.operator', true) = 'on');
GRANT SELECT, INSERT, UPDATE, DELETE ON ad_campaigns TO app_user;

ALTER TABLE ad_metrics ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS operator_only ON ad_metrics;
CREATE POLICY operator_only ON ad_metrics FOR ALL TO app_user
  USING (current_setting('app.operator', true) = 'on')
  WITH CHECK (current_setting('app.operator', true) = 'on');
GRANT SELECT, INSERT, UPDATE, DELETE ON ad_metrics TO app_user;

ALTER TABLE conversion_syncs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS operator_only ON conversion_syncs;
CREATE POLICY operator_only ON conversion_syncs FOR ALL TO app_user
  USING (current_setting('app.operator', true) = 'on')
  WITH CHECK (current_setting('app.operator', true) = 'on');
GRANT SELECT, INSERT, UPDATE, DELETE ON conversion_syncs TO app_user;
