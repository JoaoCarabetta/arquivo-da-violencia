#!/usr/bin/env bash
# Run the full 6-stage eval suite and print the 100% gate summary.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"

OUTPUT="${1:-eval/results/run-all-$(date +%Y%m%d-%H%M%S).json}"

if docker compose -f docker-compose.dev.yml ps api 2>/dev/null | grep -q running; then
  docker compose -f docker-compose.dev.yml exec -T api \
    python -m eval improvement run-all --output "$OUTPUT"
else
  docker run --rm --env-file .env \
    -v "$PWD/backend/eval:/app/eval" \
    -v "$PWD/backend/tests:/app/tests" \
    -v "$PWD/backend/app:/app/app:ro" \
    arquivo-da-violencia-api \
    python -m eval improvement run-all --output "$OUTPUT"
fi

echo "Summary written to backend/$OUTPUT"
