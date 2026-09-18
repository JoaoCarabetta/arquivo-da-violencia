#!/usr/bin/env bash
# Install or refresh the WAHA WhatsApp bridge beside Arquivo (not inside compose).
# Idempotent. Does not restart arquivo compose or the gbrain unit.
set -euo pipefail

WAHA_DIR=/opt/waha
WAHA_ENV=/etc/waha/env
WAHA_PORT=3140
WAHA_IMAGE=devlikeapro/waha:latest
HOST_NAME=wa.carabetta.xyz
CF_TOKEN_FILE=/root/.cloudflare_api_token
REPORT=/opt/waha/BOOTSTRAP.txt

log() { printf '[waha] %s\n' "$*"; }
die() { printf '[waha] ERROR: %s\n' "$*" >&2; exit 1; }

require_root() {
  [[ ${EUID} -eq 0 ]] || die "run as root"
}

redacted_nginx() {
  local f=$1
  [[ -f $f ]] || { echo "(missing $f)"; return 0; }
  sed -E 's/(ssl_certificate_key|auth_basic_user_file|Authorization).*/\1 [REDACTED]/' "$f"
}

inspect_host() {
  log "=== host inspect ==="
  hostname
  uname -a
  free -h
  df -h /
  echo "--- units ---"
  systemctl is-active nginx docker gbrain 2>/dev/null || true
  echo "--- docker ---"
  docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' || true
  echo "--- nginx sites ---"
  ls -la /etc/nginx/sites-available /etc/nginx/sites-enabled || true
  echo "--- wa / whatsapp-mcp vhost (redacted) ---"
  for f in /etc/nginx/sites-available/wa /etc/nginx/sites-available/wa.carabetta.xyz \
           /etc/nginx/sites-available/whatsapp-mcp \
           /etc/nginx/sites-enabled/wa /etc/nginx/sites-enabled/wa.carabetta.xyz \
           /etc/nginx/sites-enabled/whatsapp-mcp; do
    [[ -e $f ]] && { echo "FILE $f -> $(readlink -f "$f" 2>/dev/null || echo "$f")"; redacted_nginx "$f"; }
  done
  echo "--- certbot ---"
  certbot certificates 2>/dev/null | sed -n '/Certificate Name\|Domains\|Expiry Date\|Serial/p' || true
  echo "--- listeners ---"
  ss -lntp | grep -E ':(3000|3131|3140|8080|8000|8001)\b' || true
  echo "--- paths ---"
  [[ -d $WAHA_DIR ]] && echo "WAHA_DIR=yes" || echo "WAHA_DIR=no"
  [[ -f $WAHA_ENV ]] && echo "WAHA_ENV=yes" || echo "WAHA_ENV=no"
  [[ -f $CF_TOKEN_FILE ]] && echo "CF_TOKEN=yes" || echo "CF_TOKEN=no"
  echo "--- mem containers ---"
  docker stats --no-stream --format 'table {{.Name}}\t{{.MemUsage}}\t{{.CPUPerc}}' || true
}

available_mib() {
  awk '/MemAvailable:/ {print int($2/1024)}' /proc/meminfo
}

ensure_not_arquivo_compose() {
  [[ $WAHA_DIR != /root/arquivo-da-violencia* ]] || die "refusing to install under arquivo checkout"
}

ensure_env() {
  mkdir -p /etc/waha
  chmod 700 /etc/waha
  if [[ -f $WAHA_ENV ]]; then
    log "reusing existing $WAHA_ENV"
    return 0
  fi
  local api_key dash_pass swagger_pass
  api_key=$(openssl rand -hex 32)
  dash_pass=$(openssl rand -hex 24)
  swagger_pass=$(openssl rand -hex 24)
  umask 077
  cat >"$WAHA_ENV" <<EOF
WHATSAPP_DEFAULT_ENGINE=GOWS
WAHA_APPS_ENABLED=True
WAHA_APPS_OFF=chatwoot
WAHA_DASHBOARD_ENABLED=True
WAHA_DASHBOARD_USERNAME=admin
WAHA_DASHBOARD_PASSWORD=${dash_pass}
WHATSAPP_SWAGGER_ENABLED=False
WAHA_API_KEY=${api_key}
WAHA_API_KEY_PLAIN=${api_key}
WAHA_BASE_URL=http://127.0.0.1:${WAHA_PORT}
WAHA_PUBLIC_URL=https://${HOST_NAME}
WAHA_GOWS_DEVICE_REQUIRE_FULL_SYNC=false
WAHA_GOWS_DEVICE_HISTORY_SYNC_FULL_SYNC_DAYS_LIMIT=30
WAHA_GOWS_DEVICE_HISTORY_SYNC_INITIAL_SYNC_MAX_MESSAGES_PER_CHAT=80
TZ=America/Sao_Paulo
EOF
  chmod 600 "$WAHA_ENV"
  log "wrote $WAHA_ENV (0600)"
}

