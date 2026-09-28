#!/usr/bin/env bash
# One-shot Chile capture verification on staging (or prod with ENV=prod).
# Starts worker-capture only; never starts the BR process worker on staging.
# Usage (on VPS, from /root/arquivo-da-violencia):
#   bash scripts/test-chile-capture-staging.sh staging [when]
#   bash scripts/test-chile-capture-staging.sh prod [when]
set -euo pipefail

ENV="${1:-staging}"
WHEN="${2:-7d}"
cd /root/arquivo-da-violencia

if [ "$ENV" = "staging" ]; then
  COMPOSE="docker compose -p staging -f docker-compose.yml -f docker-compose.staging.yml"
  API_CONTAINER="staging-arquivo-api"
  CAPTURE_CONTAINER="staging-arquivo-worker-capture"
  PROCESS_CONTAINER="staging-arquivo-worker"
  DB_NAME="arquivo_staging"
  REDIS_QUEUE_PROCESS="arquivo:staging"
  REDIS_QUEUE_CAPTURE="arquivo:staging:capture"
else
  COMPOSE="docker compose -p prod -f docker-compose.yml"
  API_CONTAINER="arquivo-api"
  CAPTURE_CONTAINER="arquivo-worker-capture"
  PROCESS_CONTAINER="arquivo-worker"
  DB_NAME="arquivo_prod"
  REDIS_QUEUE_PROCESS="arquivo:production"
  REDIS_QUEUE_CAPTURE="arquivo:production:capture"
fi

queue_depth() {
  local key="$1"
  local t
  t=$(docker exec "$REDIS_C" redis-cli TYPE "$key" 2>/dev/null | tr -d '\r' || echo none)
  case "$t" in
    list) docker exec "$REDIS_C" redis-cli LLEN "$key" | tr -d '\r' ;;
    zset) docker exec "$REDIS_C" redis-cli ZCARD "$key" | tr -d '\r' ;;
    stream) docker exec "$REDIS_C" redis-cli XLEN "$key" | tr -d '\r' ;;
    none|"") echo 0 ;;
    *) echo "type=$t" ;;
  esac
}

cl_count() {
  local status="$1"
  docker exec -e PGPASSWORD="$PASS" arquivo-postgres \
    psql -U arquivo -d "$DB_NAME" -tAc \
    "SELECT COUNT(*) FROM source_google_news WHERE country='CL' AND status='$status'"
}

enqueue_capture() {
  local when_arg="$1"
  local enq_py=/tmp/enqueue_chile_capture.py
  cat > "$enq_py" <<PY
import asyncio
from app.tasks.worker import create_arq_capture_pool, get_arq_capture_queue_name

async def main():
    pool = await create_arq_capture_pool()
    job = await pool.enqueue_job("ingest_capture_countries_task", "${when_arg}")
    print(f"job_id={job.job_id}")
    print(f"queue={get_arq_capture_queue_name()}")
    print(f"when=${when_arg}")
    await pool.close()

asyncio.run(main())
PY
  docker cp "$enq_py" "$API_CONTAINER:/tmp/enqueue_chile_capture.py"
  docker exec "$API_CONTAINER" sh -lc \
    'cd /app && PYTHONPATH=/app /app/.venv/bin/python /tmp/enqueue_chile_capture.py'
  rm -f "$enq_py"
}

wait_for_job() {
  local job_id="$1"
  local pre_captured="$2"
  local ok=0
  for i in $(seq 1 90); do
    sleep 10
    local cur_cap q_cap
    cur_cap=$(cl_count captured)
    q_cap=$(queue_depth "$REDIS_QUEUE_CAPTURE")
    echo "[$i] captured=$cur_cap queue_capture=$q_cap"
    if docker logs --since=2m "$CAPTURE_CONTAINER" 2>&1 | grep -q "INGEST_CAPTURE] Complete"; then
      # Prefer seeing the specific job finish line
      if docker logs --since=20m "$CAPTURE_CONTAINER" 2>&1 | grep -q "$job_id"; then
        ok=1
        break
      fi
      # Fallback: complete line after enqueue and queue idle
      if [ "$q_cap" = "0" ] || [[ "$q_cap" == type=* ]]; then
        ok=1
        break
      fi
    fi
    if [ "$cur_cap" -gt "$pre_captured" ]; then
      ok=1
      break
    fi
    if [ "$(docker inspect -f '{{.State.Running}}' "$CAPTURE_CONTAINER")" != "true" ]; then
      echo "ERROR: capture worker exited during ingest"
      docker logs --tail=100 "$CAPTURE_CONTAINER" 2>&1 || true
      exit 1
    fi
  done
  echo "wait_ok=$ok"
  return 0
}

echo "=== Chile capture ops ($ENV) when=$WHEN ==="
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

PASS=$(grep -E '^POSTGRES_PASSWORD=' .env | head -1 | cut -d= -f2-)
if docker ps --format '{{.Names}}' | grep -qx 'staging-arquivo-redis'; then
  REDIS_C=staging-arquivo-redis
