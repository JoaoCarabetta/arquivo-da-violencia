#!/bin/bash
# =============================================================================
# Production pipeline health check
# =============================================================================
# Verifies API, worker heartbeat, recent cron activity, stuck sources, and
# recent classification errors. Exits 0 when healthy, 1 when not.
#
# Usage (on VPS):
#   ./scripts/check-pipeline-health.sh
#   ./scripts/check-pipeline-health.sh --notify          # Telegram + webhook on failure
#   ./scripts/check-pipeline-health.sh --remediate         # Tier-A fixes for stuck rows
#   ./scripts/check-pipeline-health.sh --test-webhook    # POST test payload to Cursor webhook
#
# Environment (read from $REPO_DIR/.env when present):
#   TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
#   PIPELINE_HEALTH_WEBHOOK_URL, PIPELINE_HEALTH_WEBHOOK_AUTH (Cursor Bearer crsr_…)
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/deploy-common.sh"

COMPOSE_PROD="-p prod -f docker-compose.yml"
API_PORT="${PIPELINE_HEALTH_API_PORT:-8000}"
WORKER_CONTAINER="${PIPELINE_HEALTH_WORKER_CONTAINER:-arquivo-worker}"
REDIS_HEALTH_KEY="${PIPELINE_HEALTH_REDIS_KEY:-arq:queue:health-check}"
WORKER_INFO_KEY="${PIPELINE_HEALTH_WORKER_INFO_KEY:-}"

# How long since the last hourly cron may have started (minute :05 UTC).
MAX_PIPELINE_AGE_MINUTES="${PIPELINE_HEALTH_MAX_PIPELINE_AGE_MINUTES:-100}"
STUCK_SOURCE_MINUTES="${PIPELINE_HEALTH_STUCK_SOURCE_MINUTES:-15}"
LOG_LOOKBACK_MINUTES="${PIPELINE_HEALTH_LOG_LOOKBACK_MINUTES:-120}"
READY_BACKLOG_WARN="${PIPELINE_HEALTH_READY_BACKLOG_WARN:-1500}"

NOTIFY=false
REMEDIATE=false
JSON=false
TEST_WEBHOOK=false

for arg in "$@"; do
    case "$arg" in
        --notify) NOTIFY=true ;;
        --remediate) REMEDIATE=true ;;
        --json) JSON=true ;;
        --test-webhook) TEST_WEBHOOK=true ;;
        -h|--help)
            sed -n '2,20p' "$0"
            exit 0
            ;;
        *)
            echo "Unknown option: $arg" >&2
            exit 2
            ;;
    esac
done

cd "$REPO_DIR"
load_env

FAILURES=()
WARNINGS=()
DETAILS=()

read_env_var() {
    local key="$1"
    local env_file="$REPO_DIR/.env"
    [ -f "$env_file" ] || return 0
    grep -m1 "^${key}=" "$env_file" | cut -d= -f2- | tr -d '\r' || true
}

TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-$(read_env_var TELEGRAM_BOT_TOKEN)}"
TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:-$(read_env_var TELEGRAM_CHAT_ID)}"
PIPELINE_HEALTH_WEBHOOK_URL="${PIPELINE_HEALTH_WEBHOOK_URL:-$(read_env_var PIPELINE_HEALTH_WEBHOOK_URL)}"
PIPELINE_HEALTH_WEBHOOK_AUTH="${PIPELINE_HEALTH_WEBHOOK_AUTH:-$(read_env_var PIPELINE_HEALTH_WEBHOOK_AUTH)}"
PIPELINE_HEALTH_WEBHOOK_AUTH="${PIPELINE_HEALTH_WEBHOOK_AUTH:-$(read_env_var CURSOR_AUTOMATION_TOKEN)}"
ENVIRONMENT="${ENVIRONMENT:-$(read_env_var ENVIRONMENT)}"
ENVIRONMENT="${ENVIRONMENT:-production}"
WORKER_INFO_KEY="${WORKER_INFO_KEY:-arquivo:worker:info:${ENVIRONMENT}}"

