#!/bin/bash
# =============================================================================
# Staging Database Sync Script (PostgreSQL)
# =============================================================================
# Copies the production PostgreSQL database to staging.
# Called after production deploys to refresh staging with current prod data.
#
# Usage:
#   ./scripts/sync-staging-db.sh
#
# Requires:
#   - POSTGRES_PASSWORD in .env (same postgres container as prod/staging stacks)
#   - arquivo_prod and arquivo_staging databases on the postgres service
# =============================================================================

set -e

cd /root/arquivo-da-violencia

COMPOSE_PROD="-p prod -f docker-compose.yml"
COMPOSE_STAGING="-p staging -f docker-compose.yml -f docker-compose.staging.yml"
DUMP_PATH="/tmp/arquivo_prod_sync.dump"

if [ -z "${POSTGRES_PASSWORD:-}" ]; then
    if [ -f .env ]; then
        set -a
        # shellcheck disable=SC1091
        source .env
        set +a
    fi
fi

if [ -z "${POSTGRES_PASSWORD:-}" ]; then
    echo "❌ POSTGRES_PASSWORD is not set"
    exit 1
fi

echo "🔄 Starting production → staging PostgreSQL sync..."
echo ""

echo "⏳ Ensuring postgres is running..."
docker compose $COMPOSE_PROD up -d postgres

echo ""
echo "⏳ Stopping staging api/worker..."
docker compose $COMPOSE_STAGING stop api worker || true

echo ""
echo "📥 Dumping production database (arquivo_prod)..."
docker compose $COMPOSE_PROD exec -T postgres \
    pg_dump -U arquivo -Fc -d arquivo_prod > "$DUMP_PATH"
echo "   Dump saved to $DUMP_PATH"

echo ""
echo "🔄 Restoring into staging database (arquivo_staging)..."
docker compose $COMPOSE_PROD exec -T postgres \
    pg_restore -U arquivo --clean --if-exists --no-owner --dbname=arquivo_staging < "$DUMP_PATH"
echo "   Restore complete"

echo ""
echo "🔄 Starting staging api/worker..."
docker compose $COMPOSE_STAGING up -d api worker

echo ""
echo "🏥 Waiting for staging containers to be healthy..."
# API can take >60s to pass startup auth/DB checks after a fresh recreate.
MAX_ATTEMPTS=90
ATTEMPT=1
SLEEP_SECS=2

while [ $ATTEMPT -le $MAX_ATTEMPTS ]; do
    API_HEALTHY=false
    if curl -sf "http://localhost:8001/health" > /dev/null 2>&1; then
        API_HEALTHY=true
    elif docker inspect --format='{{.State.Health.Status}}' staging-arquivo-api 2>/dev/null | grep -q "healthy"; then
        API_HEALTHY=true
    fi

    WORKER_HEALTHY=false
    if docker inspect --format='{{.State.Health.Status}}' staging-arquivo-worker 2>/dev/null | grep -q "healthy"; then
        WORKER_HEALTHY=true
    fi

    if [ "$API_HEALTHY" = true ] && [ "$WORKER_HEALTHY" = true ]; then
        echo "   ✅ Staging API is healthy"
        echo "   ✅ Staging Worker is healthy"
        break
    fi

    if [ $ATTEMPT -eq $MAX_ATTEMPTS ]; then
        echo "   ❌ Health check failed after $MAX_ATTEMPTS attempts"
        docker ps --filter name="staging-arquivo" --format 'table {{.Names}}\t{{.Status}}'
        docker logs staging-arquivo-api --tail 20 2>&1 || true
        exit 1
    fi

    sleep $SLEEP_SECS
    ATTEMPT=$((ATTEMPT + 1))
done

echo ""
echo "📊 Row counts (staging):"
docker compose $COMPOSE_PROD exec -T postgres psql -U arquivo -d arquivo_staging -c \
    "SELECT 'source_google_news' AS tbl, COUNT(*) FROM source_google_news
     UNION ALL SELECT 'raw_event', COUNT(*) FROM raw_event
     UNION ALL SELECT 'unique_event', COUNT(*) FROM unique_event;"

rm -f "$DUMP_PATH"

echo ""
echo "✅ PostgreSQL staging sync complete!"