api_key() {
  awk -F= '/^WAHA_API_KEY=/ && $1=="WAHA_API_KEY" {print $2; exit}' "$WAHA_ENV"
}

write_compose() {
  mkdir -p "$WAHA_DIR/sessions" "$WAHA_DIR/media" "$WAHA_DIR/qr"
  chmod 700 "$WAHA_DIR" "$WAHA_DIR/sessions" "$WAHA_DIR/media" "$WAHA_DIR/qr"
  cat >"$WAHA_DIR/docker-compose.yml" <<EOF
services:
  waha:
    image: ${WAHA_IMAGE}
    restart: always
    container_name: waha
    ports:
      - "127.0.0.1:${WAHA_PORT}:3000"
    volumes:
      - ./sessions:/app/.sessions
      - ./media:/app/.media
    env_file:
      - ${WAHA_ENV}
    environment:
      REDIS_URL: redis://waha-redis:6379
    depends_on:
      - redis
    dns:
      - 1.1.1.1
      - 8.8.8.8
    logging:
      driver: json-file
      options:
        max-size: "50m"
        max-file: "5"
  redis:
    image: redis:7-alpine
    restart: always
    container_name: waha-redis
    command: ["redis-server", "--save", "60", "1", "--loglevel", "warning"]
    volumes:
      - redis_data:/data
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
volumes:
  redis_data: {}
EOF
}

start_waha() {
  if ss -lnt | grep -q ":${WAHA_PORT} " && ! docker ps --format '{{.Names}}' | grep -qx waha; then
    die "port ${WAHA_PORT} already in use by something other than waha"
  fi
  log "pulling ${WAHA_IMAGE}"
  docker compose -f "$WAHA_DIR/docker-compose.yml" pull
  docker compose -f "$WAHA_DIR/docker-compose.yml" up -d
  local i
  for i in $(seq 1 40); do
    if curl -sf -o /dev/null "http://127.0.0.1:${WAHA_PORT}/health" || \
       curl -sf -o /dev/null -H "X-Api-Key: $(api_key)" "http://127.0.0.1:${WAHA_PORT}/api/sessions"; then
      log "WAHA is up"
      return 0
    fi
    sleep 3
  done
  docker logs waha --tail 80 >&2 || true
  die "WAHA did not become healthy"
}

waha_curl() {
  local method=$1 path=$2
  shift 2
  curl -sS -X "$method" "http://127.0.0.1:${WAHA_PORT}${path}" \
    -H "X-Api-Key: $(api_key)" \
    -H "Accept: application/json" \
    "$@"
}

ensure_session() {
  local name=$1
  local existing
  existing=$(waha_curl GET /api/sessions)
  if echo "$existing" | python3 -c "import json,sys
d=json.load(sys.stdin)
items=d if isinstance(d,list) else d.get('data', d.get('sessions', []))
sys.exit(0 if '$name' in [x.get('name') for x in items] else 1)" 2>/dev/null; then
    log "session $name already exists"
    waha_curl POST "/api/sessions/${name}/start" -H "Content-Type: application/json" -d '{}' >/dev/null || true
    return 0
  fi
  log "creating session $name"
  waha_curl POST /api/sessions -H "Content-Type: application/json" \
    -d "{\"name\":\"${name}\",\"config\":{\"engine\":\"GOWS\"}}" >/dev/null
}

ensure_mcp_app() {
  local session=$1
  local apps body
  apps=$(waha_curl GET /api/apps || echo '[]')
  if echo "$apps" | python3 -c "import json,sys
try:
    data=json.load(sys.stdin)
except Exception:
    sys.exit(1)
items=data if isinstance(data,list) else data.get('apps',data.get('data',[]))
sys.exit(0 if any(i.get('session')=='$session' and i.get('app')=='mcp' for i in items) else 1)" 2>/dev/null; then
    log "MCP app for $session already exists"
    return 0
  fi
  body=$(cat <<EOF
{"enabled":true,"id":"app_mcp_${session}","session":"${session}","app":"mcp","config":{"actions":{"read":true,"send":true,"control":false,"setting":false,"app":false,"delete":false}}}
EOF
)
  waha_curl POST /api/apps -H "Content-Type: application/json" -d "$body" >/dev/null
  log "created MCP app for $session"
}

