#!/usr/bin/env bash
# Send test Alertmanager payloads to alert-router (local or obs VPS).
# Usage:
#   ./scripts/test-alert-router.sh warning          # Telegram only
#   ./scripts/test-alert-router.sh critical         # Telegram + Cursor webhook
#   ./scripts/test-alert-router.sh --obs warning    # against obs VPS container
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SEVERITY="${1:-warning}"
TARGET="local"

if [[ "${1:-}" == "--obs" ]]; then
  TARGET="obs"
  SEVERITY="${2:-warning}"
fi

case "$SEVERITY" in
  warning)
    ALERT_NAME="StuckSourcesWarning"
    SEV="warning"
    AGENT="false"
    ;;
  critical)
    ALERT_NAME="WorkerDown"
    SEV="critical"
    AGENT="true"
    ;;
  *)
    echo "Usage: $0 [--obs] {warning|critical}" >&2
    exit 1
    ;;
esac

payload=$(python3 - <<PY
import json
print(json.dumps({
    "receiver": "alert-router",
    "status": "firing",
    "alerts": [{
        "status": "firing",
        "labels": {
            "alertname": "${ALERT_NAME}",
            "severity": "${SEV}",
            "agent": "${AGENT}",
            "category": "test",
        },
        "annotations": {
            "summary": "TEST: ${ALERT_NAME} from test-alert-router.sh",
            "description": "Synthetic alert — safe to ignore.",
        },
        "startsAt": "2026-01-01T00:00:00Z",
        "endsAt": "0001-01-01T00:00:00Z",
    }],
}))
PY
)

read_router_secret() {
  if [[ -n "${ALERT_ROUTER_WEBHOOK_SECRET:-}" ]]; then
    echo "$ALERT_ROUTER_WEBHOOK_SECRET"
    return
  fi
  if [[ "$TARGET" == "obs" ]]; then
    SSH_KEY="${OBS_SSH_KEY:-$HOME/.ssh/hetzner_arquivo_violencia_rsa}"
    ssh -o BatchMode=yes -i "$SSH_KEY" root@62.238.12.182 \
      'grep -E "^ALERT_ROUTER_WEBHOOK_SECRET=" /opt/arquivo-observability/.env | cut -d= -f2-'
    return
  fi
  echo "Set ALERT_ROUTER_WEBHOOK_SECRET or use --obs" >&2
  exit 1
}

ROUTER_SECRET="$(read_router_secret)"
AUTH_HEADER="Authorization: Bearer ${ROUTER_SECRET}"

if [[ "$TARGET" == "obs" ]]; then
  SSH_KEY="${OBS_SSH_KEY:-$HOME/.ssh/hetzner_arquivo_violencia_rsa}"
  echo "Posting test ${SEVERITY} alert to obs-alert-router..."
  echo "$payload" | ssh -o BatchMode=yes -i "$SSH_KEY" root@62.238.12.182 \
    "docker exec -i -e AUTH='${ROUTER_SECRET}' obs-alert-router python -c \"
import json, sys, urllib.request, os
payload = json.load(sys.stdin)
req = urllib.request.Request(
    'http://127.0.0.1:8080/alerts',
    data=json.dumps(payload).encode(),
    headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {os.environ[\"AUTH\"]}'},
    method='POST',
)
with urllib.request.urlopen(req) as resp:
    print(resp.read().decode())
\""
else
  PORT="${ALERT_ROUTER_PORT:-8080}"
  echo "Posting test ${SEVERITY} alert to http://127.0.0.1:${PORT}/alerts ..."
  curl -sf -X POST "http://127.0.0.1:${PORT}/alerts" \
    -H "Content-Type: application/json" \
    -H "$AUTH_HEADER" \
    -d "$payload"
  echo ""
fi

echo "Done. Check Telegram (and Cursor for critical)."
