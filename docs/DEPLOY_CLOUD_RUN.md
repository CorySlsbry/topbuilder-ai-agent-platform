# Deploying to Google Cloud Run

This runbook deploys the **API** (and optionally the **web** dashboard) to Cloud Run, backed by
**Supabase** Postgres (RLS + pgvector native) or **Cloud SQL**.

> Local-first: everything here is validated by `docker compose up` first. Cloud Run runs the same
> image.

## 0. Prerequisites

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT
gcloud services enable run.googleapis.com artifactregistry.googleapis.com \
  cloudbuild.googleapis.com secretmanager.googleapis.com
gcloud artifacts repositories create fieldops --repository-format=docker --location=us-central1
```

## 1. Database

Pick one. The app needs two connection strings (ADR 0002): a **runtime** URL using the
non-superuser `app_user`, and an **admin** URL used only by the migration job.

**Supabase** (recommended — RLS + pgvector are first-class):
1. Create a project; note the connection string.
2. Run `backend/migrations/*` via the migration job below (it creates `app_user`, the schema, and
   the RLS policies). Use the Supabase superuser/`postgres` URL as `MIGRATION_DATABASE_URL`, and an
   `app_user` URL as `DATABASE_URL`.

**Cloud SQL (Postgres 16)**:
```bash
gcloud sql instances create fieldops-pg --database-version=POSTGRES_16 \
  --tier=db-custom-2-7680 --region=us-central1
gcloud sql databases create fieldops --instance=fieldops-pg
# enable pgvector once connected:  CREATE EXTENSION vector;
```
Connect Cloud Run via the Cloud SQL connector (`--add-cloudsql-instances`).

## 2. Secrets

```bash
printf 'a-long-random-32B-min-secret' | gcloud secrets create JWT_SECRET --data-file=-
printf 'sk-ant-...'                    | gcloud secrets create ANTHROPIC_API_KEY --data-file=-
printf 'postgresql+asyncpg://app_user:...@HOST:5432/fieldops' | gcloud secrets create DATABASE_URL --data-file=-
printf 'postgresql://postgres:...@HOST:5432/fieldops'         | gcloud secrets create MIGRATION_DATABASE_URL --data-file=-
# Credential vault key (encrypts stored ServiceTitan/QBO tokens) — REQUIRED for /v1/connections:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" \
  | gcloud secrets create CREDENTIAL_ENCRYPTION_KEY --data-file=-
# Inbound webhook HMAC secret:
printf 'a-long-random-secret'          | gcloud secrets create WEBHOOK_SIGNING_SECRET --data-file=-
# RAG embeddings (optional — defaults to offline hashing if unset):
# printf 'sk-...'                      | gcloud secrets create OPENAI_API_KEY --data-file=-
# ServiceTitan / QuickBooks (when going live):
# gcloud secrets create SERVICETITAN_CLIENT_ID  --data-file=- ; ...CLIENT_SECRET, ...APP_KEY, ...TENANT_ID
# gcloud secrets create QUICKBOOKS_CLIENT_ID    --data-file=- ; ...CLIENT_SECRET, ...REFRESH_TOKEN, ...REALM_ID
```

The migration job (step 4) applies **all** of `migrations/*.sql` (through `0005_event_queue.sql`)
automatically. Add the new secrets to the service deploy with
`--set-secrets CREDENTIAL_ENCRYPTION_KEY=...:latest,WEBHOOK_SIGNING_SECRET=...:latest` and set
`--set-env-vars ACCOUNTING_MODE=fixture,INVENTORY_MODE=fixture,EMBEDDING_PROVIDER=hashing` (flip each
to live/openai when ready).

## 3. Build & push the API image

```bash
cd backend
gcloud builds submit --tag us-central1-docker.pkg.dev/YOUR_PROJECT/fieldops/api:latest
```

## 4. Apply migrations (one-off Cloud Run Job, not on every boot)

```bash
gcloud run jobs create fieldops-migrate \
  --image us-central1-docker.pkg.dev/YOUR_PROJECT/fieldops/api:latest \
  --region us-central1 \
  --set-secrets MIGRATION_DATABASE_URL=MIGRATION_DATABASE_URL:latest \
  --command python --args scripts/migrate.py
gcloud run jobs execute fieldops-migrate --region us-central1 --wait
```

## 5. Deploy the API service

```bash
gcloud run deploy fieldops-api \
  --image us-central1-docker.pkg.dev/YOUR_PROJECT/fieldops/api:latest \
  --region us-central1 --allow-unauthenticated \
  --set-env-vars ENV=prod,RUN_MIGRATIONS=0,SERVICETITAN_MODE=fixture,WORKFORCE_REASONING_MODEL=claude-sonnet-4-6 \
  --set-secrets DATABASE_URL=DATABASE_URL:latest,JWT_SECRET=JWT_SECRET:latest,ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest
```

Notes:
- `--allow-unauthenticated` makes the service reachable; **app auth is still enforced by JWT** on
  every endpoint. (Or front it with IAP / API Gateway.)
- `RUN_MIGRATIONS=0` — migrations are owned by the job in step 4.
- `ENV=prod` disables the `/auth/dev-token` endpoint; wire your IdP (Supabase/Auth0/Entra) in
  `app/security.py` (`decode_token`) to verify real JWTs via JWKS.
- Restrict CORS to your dashboard origin (see `app/main.py`).
- Flip `SERVICETITAN_MODE=live` (+ the ServiceTitan secrets) to use a real tenant.

## 6. Deploy the dashboard (optional, also Cloud Run)

```bash
cd ../frontend
gcloud builds submit --tag us-central1-docker.pkg.dev/YOUR_PROJECT/fieldops/web:latest
gcloud run deploy fieldops-web \
  --image us-central1-docker.pkg.dev/YOUR_PROJECT/fieldops/web:latest \
  --region us-central1 --allow-unauthenticated \
  --set-env-vars NEXT_PUBLIC_API_BASE_URL=https://fieldops-api-XXXX.run.app
```

## 7. Smoke test

```bash
API=https://fieldops-api-XXXX.run.app
curl -s $API/health
# In prod, dev-token is disabled — obtain a JWT from your IdP, then:
# curl -s -X POST "$API/v1/agents/workforce/runs?horizon_days=21" -H "Authorization: Bearer $JWT"
```

## Scaling notes

- Cloud Run `--min-instances=1` avoids cold starts for a paid tenant; `--cpu`/`--memory` per load.
- Per-tenant rate limits + usage metering belong at the gateway (roadmap).
- Streaming/event ingestion and an external vector store are deferred until triggered (ADR 0004).
