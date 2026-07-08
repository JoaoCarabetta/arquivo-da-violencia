#!/usr/bin/env bash
# Runs on the observability VPS (or via CI SSH). Syncs stack from repo checkout,
# preserves Grafana password, configures nginx/TLS, and smoke-checks Prometheus.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${REPO_DIR:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
OBS_DIR="${OBS_DIR:-/opt/arquivo-observability}"
DOMAIN="${OBS_DOMAIN:-observability.carabetta.xyz}"
OBS_IP="${OBS_VPS_IP:-62.238.12.182}"
PROD_HOST="${PROD_HOST:-77.42.72.111}"

log() { echo "[deploy-remote] $*"; }
die() { echo "[deploy-remote] ERROR: $*" >&2; exit 1; }

# --- Preserve credentials before any file sync ---
read_existing_env() {
  local key="$1"
  if [[ -f "$OBS_DIR/.env" ]]; then
    grep -E "^${key}=" "$OBS_DIR/.env" 2>/dev/null | cut -d= -f2- || true
  fi
}

existing_password=""
existing_password="$(read_existing_env GRAFANA_ADMIN_PASSWORD)"
if [[ -z "$existing_password" && -n "${GRAFANA_ADMIN_PASSWORD:-}" ]]; then
  existing_password="$GRAFANA_ADMIN_PASSWORD"
fi
if [[ -z "$existing_password" ]]; then
  die "GRAFANA_ADMIN_PASSWORD must be set (env or $OBS_DIR/.env) — never auto-generate on redeploy"
fi

existing_telegram_token="$(read_existing_env TELEGRAM_BOT_TOKEN)"
existing_telegram_chat="$(read_existing_env TELEGRAM_CHAT_ID)"
existing_webhook_url="$(read_existing_env PIPELINE_HEALTH_WEBHOOK_URL)"
existing_webhook_auth="$(read_existing_env PIPELINE_HEALTH_WEBHOOK_AUTH)"
if [[ -z "$existing_webhook_auth" ]]; then
  existing_webhook_auth="$(read_existing_env CURSOR_AUTOMATION_TOKEN)"
fi

# Allow env overrides for first-time bootstrap
existing_telegram_token="${TELEGRAM_BOT_TOKEN:-$existing_telegram_token}"
existing_telegram_chat="${TELEGRAM_CHAT_ID:-$existing_telegram_chat}"
existing_webhook_url="${PIPELINE_HEALTH_WEBHOOK_URL:-$existing_webhook_url}"
existing_webhook_auth="${PIPELINE_HEALTH_WEBHOOK_AUTH:-${CURSOR_AUTOMATION_TOKEN:-$existing_webhook_auth}}"

existing_router_secret="$(read_existing_env ALERT_ROUTER_WEBHOOK_SECRET)"
if [[ -z "$existing_router_secret" && -f "$OBS_DIR/alertmanager/secrets/webhook_bearer" ]]; then
  existing_router_secret="$(cat "$OBS_DIR/alertmanager/secrets/webhook_bearer")"
fi
existing_router_secret="${ALERT_ROUTER_WEBHOOK_SECRET:-$existing_router_secret}"
if [[ -z "$existing_router_secret" ]]; then
  existing_router_secret="$(openssl rand -hex 32)"
  log "Generated new ALERT_ROUTER_WEBHOOK_SECRET"
fi

log "Syncing stack from $REPO_DIR/infra/observability/ → $OBS_DIR/"
mkdir -p "$OBS_DIR"
rsync -a --delete \
  --exclude '.env' \
  --exclude 'prometheus_data' \
  --exclude 'grafana_data' \
  --exclude 'alertmanager/secrets/webhook_bearer' \
  "$REPO_DIR/infra/observability/" "$OBS_DIR/"

mkdir -p "$OBS_DIR/alertmanager/secrets"
printf '%s' "$existing_router_secret" >"$OBS_DIR/alertmanager/secrets/webhook_bearer"
chmod 600 "$OBS_DIR/alertmanager/secrets/webhook_bearer"

# Write .env preserving alert-router secrets across redeploys
{
  echo "GRAFANA_ADMIN_USER=admin"
  echo "GRAFANA_ADMIN_PASSWORD=${existing_password}"
  echo "GRAFANA_DOMAIN=${DOMAIN}"
  echo "GRAFANA_ROOT_URL=https://${DOMAIN}"
  [[ -n "$existing_telegram_token" ]] && echo "TELEGRAM_BOT_TOKEN=${existing_telegram_token}"
  [[ -n "$existing_telegram_chat" ]] && echo "TELEGRAM_CHAT_ID=${existing_telegram_chat}"
  [[ -n "$existing_webhook_url" ]] && echo "PIPELINE_HEALTH_WEBHOOK_URL=${existing_webhook_url}"
  [[ -n "$existing_webhook_auth" ]] && echo "PIPELINE_HEALTH_WEBHOOK_AUTH=${existing_webhook_auth}"
  echo "ALERT_ROUTER_WEBHOOK_SECRET=${existing_router_secret}"
} >"$OBS_DIR/.env"
chmod 600 "$OBS_DIR/.env"

