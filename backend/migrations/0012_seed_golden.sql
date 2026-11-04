-- 0012_seed_golden.sql
-- A baseline GLOBAL golden set (one representative case per agent, tenant_id = NULL so every tenant
-- inherits it). Each case pins the authoritative figures a narration MUST keep (must_include) and
-- phrasing it must NOT introduce (must_avoid) — this is the ADR-0003 regression the eval gate runs a
-- candidate rule against. Idempotent (guarded by note='seed'). Admin insert -> tenant_id NULL is allowed.

INSERT INTO golden_cases (tenant_id, agent, situation_text, must_include, must_avoid, note)
SELECT NULL, 'financial',
  'Cash is projected to move from $214,000 today to $128,400 (30d), $96,200 (60d), and $61,750 (90d). '
  || '3 projects show margin leakage totaling ~$48,000. Lowest-margin segment: Service at 12.4%.',
  ARRAY['$128,400', '$61,750', '$48,000', '12.4%'], ARRAY['approximately', 'roughly', 'around'], 'seed'
WHERE NOT EXISTS (SELECT 1 FROM golden_cases WHERE agent='financial' AND tenant_id IS NULL AND note='seed');

INSERT INTO golden_cases (tenant_id, agent, situation_text, must_include, must_avoid, note)
SELECT NULL, 'workforce',
  '4 understaffing risks across HVAC and Plumbing next week; 38 avoidable overtime hours (~$2,280) '
  || 'concentrated on 2 crews.',
  ARRAY['38', '$2,280', '4'], ARRAY['about', 'ballpark', 'give or take'], 'seed'
WHERE NOT EXISTS (SELECT 1 FROM golden_cases WHERE agent='workforce' AND tenant_id IS NULL AND note='seed');

INSERT INTO golden_cases (tenant_id, agent, situation_text, must_include, must_avoid, note)
SELECT NULL, 'inventory',
  '6 SKUs are below reorder point; $4,120 of unbilled materials across 9 jobs; $1,540 in vendor '
  || 'arbitrage savings available this week.',
  ARRAY['6', '$4,120', '$1,540', '9'], ARRAY['approximately', 'roughly'], 'seed'
WHERE NOT EXISTS (SELECT 1 FROM golden_cases WHERE agent='inventory' AND tenant_id IS NULL AND note='seed');

INSERT INTO golden_cases (tenant_id, agent, situation_text, must_include, must_avoid, note)
SELECT NULL, 'booking',
  '8 of 14 inbound intakes qualified; $3,260 in recovered revenue; $2,895 captured after hours across '
  || '7 calls.',
  ARRAY['$3,260', '$2,895', '14'], ARRAY['around', 'about'], 'seed'
WHERE NOT EXISTS (SELECT 1 FROM golden_cases WHERE agent='booking' AND tenant_id IS NULL AND note='seed');

INSERT INTO golden_cases (tenant_id, agent, situation_text, must_include, must_avoid, note)
SELECT NULL, 'routing',
  '12 jobs assigned across 5 technicians; 60 minutes of drive time saved versus the naive plan.',
  ARRAY['12', '5', '60'], ARRAY['approximately', 'roughly'], 'seed'
WHERE NOT EXISTS (SELECT 1 FROM golden_cases WHERE agent='routing' AND tenant_id IS NULL AND note='seed');

INSERT INTO golden_cases (tenant_id, agent, situation_text, must_include, must_avoid, note)
SELECT NULL, 'documents',
  '12 documents processed: 9 filed automatically, 1 routed for e-signature, 2 flagged for a human; '
  || '$2,920 in line items extracted.',
  ARRAY['12', '9', '$2,920'], ARRAY['roughly', 'about'], 'seed'
WHERE NOT EXISTS (SELECT 1 FROM golden_cases WHERE agent='documents' AND tenant_id IS NULL AND note='seed');
