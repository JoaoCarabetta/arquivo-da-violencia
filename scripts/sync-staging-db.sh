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
#   - POSTGRES_PASSWORD in .env
#   - Single shared Postgres container (arquivo-postgres) with arquivo_prod and
#     arquivo_staging databases
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/deploy-common.sh"

DUMP_PATH="/tmp/arquivo_prod_sync.dump"

load_env

if [ -z "${POSTGRES_PASSWORD:-}" ]; then
    echo "❌ POSTGRES_PASSWORD is not set"
    exit 1
fi

echo "🔄 Starting production → staging PostgreSQL sync..."
echo ""

ensure_prod_postgres
remove_orphan_staging_postgres

echo ""
echo "⏳ Stopping staging api/worker..."
docker compose $COMPOSE_STAGING stop api worker || true

echo ""
echo "📥 Dumping production database (arquivo_prod)..."
docker compose $COMPOSE_PROD exec -T postgres \
    pg_dump -U arquivo -Fc -d arquivo_prod > "$DUMP_PATH"
echo "   Dump saved to $DUMP_PATH"

echo ""
echo "🔌 Terminating active connections to arquivo_staging..."
docker compose $COMPOSE_PROD exec -T postgres psql -U arquivo -d postgres -c \
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'arquivo_staging' AND pid <> pg_backend_pid();" \
    >/dev/null || true

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
if ! wait_for_api_health 8001 90; then
    echo "❌ Staging API health check failed"
    docker logs staging-arquivo-api --tail 20 2>&1 || true
    exit 1
fi

if ! wait_for_worker_health staging-arquivo-worker 90; then
    echo "❌ Staging worker health check failed"
    docker logs staging-arquivo-worker --tail 20 2>&1 || true
    exit 1
fi

echo ""
echo "📊 Row counts (staging):"
docker compose $COMPOSE_PROD exec -T postgres psql -U arquivo -d arquivo_staging -c \
    "SELECT 'source_google_news' AS tbl, COUNT(*) FROM source_google_news
     UNION ALL SELECT 'raw_event', COUNT(*) FROM raw_event
     UNION ALL SELECT 'unique_event', COUNT(*) FROM unique_event;"

rm -f "$DUMP_PATH"

echo ""
echo "✅ PostgreSQL staging sync complete!"
