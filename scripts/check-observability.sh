#!/bin/bash
# Verifies Hetzner, endpoints, /metrics, and Grafana Cloud connectivity.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
if [[ -f "$REPO_DIR/.env" ]]; then set -a; source "$REPO_DIR/.env"; set +a; fi

PROD=false
for arg in "$@"; do [[ "$arg" == "--prod" ]] && PROD=true; done

SSH_HOST="${OBS_SSH_HOST:-hetzner-arv-public}"
SSH_USER="${OBS_SSH_USER:-root}"
SSH_KEY="${OBS_SSH_KEY:-$HOME/.ssh/hetzner_arquivo_violencia_rsa}"

failures=0
pass() { echo "  OK  $1"; }
fail() { echo "  FAIL $1"; failures=$((failures + 1)); }

echo "=== Observability check ($($PROD && echo prod || echo local)) ==="

if [[ -n "${HETZNER_API_TOKEN:-}" ]]; then
  hetzner_status=$(curl -sS -H "Authorization: Bearer $HETZNER_API_TOKEN" https://api.hetzner.cloud/v1/servers | python3 -c "
import sys,json
d=json.load(sys.stdin)
s=d.get('servers',[])
print('error' if not s else f\"{s[0]['name']}|{s[0]['status']}\")
" 2>/dev/null || echo error)
  [[ "$hetzner_status" == *"|running" ]] && pass "Hetzner ($hetzner_status)" || fail "Hetzner ($hetzner_status)"
else
  fail "HETZNER_API_TOKEN not set"
fi

if $PROD; then
  ssh_cmd=(ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$SSH_KEY" "${SSH_USER}@${SSH_HOST}")
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
  if echo "$metrics" | grep -q pipeline_worker_alive; then
    pass "prod /metrics pipeline_* metrics"
  else
    fail "prod /metrics missing pipeline metrics"
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

if [[ -n "${GRAFANA_CLOUD_PROM_URL:-}" && -n "${GRAFANA_CLOUD_PROM_USER:-}" && -n "${GRAFANA_CLOUD_PROM_KEY:-}" ]]; then
  code=$(curl -sS -o /dev/null -w "%{http_code}" -u "${GRAFANA_CLOUD_PROM_USER}:${GRAFANA_CLOUD_PROM_KEY}" \
    -H "Content-Type: text/plain; version=0.0.4; charset=utf-8" \
    --data-binary "pipeline_observability_check 1" "${GRAFANA_CLOUD_PROM_URL}" 2>/dev/null || echo 000)
  [[ "$code" =~ ^(200|204)$ ]] && pass "Grafana push ($code)" || fail "Grafana push (HTTP $code)"
else
  fail "Grafana Prometheus env vars not set (see docs/observability-setup.md)"
fi

if [[ -n "${GRAFANA_CLOUD_LOKI_URL:-}" && -n "${GRAFANA_CLOUD_LOKI_USER:-}" && -n "${GRAFANA_CLOUD_LOKI_KEY:-}" ]]; then
  if $PROD; then
    if "${ssh_cmd[@]}" 'docker ps --format "{{.Names}}" | grep -q promtail' 2>/dev/null; then
      pass "Promtail on prod"
    else
      fail "Promtail not running (docker compose -p prod --profile logs up -d promtail)"
    fi
  else
    pass "Loki env vars set"
  fi
else
  fail "Grafana Loki env vars not set"
fi

echo "=== $failures failure(s) ==="
exit "$((failures > 0))"
