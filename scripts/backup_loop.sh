#!/bin/sh
# Запускается внутри контейнера: бекап каждые 24 часа
set -e
BACKUPS_DIR="${BACKUPS_DIR:-/backups}"
INTERVAL="${BACKUP_INTERVAL_SECONDS:-86400}"

mkdir -p "$BACKUPS_DIR"
echo "Backup service started. Interval: ${INTERVAL}s (~24h). Dir: $BACKUPS_DIR"

while true; do
  ts=$(date +%Y%m%d_%H%M%S)
  file="${BACKUPS_DIR}/vitrina_db_${ts}.sql"
  echo "[$(date -Iseconds)] Creating backup: $file"
  pg_dump -h db -U "$POSTGRES_USER" "$POSTGRES_DB" > "$file"
  echo "[$(date -Iseconds)] Backup saved: $file"
  sleep "$INTERVAL"
done
