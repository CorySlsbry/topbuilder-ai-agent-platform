-- 0021_global_counters_rls.sql
-- Close the Supabase advisor "RLS disabled in public" on global_counters.
--
-- global_counters holds NON-tenant operational metering (per-IP / global rate-limit counters keyed by
-- an opaque string — see 0018). It was created without RLS because it has no tenant column. But it sits
-- in the `public` schema, so without RLS the PostgREST anon/authenticated roles could read/write it.
-- Enable RLS and scope a policy to `app_user` (the role the app connects as): the app keeps full access,
-- and anon/authenticated are denied. ENABLE (not FORCE) leaves the table owner/admin path for migrations.

ALTER TABLE global_counters ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS global_counters_app_rw ON global_counters;
CREATE POLICY global_counters_app_rw ON global_counters
  FOR ALL TO app_user USING (true) WITH CHECK (true);
