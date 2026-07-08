#!/usr/bin/env bash
# One-shot staging/prod backfill wrapper (near-dup merge + reclassify discarded).
#
# Usage on VPS:
#   cd /root/arquivo-da-violencia
#   bash scripts/run_prod_backfill.sh staging --dry-run
#   bash scripts/run_prod_backfill.sh staging --execute
#   bash scripts/run_prod_backfill.sh prod --execute --since 2026-01-01
#
# Requires: deploy with eval-improvement-loop merged; api container running.

set -euo pipefail

ENV="${1:-staging}"
shift || true

case "$ENV" in
  staging)
    COMPOSE_PROJECT="staging"
    API_CONTAINER="staging-arquivo-api"
    ;;
  prod)
    COMPOSE_PROJECT="prod"
    API_CONTAINER="arquivo-api"
    ;;
  *)
    echo "Usage: $0 {staging|prod} [--dry-run|--execute] [extra args...]" >&2
    exit 1
    ;;
esac

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! docker ps --format '{{.Names}}' | grep -qx "$API_CONTAINER"; then
  echo "Container $API_CONTAINER is not running." >&2
  exit 1
fi

echo "==> Backfill on $ENV ($API_CONTAINER)"
docker compose -p "$COMPOSE_PROJECT" exec -T api \
  python scripts/backfill_prod_cleanup.py "$@"

echo ""
echo "==> To drain requeued sources after --execute, enqueue pipeline jobs:"
cat <<EOF
docker compose -p $COMPOSE_PROJECT exec -T api python - <<'PY'
import asyncio
from arq import create_pool
from arq.connections import RedisSettings

async def main():
    redis = await create_pool(RedisSettings(host="redis", port=6379))
    await redis.enqueue_job("classify_pending_task", 300, 10)
    await redis.enqueue_job("download_classified_task", 200)
    await redis.enqueue_job("extract_ready_task", 100)
    await redis.enqueue_job("batch_enrich_task", 50)

asyncio.run(main())
PY
EOF
