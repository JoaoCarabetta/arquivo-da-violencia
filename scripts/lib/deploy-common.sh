#!/bin/bash
# Shared helpers for VPS deploy scripts.

REPO_DIR="${REPO_DIR:-/root/arquivo-da-violencia}"
COMPOSE_PROD="-p prod -f docker-compose.yml"
COMPOSE_STAGING="-p staging -f docker-compose.yml -f docker-compose.staging.yml"

load_env() {
    if [ -z "${POSTGRES_PASSWORD:-}" ] && [ -f "$REPO_DIR/.env" ]; then
        set -a
        # shellcheck disable=SC1091
        source "$REPO_DIR/.env"
        set +a
    fi
}

sync_deploy_repo() {
    local branch="$1"
    cd "$REPO_DIR"
    echo "📥 Syncing repository to origin/$branch..."
    git fetch origin "$branch"
    git checkout -f "$branch"
    git reset --hard "origin/$branch"
}

ensure_prod_postgres() {
    echo "📦 Ensuring production Postgres is running..."
    docker compose $COMPOSE_PROD up -d postgres

    local attempt=1
    local max_attempts=30
    while [ "$attempt" -le "$max_attempts" ]; do
        if docker compose $COMPOSE_PROD exec -T postgres pg_isready -U arquivo -d arquivo_prod >/dev/null 2>&1; then
            echo "   ✅ Production Postgres is ready"
            return 0
        fi
        sleep 2
        attempt=$((attempt + 1))
    done

    echo "❌ Production Postgres failed to become ready"
    docker logs arquivo-postgres --tail 30 2>&1 || true
    exit 1
}

remove_orphan_staging_postgres() {
    if docker ps -a --format '{{.Names}}' | grep -qx 'staging-arquivo-postgres'; then
        echo "🗑️ Removing orphan staging Postgres container (must not share prod data volume)..."
        docker rm -f staging-arquivo-postgres
    fi
}

wait_for_api_health() {
    local port="$1"
    local max_attempts="${2:-90}"
    local attempt=1

    while [ "$attempt" -le "$max_attempts" ]; do
        if curl -sf "http://localhost:${port}/health" >/dev/null 2>&1; then
            echo "   ✅ API is healthy on port ${port}"
            return 0
        fi
        sleep 2
        attempt=$((attempt + 1))
    done

    return 1
}

wait_for_worker_health() {
    local container="$1"
    local max_attempts="${2:-90}"
    local attempt=1

    while [ "$attempt" -le "$max_attempts" ]; do
        if docker inspect --format='{{.State.Health.Status}}' "$container" 2>/dev/null | grep -q "healthy"; then
            echo "   ✅ Worker is healthy"
            return 0
        fi
        sleep 2
        attempt=$((attempt + 1))
    done

    return 1
}