if [[ -z "$existing_telegram_token" || -z "$existing_telegram_chat" ]]; then
  log "WARN: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set — alert-router Telegram disabled"
fi
if [[ -z "$existing_webhook_url" || -z "$existing_webhook_auth" ]]; then
  log "WARN: PIPELINE_HEALTH_WEBHOOK_URL / auth not set — Cursor agent dispatch disabled"
fi

# --- DNS precheck ---
resolved_ip="$(getent ahosts "$DOMAIN" 2>/dev/null | awk '/STREAM/ {print $1; exit}' || true)"
if [[ -z "$resolved_ip" ]]; then
  resolved_ip="$(dig +short "$DOMAIN" 2>/dev/null | head -1 || true)"
fi
if [[ "$resolved_ip" != "$OBS_IP" ]]; then
  die "DNS for $DOMAIN resolves to '${resolved_ip:-<none>}' — expected $OBS_IP"
fi
log "DNS OK: $DOMAIN → $OBS_IP"

# --- Docker stack ---
cd "$OBS_DIR"
set -a
# shellcheck disable=SC1091
source .env
set +a
docker compose pull
docker compose up -d --build
# Bind-mounted prometheus.yml is not picked up until reload/restart.
docker compose restart prometheus alertmanager
sleep 3
if docker exec obs-prometheus wget -qO- --post-data="" http://localhost:9090/-/reload >/dev/null 2>&1; then
  log "Prometheus config reloaded"
else
  log "Prometheus reload skipped (container may still be starting)"
fi

# --- Nginx + TLS ---
nginx_site="/etc/nginx/sites-available/observability"
cert_path="/etc/letsencrypt/live/${DOMAIN}/fullchain.pem"

if [[ -f "$cert_path" ]]; then
  log "TLS cert exists — installing HTTPS nginx config"
  cp "$OBS_DIR/nginx/observability.conf" "$nginx_site"
else
  log "No TLS cert yet — HTTP-only nginx + certbot"
  cp "$OBS_DIR/nginx/observability-http-only.conf" "$nginx_site"
fi
ln -sf "$nginx_site" /etc/nginx/sites-enabled/observability
nginx -t
systemctl reload nginx

if [[ ! -f "$cert_path" ]]; then
  if command -v certbot >/dev/null 2>&1; then
    certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m admin@carabetta.xyz || true
    if [[ -f "$cert_path" ]]; then
      cp "$OBS_DIR/nginx/observability.conf" "$nginx_site"
      nginx -t && systemctl reload nginx
    fi
  else
    log "certbot not installed — skipping TLS bootstrap"
  fi
fi

# --- UFW on obs VPS (public 80/443 only; Grafana localhost-bound) ---
if command -v ufw >/dev/null 2>&1; then
  ufw allow 80/tcp comment 'observability HTTP' >/dev/null 2>&1 || true
  ufw allow 443/tcp comment 'observability HTTPS' >/dev/null 2>&1 || true
  ufw deny 3000/tcp comment 'Grafana not public' >/dev/null 2>&1 || true
fi

# --- Smoke checks ---
sleep 3
if curl -sf "https://${DOMAIN}/api/health" >/dev/null 2>&1; then
  log "Grafana HTTPS health OK"
elif curl -sf "http://127.0.0.1:3000/api/health" >/dev/null 2>&1; then
  log "Grafana local health OK (HTTPS may need cert)"
else
  die "Grafana not reachable"
fi

prom_up="$(docker exec obs-prometheus wget -qO- 'http://localhost:9090/api/v1/query?query=up%7Bjob%3D~%22arquivo-prod.*%22%7D' 2>/dev/null || true)"
if echo "$prom_up" | grep -q '"status":"success"'; then
  log "Prometheus scrape targets query OK"
else
  log "WARN: Prometheus scrape check inconclusive (prod metrics may not be deployed yet)"
fi

rules_loaded="$(docker exec obs-prometheus wget -qO- 'http://localhost:9090/api/v1/rules' 2>/dev/null || true)"
if echo "$rules_loaded" | grep -q 'WorkerDown'; then
  log "Prometheus alert rules loaded"
else
  log "WARN: Prometheus alert rules not found (check rules mount)"
fi

if docker exec obs-alert-router python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health')" >/dev/null 2>&1; then
  log "Alert-router health OK"
else
  log "WARN: Alert-router health check failed"
fi

am_ready="$(docker exec obs-alertmanager wget -qO- http://localhost:9093/-/ready 2>/dev/null || true)"
if echo "$am_ready" | grep -q 'OK'; then
  log "Alertmanager ready"
else
  log "WARN: Alertmanager not ready yet"
fi

log "Deploy complete — https://${DOMAIN}/d/arquivo-pipeline"
