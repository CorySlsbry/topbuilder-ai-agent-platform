-- 0024: per-run LLM token + cost telemetry on agent_runs.
--   Narration-side only (ADR 0003): these columns meter the LLM that NARRATES a run; they never hold
--   or influence a business figure. NULL when the run used the deterministic template path (no model
--   call) — DISABLE_LLM, no API key, or a narration error that fell back to the template.
--   tokens_in / tokens_out come straight from the Anthropic response.usage; cost_usd is computed from
--   the model price table in app/agents/_telemetry.py. Tenant-scoped by the existing agent_runs RLS
--   policy (migrations/0002_rls.sql) — no new policy needed since the columns live on that table.

ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS tokens_in  integer;
ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS tokens_out integer;
ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS cost_usd   numeric(12,6);
