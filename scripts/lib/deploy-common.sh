#!/bin/bash
# Shared helpers for VPS deploy scripts.

REPO_DIR="${REPO_DIR:-/root/arquivo-da-violencia}"
COMPOSE_PROD="-p prod -f docker-compose.yml"
COMPOSE_STAGING="-p staging -f docker-compose.yml -f docker-compose.staging.yml"

load_env() {
    if [ -n "${POSTGRES_PASSWORD:-}" ]; then
        return 0
    fi
    local env_file="$REPO_DIR/.env"
    if [ ! -f "$env_file" ]; then
        return 0
    fi
    # Do not `source` .env: bcrypt hashes contain `$` sequences.
    POSTGRES_PASSWORD="$(
        grep -m1 '^POSTGRES_PASSWORD=' "$env_file" | cut -d= -f2- | tr -d '\r'
    )"
    POSTGRES_PASSWORD="${POSTGRES_PASSWORD%\"}"
    POSTGRES_PASSWORD="${POSTGRES_PASSWORD#\"}"
    POSTGRES_PASSWORD="${POSTGRES_PASSWORD%\'}"
    POSTGRES_PASSWORD="${POSTGRES_PASSWORD#\'}"
    export POSTGRES_PASSWORD
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

prepare_docker_for_pull() {
    echo "🧹 Preparing Docker storage for image pull..."
    df -h /var/lib/docker 2>/dev/null || df -h /
    docker image prune -af || true
    docker builder prune -af || true
}

ensure_bcrypt_env_passwords() {
    local env_file="$REPO_DIR/.env"
    if [ ! -f "$env_file" ]; then
        return 0
    fi
    echo "🔐 Ensuring admin passwords in .env are bcrypt-hashed..."
    docker compose $COMPOSE_FILES run --rm --no-deps \
        -v "$env_file:/work/.env:rw" \
        -v "$REPO_DIR/scripts/hash-env-passwords.py:/tmp/hash-env-passwords.py:ro" \
        api python /tmp/hash-env-passwords.py /work/.env
    load_env
}

preflight_api_config() {
    echo "🔍 Preflight: validating API auth config..."
    if docker compose $COMPOSE_FILES run --rm --no-deps \
        -v "$REPO_DIR/.env:/run/deploy.env:ro" \
        -v "$REPO_DIR/scripts/preflight-auth.py:/tmp/preflight-auth.py:ro" \
        api sh -c "cd /app && PYTHONPATH=/app .venv/bin/python /tmp/preflight-auth.py /run/deploy.env"; then
        echo "   ✅ API config is valid"
        return 0
    fi
    echo "❌ API config validation failed — aborting deploy without stopping running services"
    return 1
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