extract_key() {
  python3 -c "import json,sys
d=json.load(sys.stdin)
if isinstance(d, dict):
    print(d.get('key') or (d.get('config') or {}).get('key') or '')
    raise SystemExit
items=d if isinstance(d,list) else []
print(items[0].get('key','') if items else '')"
}

ensure_session_key() {
  local session=$1
  local keyfile="/etc/waha/mcp-${session}.key"
  if [[ -s $keyfile && $(cat "$keyfile") != EXISTING_APP_NO_KEY ]]; then
    log "reusing session key file for $session"
    return 0
  fi
  local resp key listed
  resp=$(waha_curl POST /api/keys -H "Content-Type: application/json" -d "{\"isAdmin\":false,\"session\":\"${session}\",\"isActive\":true,\"actions\":{\"read\":true,\"send\":true,\"control\":false,\"setting\":false,\"app\":false,\"delete\":false}}")
  key=$(printf '%s' "$resp" | extract_key)
  if [[ -z $key ]]; then
    listed=$(waha_curl GET /api/keys)
    key=$(printf '%s' "$listed" | python3 -c "import json,sys
d=json.load(sys.stdin)
items=d if isinstance(d,list) else d.get('data',[])
for i in items:
    if i.get('session')=='$session' and i.get('key'):
        print(i['key']); break")
  fi
  [[ -n $key ]] || { echo "$resp" >&2; die "session key for $session did not return a secret"; }
  printf '%s\n' "$key" >"$keyfile"
  chmod 600 "$keyfile"
  log "minted scoped session key for $session"
}

save_qr() {
  local session=$1
  local dest="$WAHA_DIR/qr/${session}.png"
  if curl -sf -H "X-Api-Key: $(api_key)" \
      "http://127.0.0.1:${WAHA_PORT}/api/${session}/auth/qr" \
      -o "$dest"; then
    chmod 600 "$dest"
    log "wrote QR $dest"
  else
    log "no QR yet for $session (already linked or still starting)"
  fi
}

cf_api() {
  local method=$1 url=$2
  shift 2
  curl -sS -X "$method" "$url" \
    -H "Authorization: Bearer $(cat "$CF_TOKEN_FILE")" \
    -H "Content-Type: application/json" \
    "$@"
}

ensure_dns() {
  [[ -f $CF_TOKEN_FILE ]] || die "missing $CF_TOKEN_FILE"
  local ip zone_id rec_id rec_ip rec_proxied payload
  ip=$(curl -4 -sf https://ifconfig.me/ip || hostname -I | awk '{print $1}')
  [[ -n $ip ]] || die "could not determine public IPv4"
  zone_id=$(cf_api GET "https://api.cloudflare.com/client/v4/zones?name=carabetta.xyz" \
    | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['result'][0]['id'] if d.get('result') else '')")
  [[ -n $zone_id ]] || die "cloudflare zone carabetta.xyz not found"
  local rec_json
  rec_json=$(cf_api GET "https://api.cloudflare.com/client/v4/zones/${zone_id}/dns_records?name=${HOST_NAME}&type=A")
  rec_id=$(printf '%s' "$rec_json" | python3 -c "import json,sys; r=json.load(sys.stdin).get('result') or []; print(r[0]['id'] if r else '')")
  rec_ip=$(printf '%s' "$rec_json" | python3 -c "import json,sys; r=json.load(sys.stdin).get('result') or []; print(r[0]['content'] if r else '')")
  rec_proxied=$(printf '%s' "$rec_json" | python3 -c "import json,sys; r=json.load(sys.stdin).get('result') or []; print(r[0]['proxied'] if r else '')")
  payload=$(python3 -c "import json; print(json.dumps({'type':'A','name':'wa','content':'$ip','ttl':1,'proxied':True}))")
  if [[ -z $rec_id ]]; then
    log "creating Cloudflare A ${HOST_NAME} -> origin (proxied)"
    cf_api POST "https://api.cloudflare.com/client/v4/zones/${zone_id}/dns_records" --data "$payload" \
      | python3 -c "import json,sys; d=json.load(sys.stdin); assert d.get('success'), d"
  elif [[ $rec_ip != "$ip" || $rec_proxied != True ]]; then
    log "updating Cloudflare A ${HOST_NAME}"
    cf_api PUT "https://api.cloudflare.com/client/v4/zones/${zone_id}/dns_records/${rec_id}" --data "$payload" \
      | python3 -c "import json,sys; d=json.load(sys.stdin); assert d.get('success'), d"
  else
    log "Cloudflare A ${HOST_NAME} already correct"
  fi
}

write_nginx() {
  local available=/etc/nginx/sites-available/wa.carabetta.xyz
  local enabled=/etc/nginx/sites-enabled/wa.carabetta.xyz
  if [[ -f $available && ! -f ${available}.pre-waha ]]; then
    cp -a "$available" "${available}.pre-waha"
    log "backed up existing wa vhost"
  fi
  local cert=/etc/letsencrypt/live/${HOST_NAME}/fullchain.pem
  local key=/etc/letsencrypt/live/${HOST_NAME}/privkey.pem
  if [[ ! -f $cert ]]; then
    log "requesting Let's Encrypt cert for ${HOST_NAME}"
    certbot certonly --webroot -w /var/www/html -d "$HOST_NAME" --non-interactive --agree-tos \
      --register-unsafely-without-email || \
      certbot certonly --webroot -w /var/www/html -d "$HOST_NAME" --non-interactive --agree-tos \
        -m joao.carabetta@gmail.com
  fi
  [[ -f $cert && -f $key ]] || die "missing cert $cert"
  cat >"$available" <<EOF
# WAHA MCP front door. Dashboard stays on 127.0.0.1:${WAHA_PORT}.
# Do not expose /dashboard. Do not restart Arquivo compose to reload this.
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
        return 404;
    }
}
EOF
  ln -sfn "$available" "$enabled"
  # Avoid two vhosts claiming wa.carabetta.xyz (legacy site is whatsapp-mcp).
  for extra in /etc/nginx/sites-enabled/wa /etc/nginx/sites-enabled/wa.carabetta \
               /etc/nginx/sites-enabled/whatsapp-mcp; do
    if [[ -e $extra && $(readlink -f "$extra") != $(readlink -f "$enabled") ]]; then
      rm -f "$extra"
      log "disabled extra site $(basename "$extra")"
    fi
  done
  nginx -t
  systemctl reload nginx
  log "nginx reloaded (wa.carabetta.xyz -> 127.0.0.1:${WAHA_PORT})"
}

