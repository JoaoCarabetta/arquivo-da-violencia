#!/usr/bin/env bash
# Runs on the observability VPS. Syncs Umami stack, preserves secrets,
# configures nginx/TLS for analytics.carabetta.xyz.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${REPO_DIR:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
UMAMI_DIR="${UMAMI_DIR:-/opt/arquivo-umami}"
DOMAIN="${UMAMI_DOMAIN:-analytics.carabetta.xyz}"
OBS_IP="${OBS_VPS_IP:-62.238.12.182}"

log() { echo "[umami-deploy-remote] $*"; }
die() { echo "[umami-deploy-remote] ERROR: $*" >&2; exit 1; }

read_existing_env() {
  local key="$1"
  if [[ -f "$UMAMI_DIR/.env" ]]; then
    grep -E "^${key}=" "$UMAMI_DIR/.env" 2>/dev/null | cut -d= -f2- || true
  fi
}

existing_db_password="$(read_existing_env UMAMI_DB_PASSWORD)"
existing_app_secret="$(read_existing_env UMAMI_APP_SECRET)"

existing_db_password="${UMAMI_DB_PASSWORD:-$existing_db_password}"
existing_app_secret="${UMAMI_APP_SECRET:-$existing_app_secret}"

if [[ -z "$existing_db_password" ]]; then
  existing_db_password="$(openssl rand -hex 24)"
  log "Generated new UMAMI_DB_PASSWORD"
fi
if [[ -z "$existing_app_secret" ]]; then
  existing_app_secret="$(openssl rand -hex 32)"
  log "Generated new UMAMI_APP_SECRET"
fi

log "Syncing stack from $REPO_DIR/infra/umami/ → $UMAMI_DIR/"
mkdir -p "$UMAMI_DIR"
rsync -a --delete \
  --exclude '.env' \
  --exclude 'umami_db_data' \
  "$REPO_DIR/infra/umami/" "$UMAMI_DIR/"

{
  echo "UMAMI_DB_PASSWORD=${existing_db_password}"
  echo "UMAMI_APP_SECRET=${existing_app_secret}"
} >"$UMAMI_DIR/.env"
chmod 600 "$UMAMI_DIR/.env"

# --- DNS precheck ---
resolved_ip="$(getent ahosts "$DOMAIN" 2>/dev/null | awk '/STREAM/ {print $1; exit}' || true)"
if [[ -z "$resolved_ip" ]]; then
  resolved_ip="$(dig +short "$DOMAIN" 2>/dev/null | head -1 || true)"
fi
if [[ "$resolved_ip" != "$OBS_IP" ]]; then
  die "DNS for $DOMAIN resolves to '${resolved_ip:-<none>}' — expected $OBS_IP. Add an A record first."
fi
log "DNS OK: $DOMAIN → $OBS_IP"

# --- Docker stack ---
cd "$UMAMI_DIR"
set -a
# shellcheck disable=SC1091
source .env
set +a
docker compose pull
docker compose up -d
sleep 5

# --- Nginx + TLS ---
nginx_site="/etc/nginx/sites-available/analytics"
cert_path="/etc/letsencrypt/live/${DOMAIN}/fullchain.pem"

if [[ -f "$cert_path" ]]; then
  log "TLS cert exists — installing HTTPS nginx config"
  cp "$UMAMI_DIR/nginx/analytics.conf" "$nginx_site"
else
  log "No TLS cert yet — HTTP-only nginx + certbot"
  cp "$UMAMI_DIR/nginx/analytics-http-only.conf" "$nginx_site"
fi
ln -sf "$nginx_site" /etc/nginx/sites-enabled/analytics
nginx -t
systemctl reload nginx

if [[ ! -f "$cert_path" ]]; then
  if command -v certbot >/dev/null 2>&1; then
    certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m admin@carabetta.xyz || true
    if [[ -f "$cert_path" ]]; then
      cp "$UMAMI_DIR/nginx/analytics.conf" "$nginx_site"
      nginx -t && systemctl reload nginx
    fi
  else
    log "certbot not installed — skipping TLS bootstrap"
  fi
fi

# --- UFW (public 80/443; Umami localhost-bound) ---
if command -v ufw >/dev/null 2>&1; then
  ufw allow 80/tcp comment 'analytics HTTP' >/dev/null 2>&1 || true
  ufw allow 443/tcp comment 'analytics HTTPS' >/dev/null 2>&1 || true
  ufw deny 3001/tcp comment 'Umami not public' >/dev/null 2>&1 || true
fi

# --- Smoke checks ---
sleep 3
if curl -sf "https://${DOMAIN}/api/heartbeat" >/dev/null 2>&1; then
  log "Umami HTTPS heartbeat OK"
elif curl -sf "http://127.0.0.1:3001/api/heartbeat" >/dev/null 2>&1; then
  log "Umami local heartbeat OK (HTTPS may need cert)"
else
  die "Umami not reachable"
fi

log "Deploy complete — https://${DOMAIN}"
log "Next: log in, add prod + staging websites, set GitHub secrets UMAMI_WEBSITE_ID_PROD / UMAMI_WEBSITE_ID_STAGING"
