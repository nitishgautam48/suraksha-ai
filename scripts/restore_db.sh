#!/bin/sh
# Restore a database dump made by backup.sh. DESTRUCTIVE: replaces the current database contents.
#   docker compose stop backend worker
#   docker compose run --rm db-backup sh /scripts/restore_db.sh /backups/suraksha-db-<timestamp>.dump
#   docker compose start backend worker
set -eu
dump="${1:?usage: restore_db.sh /backups/suraksha-db-<timestamp>.dump}"
[ -f "$dump" ] || { echo "no such file: $dump" >&2; exit 1; }
export PGPASSWORD="${POSTGRES_PASSWORD}"
pg_restore --list "$dump" > /dev/null
echo "Restoring $dump into ${POSTGRES_DB}@${POSTGRES_HOST} (existing objects are dropped)..."
pg_restore -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner --single-transaction "$dump"
echo "Restore complete. Start backend/worker; migrations run automatically on start."
