#!/usr/bin/env bash
# Diagnose and repair the live WAHA worker. Never bootstraps, pulls, or rewrites compose/env.
set -euo pipefail

WAHA_DIR=/opt/waha
WAHA_ENV=/etc/waha/env
WAHA_PORT=3140

log() { printf '[waha-repair] %s\n' "$*"; }
die() { printf '[waha-repair] ERROR: %s\n' "$*" >&2; exit 1; }

[[ ${EUID} -eq 0 ]] || die "run as root"
[[ -d $WAHA_DIR && -f $WAHA_ENV && -f $WAHA_DIR/docker-compose.yml ]] || die "WAHA install missing — refuse to bootstrap"

api_key() {
  awk -F= '/^WAHA_API_KEY=/ && $1=="WAHA_API_KEY" {print $2; exit}' "$WAHA_ENV"
}

waha_curl() {
  local method=$1 path=$2
  shift 2
  curl -sS -X "$method" "http://127.0.0.1:${WAHA_PORT}${path}" \
    -H "X-Api-Key: $(api_key)" \
    -H "Accept: application/json" \
    "$@"
}

start_existing() {
  if docker ps -a --format '{{.Names}}' | grep -qx waha-redis; then
    docker start waha-redis >/dev/null || true
  fi
  if docker ps -a --format '{{.Names}}' | grep -qx waha; then
    docker start waha >/dev/null || true
  else
    die "container waha does not exist — refuse to compose-create"
  fi
}

wait_api() {
  local i
  for i in $(seq 1 30); do
    if waha_curl GET /api/sessions >/dev/null 2>&1; then
      log "API is up"
      return 0
    fi
    sleep 2
  done
  docker ps -a --filter name=waha --format '{{.Names}} {{.Status}} {{.Ports}}' >&2 || true
  docker logs waha --tail 60 2>&1 | sed -E 's/[A-Fa-f0-9]{32,}/[REDACTED]/g' >&2 || true
  die "WAHA API did not come up"
}

print_status() {
  log "=== containers ==="
  docker ps -a --filter name=waha --format '{{.Names}} {{.Status}} {{.Ports}}'
  if docker ps --format '{{.Names}}' | grep -qx waha-redis; then
    docker exec waha-redis redis-cli ping 2>/dev/null | sed 's/^/[waha-repair] redis /' || log "redis ping failed"
  else
    log "redis container not running"
  fi
  log "=== env flags (no secrets) ==="
  awk -F= '
    $1=="WHATSAPP_DEFAULT_ENGINE" || $1=="WAHA_APPS_ENABLED" || $1=="WAHA_APPS_OFF" ||
    $1=="WAHA_DASHBOARD_ENABLED" || $1=="WAHA_BASE_URL" || $1=="WAHA_PUBLIC_URL" ||
    $1=="WAHA_WORKER_ID" || $1=="REDIS_URL" {
      if ($1=="REDIS_URL") { print $1"=set"; next }
      print $1"="$2
    }
  ' "$WAHA_ENV"
  grep -q '^WAHA_API_KEY_PLAIN=' "$WAHA_ENV" && log "WAHA_API_KEY_PLAIN=set" || log "WAHA_API_KEY_PLAIN=missing"
  log "=== session files ==="
  ls -la "$WAHA_DIR/sessions" 2>/dev/null | awk '{print $1,$3,$9}' || true
  log "=== api sessions ==="
  waha_curl GET /api/sessions | python3 -c '
import json,sys
raw=sys.stdin.read()
try:
    d=json.loads(raw)
except Exception:
    print("SESSIONS_UNPARSEABLE")
    raise SystemExit
items=d if isinstance(d,list) else d.get("data", d.get("sessions", []))
if not items:
    print("SESSIONS_EMPTY")
for s in items:
    me=s.get("me") or {}
    cfg=s.get("config") or {}
    print("SESSION", s.get("name"), s.get("status"), "engine="+str(s.get("engine") or cfg.get("engine") or "-"), "phone="+str(me.get("id") or "-"))
'
  log "=== api server ==="
  waha_curl GET /api/server 2>/dev/null | python3 -c '
import json,sys
try:
    d=json.load(sys.stdin)
except Exception:
    print("SERVER_UNPARSEABLE"); raise SystemExit
if isinstance(d, dict):
    print("server", d.get("version") or d.get("status") or list(d)[:8])
else:
    print("server", type(d).__name__)
' || log "server endpoint failed"
}

ensure_session() {
  local name=$1
  local existing
  existing=$(waha_curl GET /api/sessions)
  if echo "$existing" | python3 -c "
import json,sys
d=json.load(sys.stdin)
items=d if isinstance(d,list) else d.get('data', d.get('sessions', []))
sys.exit(0 if '$name' in [x.get('name') for x in items] else 1)
" 2>/dev/null; then
    log "starting session $name"
    waha_curl POST "/api/sessions/${name}/start" -H "Content-Type: application/json" -d '{}' >/dev/null || true
    return 0
  fi
  log "creating session $name"
  waha_curl POST /api/sessions -H "Content-Type: application/json" \
    -d "{\"name\":\"${name}\",\"config\":{\"engine\":\"GOWS\"}}" >/dev/null
  waha_curl POST "/api/sessions/${name}/start" -H "Content-Type: application/json" -d '{}' >/dev/null || true
}

log "will not bootstrap or pull images"
start_existing
wait_api
print_status
ensure_session personal
ensure_session second
sleep 3
log "=== sessions after repair ==="
waha_curl GET /api/sessions | python3 -c '
import json,sys
d=json.load(sys.stdin)
items=d if isinstance(d,list) else d.get("data", d.get("sessions", []))
if not items:
    print("SESSIONS_EMPTY")
for s in items:
    me=s.get("me") or {}
    print("SESSION", s.get("name"), s.get("status"), "phone="+str(me.get("id") or "-"))
'
log "dashboard worker needs the admin API key in the worker card (from /etc/waha/env WAHA_API_KEY), not the dashboard password"
log "done"
