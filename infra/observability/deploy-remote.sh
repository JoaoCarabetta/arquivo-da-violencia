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

# MCP (mcp-grafana) tokens. The server token gates agent callers and must never
# be empty (an empty MCP_GRAFANA_SERVER_TOKEN would run the MCP unauthenticated).
existing_mcp_server_token="$(read_existing_env MCP_GRAFANA_SERVER_TOKEN)"
existing_mcp_server_token="${MCP_GRAFANA_SERVER_TOKEN:-$existing_mcp_server_token}"
if [[ -z "$existing_mcp_server_token" ]]; then
  existing_mcp_server_token="$(openssl rand -hex 32)"
  log "Generated new MCP_GRAFANA_SERVER_TOKEN"
fi
# Grafana Viewer service-account token for mcp-grafana → Grafana. Empty on first
# run; bootstrapped against the live Grafana below, then persisted.
existing_mcp_sa_token="$(read_existing_env GRAFANA_SERVICE_ACCOUNT_TOKEN)"
existing_mcp_sa_token="${GRAFANA_SERVICE_ACCOUNT_TOKEN:-$existing_mcp_sa_token}"

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
  echo "MCP_GRAFANA_SERVER_TOKEN=${existing_mcp_server_token}"
  echo "GRAFANA_SERVICE_ACCOUNT_TOKEN=${existing_mcp_sa_token}"
} >"$OBS_DIR/.env"
chmod 600 "$OBS_DIR/.env"

if [[ -z "$existing_telegram_token" || -z "$existing_telegram_chat" ]]; then
  log "WARN: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set — alert-router Telegram disabled"
fi
if [[ -z "$existing_webhook_url" || -z "$existing_webhook_auth" ]]; then
  log "WARN: PIPELINE_HEALTH_WEBHOOK_URL / auth not set — Cursor agent dispatch disabled"
fi

# --- DNS precheck (retries + DoH fallback: local resolvers can hold a stale
# negative answer for up to the zone's negative TTL after the record is created) ---
dns_ok=false
for attempt in $(seq 1 10); do
  if command -v resolvectl >/dev/null 2>&1; then
    resolvectl flush-caches >/dev/null 2>&1 || true
  fi
  resolved_ip="$(getent ahosts "$DOMAIN" 2>/dev/null | awk '/STREAM/ {print $1; exit}' || true)"
  if [[ -z "$resolved_ip" ]]; then
    resolved_ip="$(dig +short "$DOMAIN" 2>/dev/null | head -1 || true)"
  fi
  if [[ "$resolved_ip" == "$OBS_IP" ]]; then
    dns_ok=true
    break
  fi
  if curl -s --max-time 10 -H 'accept: application/dns-json' \
    "https://1.1.1.1/dns-query?name=${DOMAIN}&type=A" | grep -q "\"data\":\"${OBS_IP}\""; then
    log "DNS OK via DoH (attempt ${attempt}; local resolver still catching up)"
    dns_ok=true
    break
  fi
  log "DNS attempt ${attempt}: '$DOMAIN' → '${resolved_ip:-<none>}' (want $OBS_IP), retrying"
  sleep 6
done
$dns_ok || die "DNS for $DOMAIN does not resolve to $OBS_IP (create a DNS-only A record in the Cloudflare carabetta.xyz zone)"
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

# --- MCP: bootstrap Grafana service account (first run only) ---
# mcp-grafana needs a Viewer service-account token. It can only be minted once
# Grafana is up, so on the first deploy we create it here, persist it to .env,
# and recreate the mcp-grafana container with the new env. Never log token values.
if [[ -z "$existing_mcp_sa_token" ]]; then
  log "Bootstrapping Grafana service account for MCP (mcp-agents, role Viewer)"
  grafana_ready=false
  for _ in $(seq 1 30); do
    if curl -sf http://127.0.0.1:3000/api/health >/dev/null 2>&1; then
      grafana_ready=true
      break
    fi
    sleep 2
  done
  $grafana_ready || die "Grafana did not become healthy — cannot bootstrap MCP service account"

  admin_auth="admin:${existing_password}"
  sa_search="$(curl -sf -u "$admin_auth" \
    'http://127.0.0.1:3000/api/serviceaccounts/search?query=mcp-agents' || true)"
  sa_id="$(printf '%s' "$sa_search" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
    for sa in data.get("serviceAccounts", []):
        if sa.get("name") == "mcp-agents":
            print(sa["id"]); break
