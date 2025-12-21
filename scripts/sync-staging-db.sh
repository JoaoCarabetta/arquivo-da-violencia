#!/bin/bash
# =============================================================================
# Staging Database Sync Script
# =============================================================================
# Copies the production database to staging environment.
# Called after production deploys to refresh staging with current prod data.
#
# Usage:
#   ./scripts/sync-staging-db.sh
#
# Safety features:
#   - Stops staging containers before copying to prevent corruption
#   - Uses sqlite3 .backup for consistent copy
#   - Creates backup of current staging DB before overwriting
#   - Runs migrations after copy
#   - Verifies staging health after restart
# =============================================================================

set -e

cd /opt/arquivo-da-violencia

PROD_DB="./instance/violence.db"
STAGING_DB="./staging_instance/violence.db"
STAGING_BACKUP="./staging_instance/violence.db.backup.$(date +%Y%m%d_%H%M%S)"
COMPOSE_STAGING="-f docker-compose.yml -f docker-compose.staging.yml"

echo "🔄 Starting production to staging database sync..."
echo ""

# Step 0: Verify production database exists
if [ ! -f "$PROD_DB" ]; then
    echo "❌ Production database not found at $PROD_DB"
    exit 1
fi

# Step 1: Create staging instance directory if it doesn't exist
echo "📁 Ensuring staging instance directory exists..."
mkdir -p ./staging_instance
chmod 755 ./staging_instance

# Step 2: Stop staging containers
echo ""
echo "⏳ Stopping staging containers..."
docker compose $COMPOSE_STAGING stop api worker || true
echo "   Staging containers stopped"

# Step 3: Backup current staging database (if exists)
if [ -f "$STAGING_DB" ]; then
    echo ""
    echo "💾 Backing up current staging database..."
    cp "$STAGING_DB" "$STAGING_BACKUP"
    echo "   Backup saved to: $STAGING_BACKUP"
fi

# Step 4: Copy production database to staging
echo ""
echo "📥 Copying production database to staging..."

# Check if sqlite3 is available
if command -v sqlite3 &> /dev/null; then
    # Use sqlite3 .backup for a consistent copy (handles WAL mode correctly)
    sqlite3 "$PROD_DB" ".backup '$STAGING_DB'"
    echo "   Database copied using sqlite3 .backup (safe for WAL mode)"
else
    # Fallback to file copy (ensure no writes happening)
    cp "$PROD_DB" "$STAGING_DB"
    # Also copy WAL and SHM files if they exist
    [ -f "${PROD_DB}-wal" ] && cp "${PROD_DB}-wal" "${STAGING_DB}-wal"
    [ -f "${PROD_DB}-shm" ] && cp "${PROD_DB}-shm" "${STAGING_DB}-shm"
    echo "   Database copied using file copy"
fi

# Ensure proper permissions
chmod 666 "$STAGING_DB"

# Step 5: Run migrations on staging database
echo ""
echo "🔄 Running migrations on staging database..."
docker compose $COMPOSE_STAGING run --rm api alembic upgrade head

# Step 6: Start staging containers
echo ""
echo "🔄 Starting staging containers..."
docker compose $COMPOSE_STAGING up -d api worker

# Step 7: Health check
echo ""
echo "🏥 Waiting for staging API health check..."
MAX_ATTEMPTS=30
ATTEMPT=1

while [ $ATTEMPT -le $MAX_ATTEMPTS ]; do
    if curl -sf "http://localhost:8001/health" > /dev/null 2>&1; then
        echo "   ✅ Staging API is healthy (attempt $ATTEMPT/$MAX_ATTEMPTS)"
        break
    fi
    
    if [ $ATTEMPT -eq $MAX_ATTEMPTS ]; then
        echo "   ❌ Health check failed after $MAX_ATTEMPTS attempts"
        echo ""
        echo "📋 Recent staging API logs:"
        docker logs --tail=50 staging-arquivo-api
        exit 1
    fi
    
    echo "   Waiting... (attempt $ATTEMPT/$MAX_ATTEMPTS)"
    sleep 2
    ATTEMPT=$((ATTEMPT + 1))
done

# Step 8: Summary
PROD_SIZE=$(du -h "$PROD_DB" | cut -f1)
STAGING_SIZE=$(du -h "$STAGING_DB" | cut -f1)

echo ""
echo "✅ Database sync complete!"
echo "   Production DB size: $PROD_SIZE"
echo "   Staging DB size: $STAGING_SIZE"
echo "   Staging API: http://localhost:8001"

# Clean up old backups (keep last 5)
echo ""
echo "🧹 Cleaning up old backups..."
ls -t ./staging_instance/violence.db.backup.* 2>/dev/null | tail -n +6 | xargs -r rm -f
echo "   Kept last 5 backups"

