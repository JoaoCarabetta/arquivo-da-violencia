#!/usr/bin/env bash
# Open the WAHA dashboard on https://wa.carabetta.xyz/dashboard.
# Does not restart Arquivo compose or the gbrain unit. Does not print secrets.
set -euo pipefail

WAHA_DIR=/opt/waha
WAHA_ENV=/etc/waha/env
WAHA_PORT=3140
HOST_NAME=wa.carabetta.xyz

log() { printf '[waha-dash] %s\n' "$*"; }
die() { printf '[waha-dash] ERROR: %s\n' "$*" >&2; exit 1; }

[[ ${EUID} -eq 0 ]] || die "run as root"
[[ -d $WAHA_DIR ]] || die "missing $WAHA_DIR — bootstrap WAHA first"
[[ -f $WAHA_ENV ]] || die "missing $WAHA_ENV"

write_nginx() {
  local available=/etc/nginx/sites-available/wa.carabetta.xyz
  local enabled=/etc/nginx/sites-enabled/wa.carabetta.xyz
  local cert=/etc/letsencrypt/live/${HOST_NAME}/fullchain.pem
  local key=/etc/letsencrypt/live/${HOST_NAME}/privkey.pem
  [[ -f $cert && -f $key ]] || die "missing cert $cert"
  cat >"$available" <<EOF
# WAHA front door. Dashboard is on https://${HOST_NAME}/dashboard (WAHA login).
# /mcp stays API-key only. Do not restart Arquivo compose to reload this.
map \$http_upgrade \$waha_connection_upgrade {
    default upgrade;
    ''      close;
}
limit_req_zone \$binary_remote_addr zone=waha_mcp:10m rate=10r/s;

server {
    listen 80;
    listen [::]:80;
    server_name ${HOST_NAME};

    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    location / {
        return 301 https://\$host\$request_uri;
    }
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name ${HOST_NAME};

    ssl_certificate ${cert};
    ssl_certificate_key ${key};
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;

    client_max_body_size 32m;

    location = /health {
        proxy_pass http://127.0.0.1:${WAHA_PORT}/health;
        proxy_set_header Host \$host;
    }

    location /mcp {
        limit_req zone=waha_mcp burst=20 nodelay;
        proxy_pass http://127.0.0.1:${WAHA_PORT}/mcp;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Connection '';
        proxy_buffering off;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }

    location / {
        proxy_pass_header Authorization;
        proxy_pass http://127.0.0.1:${WAHA_PORT};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection \$waha_connection_upgrade;
        proxy_buffering off;
        proxy_read_timeout 36000s;
        proxy_send_timeout 36000s;
        proxy_redirect off;
    }
}
EOF
  ln -sfn "$available" "$enabled"
  for extra in /etc/nginx/sites-enabled/wa /etc/nginx/sites-enabled/wa.carabetta \
               /etc/nginx/sites-enabled/whatsapp-mcp; do
    if [[ -e $extra && $(readlink -f "$extra") != $(readlink -f "$enabled") ]]; then
      rm -f "$extra"
      log "disabled extra site $(basename "$extra")"
    fi
  done
  nginx -t
  systemctl reload nginx
  log "nginx reloaded — dashboard https://${HOST_NAME}/dashboard"
}

ensure_waha() {
  docker compose -f "$WAHA_DIR/docker-compose.yml" up -d
  local i
  for i in $(seq 1 20); do
    if curl -sf -o /dev/null -H "X-Api-Key: $(awk -F= '/^WAHA_API_KEY=/ && $1=="WAHA_API_KEY" {print $2; exit}' "$WAHA_ENV")" \
        "http://127.0.0.1:${WAHA_PORT}/api/sessions"; then
      log "WAHA is up"
      return 0
    fi
    sleep 2
  done
  docker logs waha --tail 40 >&2 || true
  die "WAHA did not become healthy"
}

verify() {
  local loop_code public_code mcp_code
  loop_code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${WAHA_PORT}/dashboard" || true)
  public_code=$(curl -s -o /dev/null -w '%{http_code}' "https://${HOST_NAME}/dashboard" || true)
  mcp_code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "https://${HOST_NAME}/mcp" \
    -H "Content-Type: application/json" -d '{}' || true)
  log "loopback /dashboard HTTP ${loop_code} (expect 200/301/302)"
  log "public /dashboard HTTP ${public_code} (expect 200/301/302)"
  log "public /mcp without key HTTP ${mcp_code} (expect 401)"
  curl -sf http://127.0.0.1:8000/health >/dev/null && log "prod-api=ok" || log "prod-api=FAIL"
  curl -sf http://127.0.0.1:8001/health >/dev/null && log "staging-api=ok" || log "staging-api=FAIL"
  curl -sf http://127.0.0.1:3131/health >/dev/null && log "gbrain=ok" || log "gbrain=FAIL"
  [[ $public_code =~ ^(200|301|302)$ ]] || die "public dashboard not reachable (HTTP ${public_code})"
}

log "DASHBOARD_URL=https://${HOST_NAME}/dashboard"
log "DASHBOARD_USER is WAHA_DASHBOARD_USERNAME in /etc/waha/env (password stays on the box)"
ensure_waha
write_nginx
verify
log "done. Open https://${HOST_NAME}/dashboard"