except Exception:
    pass' || true)"

  if [[ -z "$sa_id" ]]; then
    sa_id="$(curl -sf -u "$admin_auth" -X POST http://127.0.0.1:3000/api/serviceaccounts \
      -H 'Content-Type: application/json' \
      -d '{"name":"mcp-agents","role":"Viewer","isDisabled":false}' \
      | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')" \
      || die "Failed to create mcp-agents service account"
    log "Created service account mcp-agents (id ${sa_id})"
  else
    log "Service account mcp-agents already exists (id ${sa_id})"
  fi

  existing_mcp_sa_token="$(curl -sf -u "$admin_auth" -X POST \
    "http://127.0.0.1:3000/api/serviceaccounts/${sa_id}/tokens" \
    -H 'Content-Type: application/json' \
    -d "{\"name\":\"mcp-agents-$(date +%s)\"}" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["key"])')" \
    || die "Failed to create service account token"
  [[ -n "$existing_mcp_sa_token" ]] || die "Service account token came back empty"

  sed -i "s|^GRAFANA_SERVICE_ACCOUNT_TOKEN=.*|GRAFANA_SERVICE_ACCOUNT_TOKEN=${existing_mcp_sa_token}|" "$OBS_DIR/.env"
  chmod 600 "$OBS_DIR/.env"
  export GRAFANA_SERVICE_ACCOUNT_TOKEN="$existing_mcp_sa_token"
  docker compose up -d --force-recreate mcp-grafana
  log "MCP service account token persisted; mcp-grafana recreated"
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

# --- MCP smoke checks (fail the deploy if auth or the tool chain is broken) ---
# Local endpoint with the public Host header (works before TLS exists and
# exercises the --allowed-hosts validation).
mcp_local="http://127.0.0.1:8000/mcp"
mcp_headers=(-H "Host: ${DOMAIN}" -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream')
sleep 2

unauth_code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 -X POST "$mcp_local" \
  "${mcp_headers[@]}" -d '{"jsonrpc":"2.0","id":0,"method":"ping"}' || true)"
if [[ "$unauth_code" == "401" ]]; then
  log "MCP unauthenticated request correctly rejected (401)"
else
  die "MCP unauthenticated request returned '${unauth_code}' — expected 401 (check MCP_GRAFANA_SERVER_TOKEN)"
fi

mcp_auth=(-H "Authorization: Bearer ${existing_mcp_server_token}")
init_headers_file="$(mktemp)"
init_resp="$(curl -s --max-time 20 -D "$init_headers_file" -X POST "$mcp_local" \
  "${mcp_headers[@]}" "${mcp_auth[@]}" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"deploy-smoke","version":"1.0"}}}' || true)"
if echo "$init_resp" | grep -q 'serverInfo'; then
  log "MCP initialize OK"
else
  rm -f "$init_headers_file"
  die "MCP initialize failed (allowed-hosts or token misconfig?)"
fi
mcp_session="$(awk 'tolower($1)=="mcp-session-id:"{print $2}' "$init_headers_file" | tr -d '\r')"
rm -f "$init_headers_file"
session_header=()
[[ -n "$mcp_session" ]] && session_header=(-H "Mcp-Session-Id: ${mcp_session}")

curl -s --max-time 20 -o /dev/null -X POST "$mcp_local" \
  "${mcp_headers[@]}" "${mcp_auth[@]}" "${session_header[@]}" \
  -d '{"jsonrpc":"2.0","method":"notifications/initialized"}' || true

tools_resp="$(curl -s --max-time 20 -X POST "$mcp_local" \
  "${mcp_headers[@]}" "${mcp_auth[@]}" "${session_header[@]}" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' || true)"
if echo "$tools_resp" | grep -q 'query_prometheus'; then
  log "MCP tools/list OK (query_prometheus available)"
else
  die "MCP tools/list missing query_prometheus"
fi

ds_resp="$(curl -s --max-time 30 -X POST "$mcp_local" \
  "${mcp_headers[@]}" "${mcp_auth[@]}" "${session_header[@]}" \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"list_datasources","arguments":{}}}' || true)"
if echo "$ds_resp" | grep -qi 'prometheus'; then
  log "MCP → Grafana chain OK (list_datasources sees Prometheus)"
else
  die "MCP list_datasources failed — Grafana service account token may be invalid"
fi

# Pin the domain to loopback: this tests the exact public vhost (TLS + nginx +
# mcp) without depending on the box's resolver, which can hold a stale negative
# answer right after the DNS record is (re)created.
resolve_pin=(--resolve "${DOMAIN}:443:127.0.0.1")
if [[ -f "$cert_path" ]]; then
  public_unauth="$(curl -s "${resolve_pin[@]}" -o /dev/null -w '%{http_code}' --max-time 20 -X POST "https://${DOMAIN}/mcp" \
    -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
    -d '{"jsonrpc":"2.0","id":0,"method":"ping"}' || true)"
  if [[ "$public_unauth" == "401" ]]; then
    log "MCP public endpoint live at https://${DOMAIN}/mcp (auth enforced)"
  else
    die "MCP public endpoint returned '${public_unauth}' — expected 401 (check nginx /mcp location)"
  fi

  public_init="$(curl -s "${resolve_pin[@]}" --max-time 20 -X POST "https://${DOMAIN}/mcp" \
    -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
    "${mcp_auth[@]}" \
    -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"deploy-smoke-public","version":"1.0"}}}' || true)"
  if echo "$public_init" | grep -q 'serverInfo'; then
    log "MCP public authed initialize OK (full nginx → mcp chain)"
  else
    die "MCP public authed initialize failed (nginx proxy headers?)"
  fi
fi

log "Deploy complete — https://${DOMAIN}/d/arquivo-pipeline | MCP: https://${DOMAIN}/mcp"
