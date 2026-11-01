#!/usr/bin/env bash
# PostgreSQL backup.
# Usage: DATABASE_URL=... [KEEP_DAYS=14] ./backup_postgres.sh
set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL is required}"

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR=${BACKUP_DIR:-./backups}
KEEP_DAYS=${KEEP_DAYS:-14}
mkdir -p "$BACKUP_DIR"
DUMP_FILE="$BACKUP_DIR/db_$DATE.sql"
BACKUP_FILE="$BACKUP_DIR/db_$DATE.sql.gz"

pg_dump --dbname="$DATABASE_URL" --no-password --format=plain --file="$DUMP_FILE"
gzip -f "$DUMP_FILE"

# Retention: remove backups older than KEEP_DAYS.
find "$BACKUP_DIR" -name "db_*.sql.gz" -mtime +"$KEEP_DAYS" -delete

echo "Backup created: $BACKUP_FILE"
