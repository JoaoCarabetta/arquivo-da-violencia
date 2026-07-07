#!/bin/bash
# Verifies Hetzner, public endpoints, /metrics, and Grafana Cloud connectivity.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
if [[ -f "$REPO_DIR/.env" ]]; then set -a; source "$REPO_DIR/.env"; set +a; fi

PROD=false
for arg in "$@"; do [[ "$arg" == "--prod" ]] && PROD=true; done
API_BASE=$($PROD && echo "${OBS_API_BASE:-https://arquivodaviolencia.com.br}" || echo "${OBS_API_BASE:-http://localhost:8010}")

failures=0
pass() { echo "  OK  $1"; }
fail() { echo "  FAIL $1"; failures=$((failures + 1)); }

echo "=== Observability check ($API_BASE) ==="

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

curl -sf "$API_BASE/health" >/dev/null && pass "GET /health" || fail "GET /health"
curl -sf "$API_BASE/api/health" >/dev/null && pass "GET /api/health" || fail "GET /api/health"

metrics=$(curl -sf "$API_BASE/metrics" 2>/dev/null || true)
if echo "$metrics" | grep -q pipeline_worker_alive; then
  pass "/metrics pipeline_* metrics"
else
  fail "/metrics missing pipeline metrics"
fi

if [[ -n "${GRAFANA_CLOUD_PROM_URL:-}" && -n "${GRAFANA_CLOUD_PROM_USER:-}" && -n "${GRAFANA_CLOUD_PROM_KEY:-}" ]]; then
  code=$(curl -sS -o /dev/null -w "%{http_code}" -u "${GRAFANA_CLOUD_PROM_USER}:${GRAFANA_CLOUD_PROM_KEY}" \
    -H "Content-Type: text/plain; version=0.0.4; charset=utf-8" \
    --data-binary "pipeline_observability_check 1" "${GRAFANA_CLOUD_PROM_URL}" 2>/dev/null || echo 000)
  [[ "$code" =~ ^(200|204)$ ]] && pass "Grafana push ($code)" || fail "Grafana push (HTTP $code)"
else
  fail "Grafana Prometheus env vars not set"
fi

if [[ -n "${GRAFANA_CLOUD_LOKI_URL:-}" && -n "${GRAFANA_CLOUD_LOKI_USER:-}" && -n "${GRAFANA_CLOUD_LOKI_KEY:-}" ]]; then
  if $PROD; then
    ssh -o BatchMode=yes -o ConnectTimeout=10 hetzner-arv-public \
      'docker ps --format "{{.Names}}" | grep -q promtail' 2>/dev/null \
      && pass "Promtail on prod" || fail "Promtail not running on prod"
  else
    pass "Loki env vars set"
  fi
else
  fail "Grafana Loki env vars not set"
fi

echo "=== $failures failure(s) ==="
exit "$((failures > 0))"