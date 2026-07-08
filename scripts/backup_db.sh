#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

CONTAINER_NAME="${CONTAINER_NAME:-mongodb_calliope}"
BACKUP_DIR="${BACKUP_DIR:-$PROJECT_ROOT/backups}"

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
    echo "Errore: il container '$CONTAINER_NAME' non è in esecuzione." >&2
    echo "Avvialo con: docker compose up -d mongodb" >&2
    exit 1
fi

mkdir -p "$BACKUP_DIR"
BACKUP_FILE="$BACKUP_DIR/calliope-backup-$(date +%Y%m%d-%H%M%S).archive.gz"

# Rimuove il file parziale se il dump fallisce a metà
trap 'rm -f "$BACKUP_FILE"' ERR

echo "Backup del database dal container '$CONTAINER_NAME'..."
docker exec "$CONTAINER_NAME" mongodump --quiet --archive --gzip > "$BACKUP_FILE"

echo "Backup completato: $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"
echo "Per ripristinarlo: ./scripts/restore_db.sh $BACKUP_FILE"
