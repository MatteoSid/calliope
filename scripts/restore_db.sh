#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

CONTAINER_NAME="${CONTAINER_NAME:-mongodb_calliope}"
BACKUP_DIR="${BACKUP_DIR:-$PROJECT_ROOT/backups}"

usage() {
    echo "Uso: $(basename "$0") [-y|--yes] <file-backup.archive.gz>"
    echo
    echo "Ripristina un backup del database nel container '$CONTAINER_NAME'."
    echo "ATTENZIONE: le collection esistenti vengono sovrascritte (--drop)."
    if compgen -G "$BACKUP_DIR/*.archive.gz" > /dev/null; then
        echo
        echo "Backup disponibili in $BACKUP_DIR:"
        ls -1t "$BACKUP_DIR"/*.archive.gz
    fi
}

ASSUME_YES=false
BACKUP_FILE=""
for arg in "$@"; do
    case "$arg" in
        -y|--yes) ASSUME_YES=true ;;
        -h|--help) usage; exit 0 ;;
        *) BACKUP_FILE="$arg" ;;
    esac
done

if [[ -z "$BACKUP_FILE" ]]; then
    usage >&2
    exit 1
fi

if [[ ! -f "$BACKUP_FILE" ]]; then
    echo "Errore: file di backup non trovato: $BACKUP_FILE" >&2
    exit 1
fi

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
    echo "Errore: il container '$CONTAINER_NAME' non è in esecuzione." >&2
    echo "Avvialo con: docker compose up -d mongodb" >&2
    exit 1
fi

if [[ "$ASSUME_YES" != true ]]; then
    read -r -p "Il restore sovrascrive le collection esistenti nel container '$CONTAINER_NAME'. Continuare? [s/N] " reply
    case "$reply" in
        [sSyY]*) ;;
        *) echo "Annullato."; exit 0 ;;
    esac
fi

echo "Restore di '$BACKUP_FILE' nel container '$CONTAINER_NAME'..."
docker exec -i "$CONTAINER_NAME" mongorestore --quiet --archive --gzip --drop < "$BACKUP_FILE"

echo "Restore completato. Documenti per collection nel database 'calliope':"
docker exec "$CONTAINER_NAME" mongosh --quiet calliope --eval '
db.getCollectionNames().sort().forEach(function (c) {
    print("  " + c + ": " + db.getCollection(c).countDocuments());
});'
