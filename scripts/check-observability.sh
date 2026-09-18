#!/bin/bash
# Verifies production metrics endpoints and the self-hosted Grafana stack.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
if [[ -f "$REPO_DIR/.env" ]]; then set -a; source "$REPO_DIR/.env"; set +a; fi

PROD=false
for arg in "$@"; do [[ "$arg" == "--prod" ]] && PROD=true; done

PROD_SSH_HOST="${OBS_PROD_SSH_HOST:-hetzner-arv-public}"
PROD_SSH_USER="${OBS_PROD_SSH_USER:-root}"
PROD_SSH_KEY="${OBS_PROD_SSH_KEY:-$HOME/.ssh/hetzner_arquivo_violencia_rsa}"

GRAFANA_URL="${OBS_GRAFANA_URL:-https://observability.carabetta.xyz}"

failures=0
pass() { echo "  OK  $1"; }
fail() { echo "  FAIL $1"; failures=$((failures + 1)); }

echo "=== Observability check ($($PROD && echo prod || echo local)) ==="

if $PROD; then
  ssh_cmd=(ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$PROD_SSH_KEY" "${PROD_SSH_USER}@${PROD_SSH_HOST}")

  if "${ssh_cmd[@]}" 'curl -sf http://localhost:8000/api/health | grep -q healthy'; then
    pass "prod API /api/health"
  else
    fail "prod API /api/health"
  fi

  if "${ssh_cmd[@]}" 'bash /root/arquivo-da-violencia/scripts/check-pipeline-health.sh >/dev/null 2>&1'; then
    pass "prod pipeline health script"
  else
    fail "prod pipeline health script"
  fi

  metrics=$("${ssh_cmd[@]}" 'curl -sf http://localhost:8000/metrics' 2>/dev/null || true)
  if echo "$metrics" | grep -q 'pipeline_worker_alive'; then
    pass "prod /metrics exposes pipeline_worker_alive"
  else
    fail "prod /metrics missing pipeline_worker_alive"
  fi

  worker_metrics=$("${ssh_cmd[@]}" 'curl -sf http://localhost:9091/metrics' 2>/dev/null || true)
  if echo "$worker_metrics" | grep -q 'pipeline_task_total'; then
    pass "prod worker :9091 exposes task metrics"
  else
    fail "prod worker :9091 missing task metrics"
  fi
  if echo "$worker_metrics" | grep -q 'pipeline_worker_alive'; then
    fail "prod worker :9091 should not expose health gauges"
  else
    pass "prod worker :9091 has no health gauges"
  fi
else
  API_BASE="${OBS_API_BASE:-http://localhost:8010}"
  curl -sf "$API_BASE/api/health" | grep -q healthy && pass "GET /api/health" || fail "GET /api/health"
  metrics=$(curl -sf "$API_BASE/metrics" 2>/dev/null || true)
  if echo "$metrics" | grep -q pipeline_worker_alive; then
    pass "/metrics pipeline_* metrics"
  else
    fail "/metrics missing pipeline metrics"
  fi
fi

if curl -sf "${GRAFANA_URL}/api/health" | grep -qE '"database":\s*"ok"'; then
  pass "Grafana HTTPS (${GRAFANA_URL})"
else
  fail "Grafana not reachable at ${GRAFANA_URL}"
fi

if $PROD; then
  prom_result=$(ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$PROD_SSH_KEY" root@62.238.12.182 \
    'docker exec obs-prometheus wget -qO- "http://localhost:9090/api/v1/query?query=pipeline_worker_alive%7Bservice%3D%22api%22%7D"' 2>/dev/null || true)
  if echo "$prom_result" | grep -q '"status":"success"' && echo "$prom_result" | grep -q '"value"'; then
    pass 'Prometheus: pipeline_worker_alive{service="api"} series present'
  else
    fail 'Prometheus missing pipeline_worker_alive{service="api"} (check scrape + backend deploy)'
  fi

  rules_result=$(ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$PROD_SSH_KEY" root@62.238.12.182 \
    'docker exec obs-prometheus wget -qO- "http://localhost:9090/api/v1/rules"' 2>/dev/null || true)
  if echo "$rules_result" | grep -q 'WorkerDown'; then
    pass "Prometheus alert rules loaded (WorkerDown)"
  else
    fail "Prometheus alert rules missing (check rules mount + deploy)"
  fi

  am_result=$(ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$PROD_SSH_KEY" root@62.238.12.182 \
    'docker exec obs-alertmanager wget -qO- http://localhost:9093/-/ready' 2>/dev/null || true)
  if echo "$am_result" | grep -q 'OK'; then
    pass "Alertmanager ready"
  else
    fail "Alertmanager not ready"
  fi

  if ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$PROD_SSH_KEY" root@62.238.12.182 \
    'docker exec obs-alert-router python -c "import urllib.request; urllib.request.urlopen(\"http://127.0.0.1:8080/health\")"' >/dev/null 2>&1; then
    pass "Alert-router health OK"
  else
    fail "Alert-router not healthy"
  fi

  # --- MCP endpoint (mcp-grafana) ---
  mcp_url="${GRAFANA_URL%/}/mcp"
  mcp_unauth=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 -X POST "$mcp_url" \
    -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
    -d '{"jsonrpc":"2.0","id":0,"method":"ping"}' || true)
  if [[ "$mcp_unauth" == "401" ]]; then
    pass "MCP rejects unauthenticated calls (401)"
  else
    fail "MCP unauthenticated call returned '$mcp_unauth' (expected 401)"
  fi

  mcp_token=$(ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$PROD_SSH_KEY" root@62.238.12.182 \
    'grep -E "^MCP_GRAFANA_SERVER_TOKEN=" /opt/arquivo-observability/.env | cut -d= -f2-' 2>/dev/null || true)
  if [[ -n "$mcp_token" ]]; then
    mcp_hdrs=(-H "Authorization: Bearer $mcp_token" -H 'Content-Type: application/json' \
      -H 'Accept: application/json, text/event-stream')
    init_headers_file=$(mktemp)
    init_resp=$(curl -s --max-time 20 -D "$init_headers_file" -X POST "$mcp_url" "${mcp_hdrs[@]}" \
      -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"check-observability","version":"1.0"}}}' || true)
    mcp_session=$(awk 'tolower($1)=="mcp-session-id:"{print $2}' "$init_headers_file" | tr -d '\r')
    rm -f "$init_headers_file"
    session_hdr=()
    [[ -n "$mcp_session" ]] && session_hdr=(-H "Mcp-Session-Id: $mcp_session")
    if echo "$init_resp" | grep -q 'serverInfo'; then
      curl -s --max-time 20 -o /dev/null -X POST "$mcp_url" "${mcp_hdrs[@]}" "${session_hdr[@]}" \
        -d '{"jsonrpc":"2.0","method":"notifications/initialized"}' || true
      tools_resp=$(curl -s --max-time 20 -X POST "$mcp_url" "${mcp_hdrs[@]}" "${session_hdr[@]}" \
        -d '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' || true)
      if echo "$tools_resp" | grep -q 'query_prometheus'; then
        pass "MCP authed tools/list exposes query_prometheus"
      else
        fail "MCP authed tools/list missing query_prometheus"
      fi
      ds_resp=$(curl -s --max-time 30 -X POST "$mcp_url" "${mcp_hdrs[@]}" "${session_hdr[@]}" \
        -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"list_datasources","arguments":{}}}' || true)
      if echo "$ds_resp" | grep -qi 'prometheus'; then
        pass "MCP → Grafana → datasource chain OK"
      else
        fail "MCP list_datasources failed (service account token?)"
      fi
    else
      fail "MCP initialize failed with bearer token"
    fi
  else
    fail "Could not read MCP_GRAFANA_SERVER_TOKEN from obs VPS .env"
  fi
fi

echo "=== $failures failure(s) ==="
exit "$((failures > 0))"
