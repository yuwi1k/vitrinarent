#!/usr/bin/env bash
# Backup PostgreSQL (vitrina_db) via Docker Compose
# Запуск: ./scripts/backup_db.sh

set -e
cd "$(dirname "$0")/.."
BACKUPS_DIR="${PWD}/backups"
mkdir -p "$BACKUPS_DIR"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUPS_DIR}/vitrina_db_${TIMESTAMP}.sql"

echo "Creating backup: $BACKUP_FILE"
docker compose exec -T db pg_dump -U postgres vitrina_db > "$BACKUP_FILE"

echo "Backup saved: $BACKUP_FILE"
ls -la "$BACKUP_FILE"