record_failure() {
    FAILURES+=("$1")
    DETAILS+=("FAIL: $1")
}

record_warning() {
    WARNINGS+=("$1")
    DETAILS+=("WARN: $1")
}

psql_prod() {
    docker compose $COMPOSE_PROD exec -T postgres \
        psql -U arquivo -d arquivo_prod -v ON_ERROR_STOP=1 -At -c "$1"
}

echo_step() {
    if [ "$JSON" = false ]; then
        echo "$1"
    fi
}

# --- Checks -------------------------------------------------------------------

echo_step "🏥 Pipeline health check ($(date -u +%Y-%m-%dT%H:%M:%SZ))"

if ! curl -sf "http://localhost:${API_PORT}/health" >/dev/null 2>&1; then
    record_failure "api_health"
else
    DETAILS+=("OK: api_health")
fi

worker_status="$(docker inspect --format='{{.State.Health.Status}}' "$WORKER_CONTAINER" 2>/dev/null || echo missing)"
if [ "$worker_status" != "healthy" ]; then
    record_failure "worker_container_unhealthy(status=${worker_status})"
else
    DETAILS+=("OK: worker_container")
fi

heartbeat="$(docker compose $COMPOSE_PROD exec -T redis redis-cli GET "$REDIS_HEALTH_KEY" 2>/dev/null | tr -d '\r' || true)"
if [ -z "$heartbeat" ] || [ "$heartbeat" = "(nil)" ]; then
    record_failure "worker_heartbeat_missing"
else
    DETAILS+=("OK: worker_heartbeat")
fi

cron_enabled="$(docker compose $COMPOSE_PROD exec -T redis redis-cli GET "$WORKER_INFO_KEY" 2>/dev/null | tr -d '\r' || true)"
if echo "$cron_enabled" | grep -q '"cron_enabled": true'; then
  if docker logs "$WORKER_CONTAINER" --since "${MAX_PIPELINE_AGE_MINUTES}m" 2>&1 \
      | grep -qE 'cron:ingest_cities_full_pipeline|CITIES_PIPELINE\] Starting'; then
      DETAILS+=("OK: recent_pipeline_activity")
  else
      record_failure "no_recent_pipeline_run(within_${MAX_PIPELINE_AGE_MINUTES}m)"
  fi
else
    record_warning "cron_disabled_on_worker"
fi

stuck_count="$(psql_prod "
SELECT COUNT(*)
FROM source_google_news
WHERE status IN ('classifying', 'downloading', 'extracting')
  AND updated_at < now() - interval '${STUCK_SOURCE_MINUTES} minutes';
" 2>/dev/null || echo "error")"

if [ "$stuck_count" = "error" ]; then
    record_failure "stuck_sources_query_failed"
elif [ "${stuck_count:-0}" -gt 0 ]; then
    record_failure "stuck_sources(count=${stuck_count})"
else
    DETAILS+=("OK: stuck_sources")
fi

classify_errors="$(
    docker logs "$WORKER_CONTAINER" --since "${LOG_LOOKBACK_MINUTES}m" 2>&1 \
        | grep -E 'Classification complete:' \
        | tail -5 \
        | sed -n 's/.*, \([0-9][0-9]*\) errors/\1/p' \
        | awk '{s+=$1} END {print s+0}' || true
)"
if [ "${classify_errors:-0}" -gt 0 ]; then
    record_failure "classification_errors(last_${LOG_LOOKBACK_MINUTES}m=${classify_errors})"
else
    DETAILS+=("OK: classification_errors")
fi

if docker logs "$WORKER_CONTAINER" --since "${LOG_LOOKBACK_MINUTES}m" 2>&1 \
    | grep -qE 'Maintenance step failed|ProgrammingError|UndefinedFunctionError'; then
    record_failure "maintenance_or_sql_errors_in_logs"
