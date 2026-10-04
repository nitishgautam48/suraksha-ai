#!/bin/sh
# Celery worker + embedded beat scheduler (async scans, RAG ingestion, daily nudges).
set -e
cd /app
python scripts/wait_for_db.py
exec celery -A backend.workers.celery_app worker -B \
    --loglevel="${CELERY_LOG_LEVEL:-INFO}" \
    --concurrency="${CELERY_CONCURRENCY:-2}" \
    --schedule=/tmp/celerybeat-schedule
