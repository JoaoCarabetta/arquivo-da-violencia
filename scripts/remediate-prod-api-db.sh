#!/bin/bash
# =============================================================================
# Emergency remmediation: restore prod API DB-backed public endpoints.
# =============================================================================
# Run on the VPS from /root/arquivo-da-violencia (via Actions SSH).
# Safe: no DROP/TRUNCATE; recreates API container, runs alembic, verifies stats.
# =============================================================================

set -euo pipefail

REPO_DIR="${REPO_DIR:-/root/arquivo-da-violencia}"
COMPOSE_PROD="-p prod -f docker-compose.yml"
API_CONTAINER="${API_CONTAINER:-arquivo-api}"
API_PORT="${API_PORT:-8000}"

cd "$REPO_DIR"

echo "=== 1) Diagnose (pre) ==="
echo "-- API container networks --"
docker inspect "$API_CONTAINER" --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' 2>/dev/null || echo "(no container)"
echo "-- Recent API errors --"
docker logs "$API_CONTAINER" --since 6h 2>&1 | grep -iE 'error|exception|traceback|asyncpg|operational|undefinedcolumn|does not exist|connection' | tail -40 || true
echo "-- Postgres unique_event count (host-side) --"
docker compose $COMPOSE_PROD exec -T postgres \
  psql -U arquivo -d arquivo_prod -c "SELECT COUNT(*) AS unique_events FROM unique_event;" \
  || echo "WARN: psql unique_event count failed"
echo "-- Public stats (before) --"
curl -sS -m 10 "http://localhost:${API_PORT}/api/public/stats" || true
echo

echo "=== 2) Unblock dirty git (deploy hygiene) ==="
if ! git diff --quiet || ! git diff --cached --quiet || [ -n "$(git ls-files --others --exclude-standard)" ]; then
  echo "Stashing local VPS changes..."
  git stash push -u -m "remediate-prod-api-db $(date -u +%Y%m%dT%H%M%SZ)" || true
fi
git fetch origin master
git checkout -f master
git reset --hard origin/master

echo "=== 3) Ensure pipeline_net exists (compose external net) ==="
if ! docker network inspect pipeline_net >/dev/null 2>&1; then
  echo "Creating pipeline_net..."
  docker network create pipeline_net
else
  echo "pipeline_net already present"
fi

echo "=== 4) Load POSTGRES_PASSWORD for compose interpolation ==="
# Do not source full .env (bcrypt `$` sequences).
if [ -z "${POSTGRES_PASSWORD:-}" ] && [ -f .env ]; then
  POSTGRES_PASSWORD="$(
    grep -m1 '^POSTGRES_PASSWORD=' .env | cut -d= -f2- | tr -d '\r'
  )"
  POSTGRES_PASSWORD="${POSTGRES_PASSWORD%\"}"
  POSTGRES_PASSWORD="${POSTGRES_PASSWORD#\"}"
  POSTGRES_PASSWORD="${POSTGRES_PASSWORD%\'}"
  POSTGRES_PASSWORD="${POSTGRES_PASSWORD#\'}"
  export POSTGRES_PASSWORD
fi
if [ -z "${POSTGRES_PASSWORD:-}" ]; then
  echo "ERROR: POSTGRES_PASSWORD is empty; cannot recreate API with valid DATABASE_URL"
  exit 1
fi

echo "=== 5) Ensure postgres/redis up, migrate, recreate API ==="
docker compose $COMPOSE_PROD up -d --no-recreate postgres redis
docker compose $COMPOSE_PROD run --rm --no-deps api alembic upgrade head
# Force recreate so networks (default + pipeline_net) and env are reapplied.
docker compose $COMPOSE_PROD up -d --force-recreate --no-deps api

echo "=== 6) Wait for health + public stats ==="
ok=0
for i in $(seq 1 60); do
  if curl -sf "http://localhost:${API_PORT}/api/health" >/dev/null 2>&1 \
    && curl -sf "http://localhost:${API_PORT}/api/public/stats" >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 2
done

echo "-- API networks (after) --"
docker inspect "$API_CONTAINER" --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' 2>/dev/null || true
echo "-- Public stats (after) --"
stats="$(curl -sS -m 15 "http://localhost:${API_PORT}/api/public/stats" || true)"
echo "$stats"

if [ "$ok" -ne 1 ]; then
  echo "ERROR: public stats still failing after remmediation"
  docker logs "$API_CONTAINER" --since 10m 2>&1 | tail -80 || true
  exit 1
fi

total="$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("total",0))' <<<"$stats" 2>/dev/null || echo 0)"
echo "public stats total=$total"
if [ "${total:-0}" -le 0 ]; then
  echo "WARN: stats returned 200 but total=0 — API DB path works; data may still be empty"
fi

echo "✅ remmediation complete"