elif docker ps --format '{{.Names}}' | grep -qx 'arquivo-redis'; then
  REDIS_C=arquivo-redis
else
  REDIS_C=$(docker ps --format '{{.Names}}' | grep -E 'redis' | head -1)
fi
echo "redis_container=$REDIS_C"

echo ""
echo "=== Pre-ingest CL status counts ==="
PRE_CAPTURED=$(cl_count captured)
PRE_RFC=$(cl_count ready_for_classification)
echo "pre_captured=$PRE_CAPTURED pre_ready_for_classification=$PRE_RFC"

echo ""
echo "=== Redis queue depths (pre) ==="
PRE_Q_PROC=$(queue_depth "$REDIS_QUEUE_PROCESS")
PRE_Q_CAP=$(queue_depth "$REDIS_QUEUE_CAPTURE")
echo "pre_depth_process=$PRE_Q_PROC pre_depth_capture=$PRE_Q_CAP"

echo ""
echo "=== Enqueue capture ingest when=$WHEN ==="
JOB_OUT=$(enqueue_capture "$WHEN")
echo "$JOB_OUT"
JOB_ID=$(echo "$JOB_OUT" | sed -n 's/^job_id=//p' | head -1)

echo ""
echo "=== Wait for capture job ==="
wait_for_job "$JOB_ID" "$PRE_CAPTURED"

echo ""
echo "=== Capture worker logs (tail) ==="
docker logs --tail=80 "$CAPTURE_CONTAINER" 2>&1 || true

POST_CAPTURED=$(cl_count captured)
POST_RFC=$(cl_count ready_for_classification)
NEW_CAPTURED=$((POST_CAPTURED - PRE_CAPTURED))

# If the Google News window was empty, retry once with 30d
if [ "$NEW_CAPTURED" -le 0 ] && [ "$WHEN" != "30d" ]; then
  echo ""
  echo "=== No new captured rows with when=$WHEN; retry when=30d ==="
  PRE_CAPTURED=$POST_CAPTURED
  PRE_RFC=$POST_RFC
  JOB_OUT=$(enqueue_capture "30d")
  echo "$JOB_OUT"
  JOB_ID=$(echo "$JOB_OUT" | sed -n 's/^job_id=//p' | head -1)
  wait_for_job "$JOB_ID" "$PRE_CAPTURED"
  docker logs --tail=40 "$CAPTURE_CONTAINER" 2>&1 || true
  POST_CAPTURED=$(cl_count captured)
  POST_RFC=$(cl_count ready_for_classification)
  NEW_CAPTURED=$((POST_CAPTURED - PRE_CAPTURED))
fi

echo ""
echo "=== Post-ingest CL status counts ==="
POST_OTHER=$(docker exec -e PGPASSWORD="$PASS" arquivo-postgres \
  psql -U arquivo -d "$DB_NAME" -tAc \
  "SELECT status||'='||COUNT(*) FROM source_google_news WHERE country='CL' GROUP BY status ORDER BY 1")
echo "post_captured=$POST_CAPTURED post_ready_for_classification=$POST_RFC"
echo "cl_status_breakdown:"
echo "$POST_OTHER"
NEW_RFC=$((POST_RFC - PRE_RFC))

echo ""
echo "=== Redis queue depths (post) ==="
POST_Q_PROC=$(queue_depth "$REDIS_QUEUE_PROCESS")
POST_Q_CAP=$(queue_depth "$REDIS_QUEUE_CAPTURE")
echo "post_depth_process=$POST_Q_PROC post_depth_capture=$POST_Q_CAP"

echo ""
echo "=== Sample recent CL captured rows ==="
docker exec -e PGPASSWORD="$PASS" arquivo-postgres \
  psql -U arquivo -d "$DB_NAME" -c \
  "SELECT id, status, country, left(coalesce(headline,''),60) AS headline, fetched_at
   FROM source_google_news
   WHERE country='CL' AND status='captured'
   ORDER BY fetched_at DESC NULLS LAST
   LIMIT 5" || true

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
  echo "PASS: CL ready_for_classification delta=0 (still $POST_RFC preexisting)"
fi
if [ "$ENV" = "staging" ] && [ "$PROCESS_UP_AFTER" = "true" ]; then
  echo "FAIL: staging BR process worker running after test"
  FAIL=1
else
  echo "PASS: BR process worker running=$PROCESS_UP_AFTER (staging expects false)"
fi
echo "INFO: process_queue $PRE_Q_PROC -> $POST_Q_PROC ; capture_queue $PRE_Q_CAP -> $POST_Q_CAP"

if [ "$FAIL" -eq 0 ]; then
  echo "CHILE_CAPTURE_OK=yes env=$ENV"
  exit 0
fi
echo "CHILE_CAPTURE_OK=no env=$ENV"
exit 1
