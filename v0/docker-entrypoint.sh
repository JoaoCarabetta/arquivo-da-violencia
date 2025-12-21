#!/bin/bash
set -e

# Ensure instance and logs directories exist and are writable
mkdir -p /app/instance /app/logs
chmod 777 /app/instance /app/logs

# If database doesn't exist, create it with proper permissions
if [ ! -f /app/instance/violence.db ]; then
    touch /app/instance/violence.db
    chmod 666 /app/instance/violence.db
fi

# Ensure database file is writable
chmod 666 /app/instance/violence.db 2>/dev/null || true
chmod 666 /app/instance/violence.db-* 2>/dev/null || true

# Run database migrations if alembic is available
if command -v alembic &> /dev/null; then
    cd /app && alembic upgrade head || true
fi

# Execute the main command
exec "$@"

