#!/usr/bin/env bash
# Laptop wrapper: sync Umami stack to obs VPS and run deploy-remote.sh.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

OBS_HOST="${OBS_SSH_HOST:-62.238.12.182}"
OBS_USER="${OBS_SSH_USER:-root}"
OBS_KEY="${OBS_SSH_KEY:-$HOME/.ssh/hetzner_arquivo_violencia_rsa}"

OBS_IP="${OBS_VPS_IP:-62.238.12.182}"
DOMAIN="${UMAMI_DOMAIN:-analytics.carabetta.xyz}"
UMAMI_DIR="/opt/arquivo-umami"

obs_ssh=(ssh -o BatchMode=yes -o ConnectTimeout=20 -i "$OBS_KEY" "${OBS_USER}@${OBS_HOST}")
obs_rsync=(rsync -az --delete -e "ssh -i $OBS_KEY -o BatchMode=yes" \
  --exclude '.env' \
  --exclude 'umami_db_data')

echo "=== Umami analytics deploy (laptop) ==="

"${obs_ssh[@]}" "mkdir -p /root/arquivo-da-violencia/infra/umami"
"${obs_rsync[@]}" "$REPO_DIR/infra/umami/" "${OBS_USER}@${OBS_HOST}:/root/arquivo-da-violencia/infra/umami/"

# Pass secrets from local env or repo .env if set (first bootstrap / override)
db_pw="${UMAMI_DB_PASSWORD:-}"
app_secret="${UMAMI_APP_SECRET:-}"
if [[ -z "$db_pw" && -f "$REPO_DIR/.env" ]]; then
  db_pw="$(grep -E '^UMAMI_DB_PASSWORD=' "$REPO_DIR/.env" 2>/dev/null | cut -d= -f2- || true)"
fi
if [[ -z "$app_secret" && -f "$REPO_DIR/.env" ]]; then
  app_secret="$(grep -E '^UMAMI_APP_SECRET=' "$REPO_DIR/.env" 2>/dev/null | cut -d= -f2- || true)"
fi

remote_env="REPO_DIR=/root/arquivo-da-violencia UMAMI_DIR=$UMAMI_DIR UMAMI_DOMAIN=$DOMAIN OBS_VPS_IP=$OBS_IP"
if [[ -n "$db_pw" ]]; then
  remote_env="$remote_env UMAMI_DB_PASSWORD=$(printf '%q' "$db_pw")"
fi
if [[ -n "$app_secret" ]]; then
  remote_env="$remote_env UMAMI_APP_SECRET=$(printf '%q' "$app_secret")"
fi

"${obs_ssh[@]}" "$remote_env bash /root/arquivo-da-violencia/infra/umami/deploy-remote.sh"

echo "=== Done: https://${DOMAIN} ==="
