#!/usr/bin/env bash
# Restore PostgreSQL from backup (via Docker Compose)
# Использование: ./scripts/restore_db.sh [путь_к_файлу.sql]

set -e
cd "$(dirname "$0")/.."
BACKUPS_DIR="${PWD}/backups"

BACKUP_FILE="${1:-}"
if [ -z "$BACKUP_FILE" ]; then
  BACKUP_FILE=$(ls -t "$BACKUPS_DIR"/vitrina_db_*.sql 2>/dev/null | head -1)
  if [ -z "$BACKUP_FILE" ]; then
    echo "No backup file specified and no backups in $BACKUPS_DIR"
    exit 1
  fi
  echo "Using latest backup: $BACKUP_FILE"
fi

if [ ! -f "$BACKUP_FILE" ]; then
  echo "File not found: $BACKUP_FILE"
  exit 1
fi

echo "Restore from: $BACKUP_FILE"
echo "WARNING: This will replace current database. Continue? (y/N)"
read -r confirm
if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
  echo "Aborted."
  exit 0
fi

docker compose exec -T db psql -U postgres vitrina_db < "$BACKUP_FILE"
echo "Restore completed."
