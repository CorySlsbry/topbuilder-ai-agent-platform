-- 0001_init.sql
-- Extensions, the non-superuser runtime role, schema, and grants.
-- Runs as the admin (superuser) connection. See ADR 0002.

CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS vector;     -- pgvector (RAG-ready columns)

-- Runtime role used by the API. NOT a superuser, NO BYPASSRLS -> RLS is enforced for it.
-- (Password here matches docker-compose's DATABASE_URL; rotate via Secret Manager in prod.)
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_user') THEN
    CREATE ROLE app_user LOGIN PASSWORD 'app_pw';
  END IF;
END
$$;

-- ---------------------------------------------------------------------------
-- Core tenancy
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tenants (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name       text NOT NULL,
  slug       text NOT NULL UNIQUE,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS users (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id  uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE
               DEFAULT NULLIF(current_setting('app.current_tenant', true), '')::uuid,
  email      text NOT NULL,
  role       text NOT NULL DEFAULT 'viewer',
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, email)
);

CREATE TABLE IF NOT EXISTS servicetitan_connections (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE
                 DEFAULT NULLIF(current_setting('app.current_tenant', true), '')::uuid,
  st_tenant_id text,
  mode         text NOT NULL DEFAULT 'fixture',  -- fixture | live
  created_at   timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Agent runs, recommendations, reasoning, audit
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent_runs (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE
                DEFAULT NULLIF(current_setting('app.current_tenant', true), '')::uuid,
  agent       text NOT NULL,                      -- 'workforce' | 'inventory' | 'financial'
  status      text NOT NULL DEFAULT 'pending',    -- pending | running | succeeded | failed
  inputs_hash text,
  horizon_days int,
  started_at  timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz,
  duration_ms int,
  created_by  uuid,
  error       text,
  result      jsonb               -- denormalized snapshot of the returned result for fast reads
);
CREATE INDEX IF NOT EXISTS idx_agent_runs_tenant_started
  ON agent_runs (tenant_id, started_at DESC);

CREATE TABLE IF NOT EXISTS agent_recommendations (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id             uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE
                          DEFAULT NULLIF(current_setting('app.current_tenant', true), '')::uuid,
  run_id                uuid NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
  kind                  text NOT NULL,            -- 'understaffing' | 'overtime'
  payload               jsonb NOT NULL,
  confidence            numeric(4,3),             -- 0.000 - 1.000
  economic_impact_cents bigint,
  created_at            timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_reco_run ON agent_recommendations (run_id);

-- append-only
CREATE TABLE IF NOT EXISTS agent_reasoning_logs (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id  uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE
               DEFAULT NULLIF(current_setting('app.current_tenant', true), '')::uuid,
  run_id     uuid NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
  step       text NOT NULL,
  detail     text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_reason_run ON agent_reasoning_logs (run_id);

-- append-only
CREATE TABLE IF NOT EXISTS audit_events (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id  uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE
               DEFAULT NULLIF(current_setting('app.current_tenant', true), '')::uuid,
  actor      text NOT NULL,
  action     text NOT NULL,
  target     text,
  detail     jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_audit_tenant_created
  ON audit_events (tenant_id, created_at DESC);

-- ---------------------------------------------------------------------------
-- Knowledge base (RAG "Learn" module) — tables now, ingestion in Phase 2
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS knowledge_documents (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE
                DEFAULT NULLIF(current_setting('app.current_tenant', true), '')::uuid,
  agent       text,                               -- which agent this knowledge is scoped to
  source_type text NOT NULL,                       -- csv | xlsx | pdf | url
  source_ref  text NOT NULL,
  uploaded_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS knowledge_chunks (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE
                DEFAULT NULLIF(current_setting('app.current_tenant', true), '')::uuid,
  document_id uuid NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
  content     text NOT NULL,
  embedding   vector(3072),                        -- text-embedding-3-large
  metadata    jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at  timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Grants to the runtime role (table privileges; RLS still constrains rows)
-- ---------------------------------------------------------------------------
GRANT USAGE ON SCHEMA public TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO app_user;
