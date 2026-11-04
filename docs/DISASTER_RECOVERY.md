# Disaster Recovery — RTO / RPO, backups, and validation

Documents Top Builder AI's recovery objectives, the backup mechanisms behind them, the restore
procedure, and the most recent validation exercise. Written to answer the Procore Marketplace Partner
Application's DR question truthfully — the targets below are backed by mechanisms that exist today.

## Recovery objectives (this integration)

| Objective | Target | Basis |
|---|---|---|
| **RPO** (max data loss) | **≤ 24 hours** today; **≤ 5 minutes** at go-live | Supabase automated **daily** backups today; Point-in-Time Recovery (PITR, ~2-minute WAL granularity) enabled with real customer data. |
| **RTO** (max downtime) | **≤ 4 hours** | Stateless API/web restore from immutable Artifact Registry images (minutes) + database restore from the latest backup/PITR. |

The platform is **advisory-by-default and pre-launch (no real customer data in production yet)**, so a
recovery event today loses only regenerable demo/fixture data. The objectives above are the committed
targets for when live customer data is onboarded.

## What we recover, and from where

- **Primary database** — Supabase Postgres 17 (`topbuilder-ai-agents`, ref `zoprshhdvvyhbnltttyt`,
  AWS `us-east-2`). Encrypted at rest (AES-256). Supabase takes **automated daily backups**; PITR is a
  one-click add-on enabled before live customer data.
- **Application (API / dashboard / landing / booking)** — stateless Cloud Run services. Recovery = redeploy
  the last-known-good **immutable image** from Artifact Registry (`us-central1-docker.pkg.dev/...`). No state
  lives in the containers.
- **Secrets** — Secret Manager (versioned, AES-256 at rest). Recovered with the project, not the database.
- **Object/derived data** — none that is not reproducible from the database + source.

## Restore procedure (RTO path)

1. **Assess** — identify the failure (DB corruption/loss, region issue, bad deploy) and the target recovery point.
2. **Database** — restore from the latest Supabase backup (or PITR to a timestamp) into the project (or a new
   project, then repoint). Verify with the recovery-point checks below.
3. **Application** — redeploy each Cloud Run service from its last-good Artifact Registry image
   (`gcloud run deploy <svc> --image <repo>:<sha>`). Point `DATABASE_URL` at the restored DB.
4. **Verify** — `/health` + `/health/db` 200; run the smoke checks; confirm RLS tenant isolation; confirm
   row counts vs. the recovery point.
5. **Resume** — return traffic; record the incident + actual RTO/RPO achieved.

## Backup integrity & recovery-point evidence

A lightweight recovery-point snapshot (row counts across all tables) is the integrity oracle for any
restore — compare post-restore counts to the last snapshot. Capture with:

```sql
select relname as table_name, n_live_tup as approx_rows
from pg_stat_user_tables where schemaname='public' order by relname;
```

## Validation log

| Date | Exercise | Result |
|---|---|---|
| **2026-06-14** | Recovery-point capture (33 tables) + **restore rehearsal** (round-tripped `org_people` through a restore target and compared counts) + runbook walkthrough. | **PASS** — `source_rows=38, restored_rows=38, integrity_ok=true`; project `ACTIVE_HEALTHY`; no data-integrity drift. |

> Cadence: re-run the restore rehearsal **quarterly** and before each major release, and switch on PITR
> (tightening RPO to minutes) as part of the live-customer go-live gate (`docs/GO_LIVE_RUNBOOK.md`).
