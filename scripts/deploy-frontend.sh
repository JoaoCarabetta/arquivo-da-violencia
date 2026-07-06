#!/bin/bash
# =============================================================================
# Frontend Deployment Script
# =============================================================================
# Usage:
#   ./scripts/deploy-frontend.sh [production|staging]
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/deploy-common.sh"

ENVIRONMENT="${1:-production}"

if [ "$ENVIRONMENT" = "staging" ]; then
    COMPOSE_FILES="$COMPOSE_STAGING"
    DEPLOY_BRANCH="develop"
    echo "🎭 Deploying frontend to STAGING"
else
    COMPOSE_FILES="$COMPOSE_PROD"
    DEPLOY_BRANCH="master"
    echo "🚀 Deploying frontend to PRODUCTION"
fi

sync_deploy_repo "$DEPLOY_BRANCH"

echo ""
echo "📥 Pulling frontend image..."
docker compose $COMPOSE_FILES pull frontend

echo ""
echo "🔄 Restarting frontend..."
docker compose $COMPOSE_FILES up -d frontend

echo ""
echo "🧹 Cleaning up old images..."
docker image prune -f || true

echo ""
echo "✅ Frontend deployment complete ($ENVIRONMENT)"
