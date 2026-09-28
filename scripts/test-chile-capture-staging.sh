#!/usr/bin/env bash
# One-shot Chile capture verification on staging (or prod with ENV=prod).
# Starts worker-capture only; never starts the BR process worker on staging.
# Usage (on VPS, from /root/arquivo-da-violencia):
#   bash scripts/test-chile-capture-staging.sh staging
#   bash scripts/test-chile-capture-staging.sh prod
set -euo pipefail

ENV="${1:-staging}"
cd /root/arquivo-da-violencia

if [ "$ENV" = "staging" ]; then
  COMPOSE="docker compose -p staging -f docker-compose.yml -f docker-compose.staging.yml"
  API_CONTAINER="staging-arquivo-api"
  CAPTURE_CONTAINER="staging-arquivo-worker-capture"
  PROCESS_CONTAINER="staging-arquivo-worker"
  DB_NAME="arquivo_staging"
  REDIS_QUEUE_PROCESS="arquivo:staging"
  REDIS_QUEUE_CAPTURE="arquivo:staging:capture"
  API_BASE="http://127.0.0.1:8001"
else
  COMPOSE="docker compose -p prod -f docker-compose.yml"
  API_CONTAINER="arquivo-api"
  CAPTURE_CONTAINER="arquivo-worker-capture"
  PROCESS_CONTAINER="arquivo-worker"
  DB_NAME="arquivo_prod"
  REDIS_QUEUE_PROCESS="arquivo:production"
  REDIS_QUEUE_CAPTURE="arquivo:production:capture"
  API_BASE="http://127.0.0.1:8000"
fi

echo "=== Chile capture ops ($ENV) ==="
echo "git: $(git rev-parse --short HEAD) $(git log -1 --pretty=%s)"
echo "branch: $(git rev-parse --abbrev-ref HEAD)"

echo ""
echo "=== API capture countries env ==="
docker inspect "$API_CONTAINER" --format '{{range .Config.Env}}{{println .}}{{end}}' \
  | grep -E 'PIPELINE_(CAPTURE|ACTIVE)_COUNTRIES|ENVIRONMENT' || true

echo ""
echo "=== Pull + start worker-capture (process worker untouched) ==="
# shellcheck disable=SC2086
$COMPOSE pull worker-capture
# shellcheck disable=SC2086
$COMPOSE up -d --no-deps worker-capture

sleep 5
echo ""
echo "=== Container states ==="
docker ps -a --filter "name=${CAPTURE_CONTAINER}" --filter "name=${PROCESS_CONTAINER}" \
  --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'

CAPTURE_UP=$(docker inspect -f '{{.State.Running}}' "$CAPTURE_CONTAINER" 2>/dev/null || echo false)
PROCESS_UP=$(docker inspect -f '{{.State.Running}}' "$PROCESS_CONTAINER" 2>/dev/null || echo false)
echo "capture_running=$CAPTURE_UP process_running=$PROCESS_UP"

if [ "$CAPTURE_UP" != "true" ]; then
  echo "ERROR: capture worker not running"
  docker logs --tail=80 "$CAPTURE_CONTAINER" 2>&1 || true
  exit 1
fi

if [ "$ENV" = "staging" ] && [ "$PROCESS_UP" = "true" ]; then
  echo "ERROR: staging BR process worker is running (should stay stopped)"
  exit 1
fi

echo ""
echo "=== Pre-ingest CL status counts ==="
PASS=$(grep -E '^POSTGRES_PASSWORD=' .env | head -1 | cut -d= -f2-)
PRE_CAPTURED=$(docker exec -e PGPASSWORD="$PASS" arquivo-postgres \
  psql -U arquivo -d "$DB_NAME" -tAc \
  "SELECT COUNT(*) FROM source_google_news WHERE country='CL' AND status='captured'")
PRE_RFC=$(docker exec -e PGPASSWORD="$PASS" arquivo-postgres \
  psql -U arquivo -d "$DB_NAME" -tAc \
  "SELECT COUNT(*) FROM source_google_news WHERE country='CL' AND status='ready_for_classification'")
echo "pre_captured=$PRE_CAPTURED pre_ready_for_classification=$PRE_RFC"

echo ""
echo "=== Redis queue depths (pre) ==="
# Staging redis is published on host 6380 in some setups; prefer docker exec.
if docker ps --format '{{.Names}}' | grep -qx 'staging-arquivo-redis'; then
  REDIS_C=staging-arquivo-redis
elif docker ps --format '{{.Names}}' | grep -qx 'arquivo-redis'; then
  REDIS_C=arquivo-redis
else
  REDIS_C=$(docker ps --format '{{.Names}}' | grep -E 'redis' | head -1)
fi
echo "redis_container=$REDIS_C"
PRE_Q_PROC=$(docker exec "$REDIS_C" redis-cli LLEN "$REDIS_QUEUE_PROCESS" || echo err)
PRE_Q_CAP=$(docker exec "$REDIS_C" redis-cli LLEN "$REDIS_QUEUE_CAPTURE" || echo err)
echo "pre_llen_process=$PRE_Q_PROC pre_llen_capture=$PRE_Q_CAP"

echo ""
echo "=== Enqueue capture ingest via API container (bypass HTTP auth) ==="
ENQ_PY=/tmp/enqueue_chile_capture.py
cat > "$ENQ_PY" <<'PY'
import asyncio
from app.tasks.worker import create_arq_capture_pool, get_arq_capture_queue_name

