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

if printf '%s\n' "$@" | grep -qx -- '--execute'; then
  echo ""
  echo "==> Enqueue pipeline jobs"
  docker compose -p "$COMPOSE_PROJECT" exec -T api \
    python scripts/enqueue_backfill_pipeline.py
fi
