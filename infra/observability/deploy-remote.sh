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

# --- Preserve Grafana credentials before any file sync ---
existing_password=""
if [[ -f "$OBS_DIR/.env" ]]; then
  # shellcheck disable=SC1090
  existing_password="$(grep -E '^GRAFANA_ADMIN_PASSWORD=' "$OBS_DIR/.env" 2>/dev/null | cut -d= -f2- || true)"
fi
if [[ -z "$existing_password" && -n "${GRAFANA_ADMIN_PASSWORD:-}" ]]; then
  existing_password="$GRAFANA_ADMIN_PASSWORD"
fi
if [[ -z "$existing_password" ]]; then
  die "GRAFANA_ADMIN_PASSWORD must be set (env or $OBS_DIR/.env) — never auto-generate on redeploy"
fi

log "Syncing stack from $REPO_DIR/infra/observability/ → $OBS_DIR/"
mkdir -p "$OBS_DIR"
rsync -a --delete \
  --exclude '.env' \
  --exclude 'prometheus_data' \
  --exclude 'grafana_data' \
  "$REPO_DIR/infra/observability/" "$OBS_DIR/"

# Write .env without clobbering password if file already exists with same value
cat >"$OBS_DIR/.env" <<EOF
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=${existing_password}
GRAFANA_DOMAIN=${DOMAIN}
GRAFANA_ROOT_URL=https://${DOMAIN}
EOF
chmod 600 "$OBS_DIR/.env"

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
docker compose up -d

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

log "Deploy complete — https://${DOMAIN}/d/arquivo-pipeline"
