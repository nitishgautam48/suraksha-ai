#!/bin/sh
# Copy ./backups to off-machine storage with rclone (profile "offsite").
# Configure the remote entirely with environment variables, e.g. for S3-compatible storage:
#   BACKUP_REMOTE=offsite:my-bucket/suraksha
#   RCLONE_CONFIG_OFFSITE_TYPE=s3  RCLONE_CONFIG_OFFSITE_PROVIDER=AWS  RCLONE_CONFIG_OFFSITE_REGION=ap-south-1
#   RCLONE_CONFIG_OFFSITE_ACCESS_KEY_ID=...  RCLONE_CONFIG_OFFSITE_SECRET_ACCESS_KEY=...
# Works with any rclone backend (S3, Backblaze B2, Google Drive, SFTP, ...). Files are copied, never
# deleted remotely by local retention; remote retention is BACKUP_REMOTE_RETENTION_DAYS (0 = keep all).
set -eu
: "${BACKUP_REMOTE:?set BACKUP_REMOTE, e.g. offsite:bucket/path}"
: "${OFFSITE_INTERVAL_SECONDS:=3600}" "${BACKUP_REMOTE_RETENTION_DAYS:=30}"
while true; do
  ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  if rclone copy /backups "$BACKUP_REMOTE" --include 'suraksha-*' --min-age 2m --checksum --stats-one-line -v; then
    echo "[$ts] offsite copy complete -> $BACKUP_REMOTE"
    if [ "$BACKUP_REMOTE_RETENTION_DAYS" -gt 0 ]; then
      rclone delete "$BACKUP_REMOTE" --include 'suraksha-*' --min-age "${BACKUP_REMOTE_RETENTION_DAYS}d" -v || true
    fi
  else
    echo "[$ts] offsite copy FAILED - will retry next interval" >&2
  fi
  [ "${1:-}" = "--once" ] && exit 0
  sleep "$OFFSITE_INTERVAL_SECONDS"
done
