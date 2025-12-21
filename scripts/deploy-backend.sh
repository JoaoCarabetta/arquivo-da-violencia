#!/bin/bash
# =============================================================================
# Backend Deployment Script
# =============================================================================
# This script handles graceful backend deployment with worker shutdown.
#
# Usage:
#   ./scripts/deploy-backend.sh [production|staging]
#
# Features:
#   - Graceful worker shutdown (waits for current job to finish)
#   - Database migrations
#   - Health check verification
# =============================================================================

set -e

# Default to production if no environment specified
ENVIRONMENT="${1:-production}"

# Configuration based on environment
if [ "$ENVIRONMENT" = "staging" ]; then
    COMPOSE_FILES="-p staging -f docker-compose.yml -f docker-compose.staging.yml"
    WORKER_CONTAINER="staging-arquivo-worker"
    API_CONTAINER="staging-arquivo-api"
    API_PORT="8001"
    echo "🎭 Deploying to STAGING environment"
else
    COMPOSE_FILES=""
    WORKER_CONTAINER="arquivo-worker"
    API_CONTAINER="arquivo-api"
    API_PORT="8000"
    echo "🚀 Deploying to PRODUCTION environment"
fi

cd /root/arquivo-da-violencia

# Step 1: Pull new images
echo ""
echo "📥 Pulling new images..."
docker compose $COMPOSE_FILES pull api worker

# Step 2: Graceful worker shutdown
echo ""
echo "⏳ Gracefully stopping worker (waiting up to 120s for current job)..."
if docker ps -q -f name="$WORKER_CONTAINER" | grep -q .; then
    docker stop --time=120 "$WORKER_CONTAINER" || true
    echo "   Worker stopped"
else
    echo "   Worker was not running"
fi

# Step 3: Run database migrations
echo ""
echo "🔄 Running database migrations..."
docker compose $COMPOSE_FILES run --rm api alembic upgrade head

# Step 4: Start new containers
echo ""
echo "🔄 Starting new containers..."
docker compose $COMPOSE_FILES up -d api worker

# Step 5: Health check
echo ""
echo "🏥 Waiting for containers to be healthy..."
MAX_ATTEMPTS=30
ATTEMPT=1

while [ $ATTEMPT -le $MAX_ATTEMPTS ]; do
    # Check API health via HTTP
    API_HEALTHY=false
    if curl -sf "http://localhost:$API_PORT/health" > /dev/null 2>&1; then
        API_HEALTHY=true
    fi
    
    # Check Worker health via Docker
    WORKER_HEALTHY=false
    if docker inspect --format='{{.State.Health.Status}}' "$WORKER_CONTAINER" 2>/dev/null | grep -q "healthy"; then
        WORKER_HEALTHY=true
    fi
    
    # Both must be healthy
    if [ "$API_HEALTHY" = true ] && [ "$WORKER_HEALTHY" = true ]; then
        echo "   ✅ API is healthy"
        echo "   ✅ Worker is healthy"
        break
    fi
    
    if [ $ATTEMPT -eq $MAX_ATTEMPTS ]; then
        echo "   ❌ Health check failed after $MAX_ATTEMPTS attempts"
        echo ""
        echo "📋 Container status:"
        docker ps --filter name="$API_CONTAINER" --filter name="$WORKER_CONTAINER" --format 'table {{.Names}}\t{{.Status}}'
        echo ""
        echo "📋 Recent API logs:"
        docker logs --tail=30 "$API_CONTAINER"
        echo ""
        echo "📋 Recent Worker logs:"
        docker logs --tail=30 "$WORKER_CONTAINER"
        exit 1
    fi
    
    STATUS=""
    [ "$API_HEALTHY" = false ] && STATUS="$STATUS API"
    [ "$WORKER_HEALTHY" = false ] && STATUS="$STATUS Worker"
    echo "   Waiting for:$STATUS (attempt $ATTEMPT/$MAX_ATTEMPTS)"
    sleep 2
    ATTEMPT=$((ATTEMPT + 1))
done

# Step 6: Clean up
echo ""
echo "🧹 Cleaning up old images..."
docker image prune -f

echo ""
echo "✅ Backend deployment complete!"
echo "   Environment: $ENVIRONMENT"
echo "   API URL: http://localhost:$API_PORT"

