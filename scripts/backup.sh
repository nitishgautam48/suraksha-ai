#!/bin/sh
# Scheduled backups (runs in the `db-backup` service, image postgres:16-alpine).
#   - PostgreSQL: pg_dump custom format, verified with pg_restore --list
#   - Uploaded files and knowledge documents: tar.gz of the volumes (mounted read-only)
#   - Retention: delete backups older than BACKUP_RETENTION_DAYS
# ChromaDB is not backed up: it is rebuilt from the knowledge documents (POST /admin/knowledge/ingest).
# Run once:  docker compose run --rm db-backup sh /scripts/backup.sh --once
set -eu
: "${BACKUP_DIR:=/backups}" "${BACKUP_INTERVAL_SECONDS:=86400}" "${BACKUP_RETENTION_DAYS:=7}" "${BACKUP_INITIAL_DELAY_SECONDS:=900}"
export PGPASSWORD="${POSTGRES_PASSWORD}"

backup_once() {
  ts=$(date -u +%Y%m%dT%H%M%SZ)
  mkdir -p "$BACKUP_DIR"
  db_file="$BACKUP_DIR/suraksha-db-$ts.dump"
  echo "[$ts] dumping database ${POSTGRES_DB}@${POSTGRES_HOST}"
  pg_dump -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -Z 6 -f "$db_file.partial"
  pg_restore --list "$db_file.partial" > /dev/null   # fails loudly if the dump is unreadable
  mv "$db_file.partial" "$db_file"
  for vol in uploads knowledge; do
    if [ -d "/data/$vol" ] && [ -n "$(ls -A "/data/$vol" 2>/dev/null)" ]; then
      tar -czf "$BACKUP_DIR/suraksha-$vol-$ts.tar.gz" -C /data "$vol"
    fi
  done
  find "$BACKUP_DIR" -name 'suraksha-*' -type f -mtime +"$BACKUP_RETENTION_DAYS" -print -delete
  echo "[$ts] backup complete: $(du -h "$db_file" | cut -f1) database dump"
}

if [ "${1:-}" = "--once" ]; then
  backup_once
  exit 0
fi
until pg_isready -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -q; do sleep 2; done
# Let the API run its migrations first, so the first scheduled backup contains real data.
echo "first backup in ${BACKUP_INITIAL_DELAY_SECONDS}s, then every ${BACKUP_INTERVAL_SECONDS}s"
sleep "$BACKUP_INITIAL_DELAY_SECONDS"
while true; do
  backup_once || echo "backup FAILED - will retry next interval" >&2
  sleep "$BACKUP_INTERVAL_SECONDS"
done
