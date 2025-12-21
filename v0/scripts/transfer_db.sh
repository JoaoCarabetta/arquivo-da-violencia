#!/bin/bash
# Script to transfer violence.db from remote server
# Usage: ./scripts/transfer_db.sh [user@]hostname [path_to_remote_db]

set -e

REMOTE_HOST="${1:-user@remote-server}"
REMOTE_PATH="${2:-/Users/joaoc/Documents/projects/arquivo-da-violencia/instance/violence.db}"
LOCAL_DIR="/root/arquivo-da-violencia/instance"
BACKUP_DIR="${LOCAL_DIR}/backups"

echo "Transferring database from remote server..."
echo "Remote: ${REMOTE_HOST}:${REMOTE_PATH}"
echo "Local: ${LOCAL_DIR}/violence.db"

# Create backup directory if it doesn't exist
mkdir -p "${BACKUP_DIR}"

# Backup existing database if it exists
if [ -f "${LOCAL_DIR}/violence.db" ]; then
    BACKUP_FILE="${BACKUP_DIR}/violence.db.backup.$(date +%Y%m%d_%H%M%S)"
    echo "Backing up existing database to ${BACKUP_FILE}..."
    cp "${LOCAL_DIR}/violence.db" "${BACKUP_FILE}"
    
    # Also backup WAL files
    [ -f "${LOCAL_DIR}/violence.db-shm" ] && cp "${LOCAL_DIR}/violence.db-shm" "${BACKUP_FILE}-shm" 2>/dev/null || true
    [ -f "${LOCAL_DIR}/violence.db-wal" ] && cp "${LOCAL_DIR}/violence.db-wal" "${BACKUP_FILE}-wal" 2>/dev/null || true
fi

# Transfer the file using scp
echo "Transferring file..."
scp "${REMOTE_HOST}:${REMOTE_PATH}" "${LOCAL_DIR}/violence.db"

# Set proper permissions
chmod 644 "${LOCAL_DIR}/violence.db"

echo "Database transfer complete!"
echo "File location: ${LOCAL_DIR}/violence.db"
if [ -f "${BACKUP_FILE}" ]; then
    echo "Previous database backed up to: ${BACKUP_FILE}"
fi