async def main():
    pool = await create_arq_capture_pool()
    job = await pool.enqueue_job("ingest_capture_countries_task", "1h")
    print(f"job_id={job.job_id}")
    print(f"queue={get_arq_capture_queue_name()}")
    await pool.close()

asyncio.run(main())
PY
docker cp "$ENQ_PY" "$API_CONTAINER:/tmp/enqueue_chile_capture.py"
JOB_OUT=$(docker exec -w /app -e PYTHONPATH=/app "$API_CONTAINER" \
  python /tmp/enqueue_chile_capture.py)
echo "$JOB_OUT"
rm -f "$ENQ_PY"

echo ""
echo "=== Wait for capture job (up to 15m) ==="
OK=0
for i in $(seq 1 90); do
  sleep 10
  # Job done when capture queue empty AND captured count increased OR worker idle
  CUR_CAP=$(docker exec -e PGPASSWORD="$PASS" arquivo-postgres \
    psql -U arquivo -d "$DB_NAME" -tAc \
    "SELECT COUNT(*) FROM source_google_news WHERE country='CL' AND status='captured'")
  Q_CAP=$(docker exec "$REDIS_C" redis-cli LLEN "$REDIS_QUEUE_CAPTURE" || echo 0)
  # Also count recent jobs in arq result keys if available
  echo "[$i] captured=$CUR_CAP queue_capture=$Q_CAP"
  if [ "$CUR_CAP" -gt "$PRE_CAPTURED" ] && [ "$Q_CAP" = "0" ]; then
    OK=1
    break
  fi
  # Fail fast if capture worker died
  if [ "$(docker inspect -f '{{.State.Running}}' "$CAPTURE_CONTAINER")" != "true" ]; then
    echo "ERROR: capture worker exited during ingest"
    docker logs --tail=100 "$CAPTURE_CONTAINER" 2>&1 || true
    exit 1
  fi
done

echo ""
echo "=== Capture worker logs (tail) ==="
docker logs --tail=60 "$CAPTURE_CONTAINER" 2>&1 || true

echo ""
echo "=== Post-ingest CL status counts ==="
POST_CAPTURED=$(docker exec -e PGPASSWORD="$PASS" arquivo-postgres \
  psql -U arquivo -d "$DB_NAME" -tAc \
  "SELECT COUNT(*) FROM source_google_news WHERE country='CL' AND status='captured'")
POST_RFC=$(docker exec -e PGPASSWORD="$PASS" arquivo-postgres \
  psql -U arquivo -d "$DB_NAME" -tAc \
  "SELECT COUNT(*) FROM source_google_news WHERE country='CL' AND status='ready_for_classification'")
POST_OTHER=$(docker exec -e PGPASSWORD="$PASS" arquivo-postgres \
  psql -U arquivo -d "$DB_NAME" -tAc \
  "SELECT status||'='||COUNT(*) FROM source_google_news WHERE country='CL' GROUP BY status ORDER BY 1")
echo "post_captured=$POST_CAPTURED post_ready_for_classification=$POST_RFC"
echo "cl_status_breakdown:"
echo "$POST_OTHER"

NEW_CAPTURED=$((POST_CAPTURED - PRE_CAPTURED))
NEW_RFC=$((POST_RFC - PRE_RFC))

echo ""
echo "=== Redis queue depths (post) ==="
POST_Q_PROC=$(docker exec "$REDIS_C" redis-cli LLEN "$REDIS_QUEUE_PROCESS" || echo err)
POST_Q_CAP=$(docker exec "$REDIS_C" redis-cli LLEN "$REDIS_QUEUE_CAPTURE" || echo err)
echo "post_llen_process=$POST_Q_PROC post_llen_capture=$POST_Q_CAP"

# Sample recent CL rows
echo ""
echo "=== Sample recent CL captured rows ==="
docker exec -e PGPASSWORD="$PASS" arquivo-postgres \
  psql -U arquivo -d "$DB_NAME" -c \
  "SELECT id, status, country, left(title,60) AS title, created_at
   FROM source_google_news
   WHERE country='CL' AND status='captured'
   ORDER BY created_at DESC NULLS LAST
   LIMIT 5"

PROCESS_UP_AFTER=$(docker inspect -f '{{.State.Running}}' "$PROCESS_CONTAINER" 2>/dev/null || echo false)

echo ""
echo "=== VERDICT ==="
FAIL=0
if [ "$NEW_CAPTURED" -le 0 ]; then
  echo "FAIL: no new CL captured sources (delta=$NEW_CAPTURED)"
  FAIL=1
else
  echo "PASS: new CL captured sources=$NEW_CAPTURED"
fi
if [ "$NEW_RFC" -ne 0 ]; then
  echo "FAIL: CL ready_for_classification increased by $NEW_RFC (should be 0)"
  FAIL=1
else
  echo "PASS: CL ready_for_classification delta=0"
fi
if [ "$ENV" = "staging" ] && [ "$PROCESS_UP_AFTER" = "true" ]; then
  echo "FAIL: staging BR process worker running after test"
  FAIL=1
else
  echo "PASS: BR process worker running=$PROCESS_UP_AFTER (staging expects false)"
fi
# Process queue should not grow from capture (allow same depth)
echo "INFO: process_queue $PRE_Q_PROC -> $POST_Q_PROC ; capture_queue $PRE_Q_CAP -> $POST_Q_CAP"

if [ "$FAIL" -eq 0 ]; then
  echo "CHILE_CAPTURE_OK=yes env=$ENV"
  exit 0
fi
echo "CHILE_CAPTURE_OK=no env=$ENV"
exit 1
