#!/usr/bin/env bash
# Laptop wrapper: sync observability stack to obs VPS and run deploy-remote.sh.
# Also opens prod firewall for Prometheus scrape (idempotent).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

OBS_HOST="${OBS_SSH_HOST:-62.238.12.182}"
OBS_USER="${OBS_SSH_USER:-root}"
OBS_KEY="${OBS_SSH_KEY:-$HOME/.ssh/hetzner_arquivo_violencia_rsa}"

PROD_HOST="${PROD_SSH_HOST:-hetzner-arv}"
PROD_USER="${PROD_SSH_USER:-root}"
PROD_KEY="${PROD_SSH_KEY:-$HOME/.ssh/hetzner_arquivo_violencia_rsa}"

OBS_IP="${OBS_VPS_IP:-62.238.12.182}"
DOMAIN="${OBS_DOMAIN:-observability.carabetta.xyz}"
OBS_DIR="/opt/arquivo-observability"

obs_ssh=(ssh -o BatchMode=yes -o ConnectTimeout=20 -i "$OBS_KEY" "${OBS_USER}@${OBS_HOST}")
obs_rsync=(rsync -az --delete -e "ssh -i $OBS_KEY -o BatchMode=yes" \
  --exclude '.env' \
  --exclude 'prometheus_data' \
  --exclude 'grafana_data')

prod_ssh=(ssh -o BatchMode=yes -o ConnectTimeout=20 -i "$PROD_KEY" "${PROD_USER}@${PROD_HOST}")

echo "=== Observability deploy (laptop) ==="

# Ensure repo exists on obs VPS for deploy-remote.sh (CI uses git pull instead)
"${obs_ssh[@]}" "mkdir -p /root/arquivo-da-violencia/infra/observability"
"${obs_rsync[@]}" "$REPO_DIR/infra/observability/" "${OBS_USER}@${OBS_HOST}:/root/arquivo-da-violencia/infra/observability/"

# Pass password from local .env if set
grafana_pw="${GRAFANA_ADMIN_PASSWORD:-}"
if [[ -z "$grafana_pw" && -f "$REPO_DIR/.env" ]]; then
  grafana_pw="$(grep -E '^GRAFANA_ADMIN_PASSWORD=' "$REPO_DIR/.env" 2>/dev/null | cut -d= -f2- || true)"
fi

remote_env="REPO_DIR=/root/arquivo-da-violencia OBS_DIR=$OBS_DIR OBS_DOMAIN=$DOMAIN OBS_VPS_IP=$OBS_IP PROD_HOST=$PROD_HOST"
if [[ -n "$grafana_pw" ]]; then
  remote_env="$remote_env GRAFANA_ADMIN_PASSWORD=$(printf '%q' "$grafana_pw")"
fi

"${obs_ssh[@]}" "$remote_env bash /root/arquivo-da-violencia/infra/observability/deploy-remote.sh"

echo "=== Prod firewall: allow obs VPS scrape ==="
"${prod_ssh[@]}" bash -s "$OBS_IP" <<'REMOTE'
set -euo pipefail
OBS_IP="$1"
ufw allow from "$OBS_IP" to any port 8000 proto tcp comment 'Prometheus scrape API' >/dev/null 2>&1 || true
ufw allow from "$OBS_IP" to any port 9091 proto tcp comment 'Prometheus scrape worker' >/dev/null 2>&1 || true
ufw allow from "$OBS_IP" to any port 9100 proto tcp comment 'Prometheus scrape node_exporter' >/dev/null 2>&1 || true
echo "UFW rules for $OBS_IP → :8000/:9091/:9100 applied"
REMOTE

echo "=== Done: https://${DOMAIN}/d/arquivo-pipeline and /d/arquivo-hosts ==="