verify_stack() {
  log "=== post checks ==="
  curl -sf http://127.0.0.1:8000/health && echo " prod-api=ok" || echo " prod-api=FAIL"
  curl -sf http://127.0.0.1:8001/health && echo " staging-api=ok" || echo " staging-api=FAIL"
  curl -sf http://127.0.0.1:3131/health && echo " gbrain=ok" || echo " gbrain=FAIL"
  systemctl is-active gbrain nginx docker
  docker ps --filter name=arquivo --format '{{.Names}} {{.Status}}'
  docker ps --filter name=waha --format '{{.Names}} {{.Status}}'
  local code
  code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "https://${HOST_NAME}/mcp" \
    -H "Content-Type: application/json" -d '{}' || true)
  log "public /mcp without key HTTP ${code} (expect 401)"
}

write_report() {
  umask 077
  cat >"$REPORT" <<EOF
WAHA bootstrap $(date -u +%Y-%m-%dT%H:%M:%SZ)
host=$(hostname)
port=127.0.0.1:${WAHA_PORT}
public=https://${HOST_NAME}/mcp
sessions=personal,second
mcp_keys=/etc/waha/mcp-personal.key /etc/waha/mcp-second.key
admin_env=/etc/waha/env
qr_dir=${WAHA_DIR}/qr
mem_available_mib=$(available_mib)
EOF
  chmod 600 "$REPORT"
}

main() {
  require_root
  inspect_host
  local avail
  avail=$(available_mib)
  log "MemAvailable=${avail} MiB"
  if [[ $avail -lt 700 ]]; then
    die "MemAvailable ${avail} MiB is too low for WAHA on this box — resize ARV or install on obs instead"
  fi
  ensure_not_arquivo_compose
  ensure_env
  write_compose
  start_waha
  ensure_dns
  write_nginx
  ensure_session personal
  ensure_session second
  sleep 5
  ensure_mcp_app personal
  ensure_mcp_app second
  ensure_session_key personal
  ensure_session_key second
  save_qr personal
  save_qr second
  verify_stack
  write_report
  log "done. Keys stay in /etc/waha (not printed)."
}

main "$@"
