#!/bin/bash
# =============================================================================
# Backend Deployment Script
# =============================================================================
# Usage:
#   ./scripts/deploy-backend.sh [production|staging]
#
# Staging shares the production Postgres instance (arquivo-postgres) and uses
# the arquivo_staging database. Never start a second Postgres container.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/deploy-common.sh"

ENVIRONMENT="${1:-production}"

if [ "$ENVIRONMENT" = "staging" ]; then
    COMPOSE_FILES="$COMPOSE_STAGING"
    DEPLOY_BRANCH="develop"
    WORKER_CONTAINER="staging-arquivo-worker"
    API_CONTAINER="staging-arquivo-api"
    API_PORT="8001"
    echo "🎭 Deploying backend to STAGING"
else
    COMPOSE_FILES="$COMPOSE_PROD"
    DEPLOY_BRANCH="master"
    WORKER_CONTAINER="arquivo-worker"
    API_CONTAINER="arquivo-api"
    API_PORT="8000"
    echo "🚀 Deploying backend to PRODUCTION"
fi

sync_deploy_repo "$DEPLOY_BRANCH"
load_env
ensure_prod_postgres
remove_orphan_staging_postgres

echo ""
prepare_docker_for_pull
echo "📥 Pulling backend images..."
if ! docker compose $COMPOSE_FILES pull api worker; then
    echo "⚠️ Image pull failed; pruning storage and retrying once..."
    prepare_docker_for_pull
    docker compose $COMPOSE_FILES pull api worker
fi

if [ "$ENVIRONMENT" = "production" ]; then
    echo "📥 Pulling node_exporter (best-effort)..."
    docker compose $COMPOSE_FILES pull node_exporter || echo "⚠️ node_exporter pull failed; continuing backend deploy"
fi

ensure_bcrypt_env_passwords
if ! preflight_api_config; then
    exit 1
fi

echo ""
echo "⏳ Gracefully stopping API and worker (up to 120s)..."
docker stop --timeout=120 "$WORKER_CONTAINER" "$API_CONTAINER" 2>/dev/null || true
docker rm -f "$API_CONTAINER" "$WORKER_CONTAINER" 2>/dev/null || true

echo ""
if [ "$ENVIRONMENT" = "staging" ]; then
    echo "📦 Ensuring staging Redis is running..."
    docker compose $COMPOSE_FILES up -d --no-recreate redis
else
    echo "📦 Ensuring production Postgres and Redis are running..."
    docker compose $COMPOSE_FILES up -d --no-recreate postgres redis
fi

echo ""
echo "🔄 Running database migrations..."
docker compose $COMPOSE_FILES run --rm --no-deps api alembic upgrade head

echo ""
echo "🔄 Starting API and worker..."
docker compose $COMPOSE_FILES up -d --no-deps api worker

if [ "$ENVIRONMENT" = "production" ]; then
    echo "🔄 Starting node_exporter (best-effort)..."
    docker compose $COMPOSE_FILES up -d --no-deps node_exporter || echo "⚠️ node_exporter start failed; backend deploy continues"
fi

echo ""
echo "🏥 Waiting for health checks..."
if ! wait_for_api_health "$API_PORT" 90; then
    echo "❌ API health check failed"
    docker logs --tail=30 "$API_CONTAINER" 2>&1 || true
    exit 1
fi

if ! wait_for_worker_health "$WORKER_CONTAINER" 90; then
    echo "❌ Worker health check failed"
    docker logs --tail=30 "$WORKER_CONTAINER" 2>&1 || true
    exit 1
fi

echo ""
echo "🧹 Cleaning up old images..."
docker image prune -f || true

echo ""
echo "✅ Backend deployment complete ($ENVIRONMENT)"
