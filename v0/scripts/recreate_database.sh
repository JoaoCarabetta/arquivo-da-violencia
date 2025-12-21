#!/bin/bash
# Script to safely recreate the database after corruption

set -e

DB_PATH="instance/violence.db"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "⚠️  WARNING: This will recreate the database (data will be lost)"
echo "Database: $DB_PATH"
echo ""
read -p "Are you sure? Type 'yes' to continue: " confirm

if [ "$confirm" != "yes" ]; then
    echo "Cancelled."
    exit 1
fi

# Backup corrupted database
if [ -f "$DB_PATH" ]; then
    BACKUP_PATH="${DB_PATH}.corrupted_${TIMESTAMP}"
    cp "$DB_PATH" "$BACKUP_PATH"
    echo "✅ Corrupted database backed up to: $BACKUP_PATH"
fi

# Remove WAL and SHM files
for ext in "-wal" "-shm"; do
    if [ -f "${DB_PATH}${ext}" ]; then
        rm "${DB_PATH}${ext}"
        echo "✅ Removed: ${DB_PATH}${ext}"
    fi
done

# Remove corrupted database
if [ -f "$DB_PATH" ]; then
    rm "$DB_PATH"
    echo "✅ Removed corrupted database"
fi

# Create new empty database
touch "$DB_PATH"
chmod 666 "$DB_PATH"
echo "✅ Created new empty database"

echo ""
echo "Next steps:"
echo "  1. Run migrations: uv run python entrypoints/manage.py db_upgrade"
echo "  2. Restart the application"

