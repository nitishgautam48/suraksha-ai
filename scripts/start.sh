#!/bin/sh
# API container entrypoint: wait for DB -> migrate -> seed -> serve.
set -e
cd /app
python scripts/wait_for_db.py
echo "Running database migrations..."
alembic -c backend/alembic.ini upgrade head
echo "Seeding learning content / bootstrap admin..."
python -m backend.seed.seed
# Prometheus multi-process mode: each uvicorn worker writes metrics here; /metrics aggregates them.
export PROMETHEUS_MULTIPROC_DIR="${PROMETHEUS_MULTIPROC_DIR:-/tmp/prometheus}"
rm -rf "$PROMETHEUS_MULTIPROC_DIR" && mkdir -p "$PROMETHEUS_MULTIPROC_DIR"
echo "Starting Suraksha AI API on :8000 (workers=${WEB_CONCURRENCY:-2})"
exec uvicorn backend.main:app \
    --host 0.0.0.0 --port 8000 \
    --workers "${WEB_CONCURRENCY:-2}" \
    --proxy-headers --forwarded-allow-ips="${FORWARDED_ALLOW_IPS:-127.0.0.1}" \
    --timeout-keep-alive 30 \
    --no-server-header