else
    DETAILS+=("OK: maintenance_logs")
fi

ready_backlog="$(psql_prod "
SELECT COUNT(*) FROM source_google_news WHERE status = 'ready_for_classification';
" 2>/dev/null || echo "error")"
if [ "$ready_backlog" = "error" ]; then
    record_warning "ready_backlog_query_failed"
elif [ "${ready_backlog:-0}" -ge "$READY_BACKLOG_WARN" ]; then
    record_warning "large_classification_backlog(count=${ready_backlog})"
else
    DETAILS+=("OK: ready_backlog(${ready_backlog})")
fi

# --- Tier-A remediation -------------------------------------------------------

if [ "$REMEDIATE" = true ]; then
    had_stuck=false
    for f in "${FAILURES[@]:-}"; do
        if [[ "$f" == stuck_sources* ]]; then
            had_stuck=true
            break
        fi
    done
    if [ "$had_stuck" = true ]; then
        echo_step "🔧 Tier-A: resetting stuck transient source statuses..."
        if ! psql_prod "
UPDATE source_google_news
SET status = CASE status
    WHEN 'classifying' THEN 'ready_for_classification'
    WHEN 'downloading' THEN 'ready_for_download'
    WHEN 'extracting' THEN 'ready_for_extraction'
    ELSE status
END,
updated_at = CURRENT_TIMESTAMP
WHERE status IN ('classifying', 'downloading', 'extracting')
  AND updated_at < now() - interval '${STUCK_SOURCE_MINUTES} minutes';
" >/dev/null 2>&1; then
            record_failure "remediate_stuck_sources_failed"
        else
            stuck_after="$(psql_prod "
SELECT COUNT(*)
FROM source_google_news
WHERE status IN ('classifying', 'downloading', 'extracting')
  AND updated_at < now() - interval '${STUCK_SOURCE_MINUTES} minutes';
" 2>/dev/null || echo "error")"
            DETAILS+=("REMEDIATE: stuck_sources_remaining=${stuck_after}")
            if [ "$stuck_after" = "0" ]; then
                filtered=()
                for f in "${FAILURES[@]}"; do
                    [[ "$f" == stuck_sources* ]] && continue
                    filtered+=("$f")
                done
                FAILURES=("${filtered[@]}")
                DETAILS+=("OK: stuck_sources_after_remediate")
            fi
        fi
    fi
fi

# --- Notify -------------------------------------------------------------------

send_telegram() {
    local text="$1"
    [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ] || return 0
    curl -sf -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d "chat_id=${TELEGRAM_CHAT_ID}" \
        --data-urlencode "text=${text}" \
        -d "parse_mode=HTML" \
        -d "disable_notification=false" >/dev/null || true
}

send_webhook() {
    local payload="$1"
    [ -n "${PIPELINE_HEALTH_WEBHOOK_URL:-}" ] || return 0

    local token="${PIPELINE_HEALTH_WEBHOOK_AUTH:-}"
    token="${token#Bearer }"

    local -a curl_args=(
        -s -w "%{http_code}" -o /tmp/pipeline_health_webhook_resp.txt
        -X POST "$PIPELINE_HEALTH_WEBHOOK_URL"
        -H "Content-Type: application/json"
        -d "$payload"
    )
    if [ -n "$token" ]; then
        curl_args+=(-H "Authorization: Bearer ${token}")
    fi

    local http_code
    http_code=$(curl "${curl_args[@]}" 2>/dev/null || echo "000")
    if [ "$http_code" -lt 200 ] || [ "$http_code" -ge 300 ]; then
        local body
        body="$(tr -d '\n' </tmp/pipeline_health_webhook_resp.txt 2>/dev/null | head -c 200)"
        WEBHOOK_LAST_ERROR="http_${http_code}${body:+:${body}}"
        return 1
    fi
    WEBHOOK_LAST_ERROR=""
    return 0
}

# --- Summary ------------------------------------------------------------------

