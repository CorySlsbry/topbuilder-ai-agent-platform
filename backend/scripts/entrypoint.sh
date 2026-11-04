#!/bin/sh
# Container entrypoint. Optionally applies migrations, then serves the API.
#
# RUN_MIGRATIONS=1 (default) is convenient for local compose / single-instance.
# In Cloud Run, set RUN_MIGRATIONS=0 on the *service* and apply migrations with a one-off
# Cloud Run Job (`python scripts/migrate.py`) so multiple instances don't race. See
# docs/DEPLOY_CLOUD_RUN.md.
set -eu

if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
  echo "[entrypoint] applying database migrations..."
  python scripts/migrate.py
fi

PORT_TO_BIND="${PORT:-${API_PORT:-8000}}"   # Cloud Run injects $PORT
echo "[entrypoint] starting uvicorn on :${PORT_TO_BIND}"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT_TO_BIND}"
