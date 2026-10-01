#!/usr/bin/env bash
# ==============================================================================
# Invoice Generator - Pre-Migration Database Backup & Retention Script
# ==============================================================================
# - Runs automatically before any database migration.
# - Dumps the production MySQL database to a timestamped file outside the repo.
# - Enforces a strict retention policy: retains the latest 14 backups.
# - Fails immediately if the backup creation fails or the file is empty.
# - Never logs or exposes database passwords.
# ==============================================================================

set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="/var/backups/invoice-maker"
RETENTION_COUNT=14

# 1. Parse DB credentials securely from .env if present
DB_NAME="invoice_app"
DB_USER="invoice_user"
DB_PASSWORD=""
DB_HOST="127.0.0.1"
DB_PORT="3307"

if [ -f "$APP_DIR/.env" ]; then
    ENV_NAME=$(grep -E '^[[:space:]]*DB_NAME=' "$APP_DIR/.env" | head -n1 | cut -d '=' -f2- | tr -d '\r' | tr -d '"' | tr -d "'" | xargs || true)
    ENV_USER=$(grep -E '^[[:space:]]*DB_USER=' "$APP_DIR/.env" | head -n1 | cut -d '=' -f2- | tr -d '\r' | tr -d '"' | tr -d "'" | xargs || true)
    ENV_PASS=$(grep -E '^[[:space:]]*DB_PASSWORD=' "$APP_DIR/.env" | head -n1 | cut -d '=' -f2- | tr -d '\r' | tr -d '"' | tr -d "'" || true)
    ENV_HOST=$(grep -E '^[[:space:]]*DB_HOST=' "$APP_DIR/.env" | head -n1 | cut -d '=' -f2- | tr -d '\r' | tr -d '"' | tr -d "'" | xargs || true)
    ENV_PORT=$(grep -E '^[[:space:]]*DB_PORT=' "$APP_DIR/.env" | head -n1 | cut -d '=' -f2- | tr -d '\r' | tr -d '"' | tr -d "'" | xargs || true)

    [ -n "$ENV_NAME" ] && DB_NAME="$ENV_NAME"
    [ -n "$ENV_USER" ] && DB_USER="$ENV_USER"
    [ -n "$ENV_PASS" ] && DB_PASSWORD="$ENV_PASS"
    [ -n "$ENV_HOST" ] && DB_HOST="$ENV_HOST"
    [ -n "$ENV_PORT" ] && DB_PORT="$ENV_PORT"
fi

# 2. Ensure secure backup directory exists
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/${DB_NAME}_${TIMESTAMP}.sql"

echo "[BACKUP] Starting pre-migration database backup for '${DB_NAME}'..."

# 3. Execute mysqldump (prefers host mysqldump, falls back to Docker container)
if command -v mysqldump &> /dev/null; then
    MYSQL_PWD="$DB_PASSWORD" mysqldump \
        --host="$DB_HOST" \
        --port="$DB_PORT" \
        --user="$DB_USER" \
        --single-transaction \
        --quick \
        --no-tablespaces \
        "$DB_NAME" > "$BACKUP_FILE"
elif command -v docker &> /dev/null && docker ps --format '{{.Names}}' | grep -q 'vellkoerp-testing-host-mysql-1'; then
    docker exec -i -e MYSQL_PWD="$DB_PASSWORD" vellkoerp-testing-host-mysql-1 \
        mysqldump \
        --single-transaction \
        --quick \
        --no-tablespaces \
        -u "$DB_USER" \
        "$DB_NAME" > "$BACKUP_FILE"
else
    echo "[BACKUP ERROR] Neither host 'mysqldump' nor MySQL Docker container was found!" >&2
    exit 1
fi

# 4. Verify backup validity
if [ ! -s "$BACKUP_FILE" ]; then
    echo "[BACKUP ERROR] Backup file was not created or is empty: $BACKUP_FILE" >&2
    rm -f "$BACKUP_FILE"
    exit 1
fi

chmod 600 "$BACKUP_FILE"
BACKUP_SIZE=$(ls -lh "$BACKUP_FILE" | awk '{print $5}')
echo "[BACKUP SUCCESS] Snapshot created at $BACKUP_FILE ($BACKUP_SIZE)"

# 5. Backup Retention Policy: Keep the latest 14 backups
# List files sorted by modification time (newest first)
mapfile -t ALL_BACKUPS < <(ls -1t "${BACKUP_DIR}/${DB_NAME}_"*.sql 2>/dev/null || true)
TOTAL_BACKUPS=${#ALL_BACKUPS[@]}

if [ "$TOTAL_BACKUPS" -gt "$RETENTION_COUNT" ]; then
    echo "[BACKUP RETENTION] Found $TOTAL_BACKUPS backups. Pruning to retain latest $RETENTION_COUNT..."
    for (( i=RETENTION_COUNT; i<TOTAL_BACKUPS; i++ )); do
        OLD_FILE="${ALL_BACKUPS[$i]}"
        if [ -f "$OLD_FILE" ]; then
            echo "[BACKUP RETENTION] Removing old snapshot: $(basename "$OLD_FILE")"
            rm -f "$OLD_FILE"
        fi
    done
fi

REMAINING_COUNT=$(ls -1 "${BACKUP_DIR}/${DB_NAME}_"*.sql 2>/dev/null | wc -l)
echo "[BACKUP RETENTION] Active snapshots stored: $REMAINING_COUNT (policy: keep latest $RETENTION_COUNT)"