STATUS="healthy"
if [ "${#FAILURES[@]}" -gt 0 ]; then
    STATUS="unhealthy"
fi

json_array() {
    if [ "$#" -eq 0 ]; then
        echo '[]'
    else
        printf '%s\n' "$@" | python3 -c 'import json,sys; print(json.dumps([l for l in sys.stdin.read().splitlines() if l]))'
    fi
}

if [ "$TEST_WEBHOOK" = true ]; then
    echo_step "🔔 Sending test webhook to Cursor Automation..."
    if [ -z "${PIPELINE_HEALTH_WEBHOOK_AUTH:-}" ]; then
        record_failure "webhook_auth_missing(set PIPELINE_HEALTH_WEBHOOK_AUTH or CURSOR_AUTOMATION_TOKEN)"
    elif ! send_webhook "$(python3 - <<PY
import json
print(json.dumps({
    "status": "${STATUS}",
    "test": True,
    "failures": $(json_array ${FAILURES[@]+"${FAILURES[@]}"}),
    "warnings": $(json_array ${WARNINGS[@]+"${WARNINGS[@]}"}),
    "host": "$(hostname -s)",
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "prompt": "TEST: Pipeline health automation check. SSH to hetzner-arv, run: cd /root/arquivo-da-violencia && bash scripts/check-pipeline-health.sh --json && docker logs arquivo-worker --tail 30. Reply with a one-line summary of pipeline status. Do not open PRs for this test.",
}))
PY
)"; then
        record_failure "webhook_test_failed(${WEBHOOK_LAST_ERROR:-unknown})"
    else
        DETAILS+=("OK: test_webhook_sent")
    fi
    if [ "${#FAILURES[@]}" -gt 0 ]; then
        STATUS="unhealthy"
    fi
fi

if [ "$JSON" = true ]; then
    python3 - <<PY
import json
print(json.dumps({
    "status": "${STATUS}",
    "failures": $(json_array ${FAILURES[@]+"${FAILURES[@]}"}),
    "warnings": $(json_array ${WARNINGS[@]+"${WARNINGS[@]}"}),
    "details": $(json_array ${DETAILS[@]+"${DETAILS[@]}"}),
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
}))
PY
else
    echo ""
    echo "Status: ${STATUS}"
    if [ "${#FAILURES[@]}" -gt 0 ]; then
        echo "Failures:"
        printf '  - %s\n' "${FAILURES[@]}"
    fi
    if [ "${#WARNINGS[@]}" -gt 0 ]; then
        echo "Warnings:"
        printf '  - %s\n' "${WARNINGS[@]}"
    fi
fi

if [ "$STATUS" = "unhealthy" ] && [ "$NOTIFY" = true ]; then
    summary="Pipeline UNHEALTHY on $(hostname -s)
Failures: $(IFS=, ; echo "${FAILURES[*]}")"
    if [ "${#WARNINGS[@]}" -gt 0 ]; then
        summary="${summary}
Warnings: $(IFS=, ; echo "${WARNINGS[*]}")"
    fi
    send_telegram "$summary"
    if ! send_webhook "$(python3 - <<PY
import json
print(json.dumps({
    "status": "unhealthy",
    "failures": $(json_array ${FAILURES[@]+"${FAILURES[@]}"}),
    "warnings": $(json_array ${WARNINGS[@]+"${WARNINGS[@]}"}),
    "host": "$(hostname -s)",
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "prompt": "Production pipeline unhealthy. SSH to hetzner-arv, run scripts/check-pipeline-health.sh, inspect docker logs arquivo-worker --since 2h and pipeline_attempt in arquivo_prod. Apply Tier-A remediation if safe; otherwise open a PR to develop with a minimal fix. Do not push master directly.",
}))
PY
)"; then
        record_warning "webhook_notify_failed(${WEBHOOK_LAST_ERROR:-unknown})"
    fi
fi

if [ "$STATUS" = "unhealthy" ]; then
    exit 1
fi

exit 0
