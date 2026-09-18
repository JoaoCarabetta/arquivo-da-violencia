#!/usr/bin/env bash
# Compact snapshot of key pipeline/host metrics queried THROUGH the MCP
# endpoint (same chain agents use: mcp-grafana → Grafana → Prometheus).
# Runs on the obs VPS. Called by deploy-remote.sh at the end of each deploy;
# also handy as a terminal dashboard: bash /opt/arquivo-observability/mcp-snapshot.sh
# Prints "label<TAB>value" lines. Never prints the token.
set -euo pipefail

OBS_DIR="${OBS_DIR:-/opt/arquivo-observability}"
DOMAIN="${OBS_DOMAIN:-observability.carabetta.xyz}"
MCP_URL="${MCP_URL:-http://127.0.0.1:8000/mcp}"

token="$(grep -E '^MCP_GRAFANA_SERVER_TOKEN=' "$OBS_DIR/.env" | cut -d= -f2-)"
[[ -n "$token" ]] || { echo "ERROR: MCP_GRAFANA_SERVER_TOKEN not found in $OBS_DIR/.env" >&2; exit 1; }

hdr=(-H "Host: ${DOMAIN}" -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' -H "Authorization: Bearer ${token}")

init_headers="$(mktemp)"
curl -s --max-time 20 -D "$init_headers" -o /dev/null -X POST "$MCP_URL" "${hdr[@]}" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"mcp-snapshot","version":"1.0"}}}'
session="$(awk 'tolower($1)=="mcp-session-id:"{print $2}' "$init_headers" | tr -d '\r')"
rm -f "$init_headers"
sess=()
[[ -n "$session" ]] && sess=(-H "Mcp-Session-Id: ${session}")
curl -s --max-time 20 -o /dev/null -X POST "$MCP_URL" "${hdr[@]}" "${sess[@]}" \
  -d '{"jsonrpc":"2.0","method":"notifications/initialized"}' || true

run() { # run <label> <promql-instant-expr>
  local label="$1" expr="$2" payload resp
  payload="$(python3 -c 'import json,sys; print(json.dumps({"jsonrpc":"2.0","id":9,"method":"tools/call","params":{"name":"query_prometheus","arguments":{"datasourceUid":"prometheus","expr":sys.argv[1],"endTime":"now","queryType":"instant"}}}))' "$expr")"
  resp="$(curl -s --max-time 30 -X POST "$MCP_URL" "${hdr[@]}" "${sess[@]}" -d "$payload" || true)"
  RESP="$resp" LABEL="$label" python3 <<'PYEOF'
import json, os, sys

label = os.environ["LABEL"]
raw = os.environ.get("RESP", "")
if raw.startswith("event:") or raw.startswith("data:") or "\ndata:" in raw:
    raw = "".join(l[5:].strip() for l in raw.splitlines() if l.startswith("data:"))
try:
    msg = json.loads(raw)
    text = msg["result"]["content"][0]["text"]
    data = json.loads(text)
    if isinstance(data, dict):
        data = data.get("data", data)
    if isinstance(data, dict):
        data = data.get("result", [])
    if not isinstance(data, list):
        data = [data]
    if not data:
        print(f"{label}\t<no data>")
    for series in data:
        metric = series.get("metric", {}) if isinstance(series, dict) else {}
        value = series.get("value", [None, "?"])[1] if isinstance(series, dict) else series
        keep = {k: v for k, v in metric.items()
                if k not in ("__name__", "service", "environment", "job", "instance")}
        sel = ",".join(f"{k}={v}" for k, v in sorted(keep.items()))
        print(f"{label}{'{' + sel + '}' if sel else ''}\t{value}")
except Exception as exc:
    print(f"{label}\tERROR {exc}", file=sys.stderr)
PYEOF
}

echo "# metrics-snapshot via MCP — $(date -u +%FT%TZ)"
run worker_alive        'pipeline_worker_alive{service="api"}'
run redis_connected     'pipeline_redis_connected{service="api"}'
run queue_depth         'pipeline_queue_depth{service="api"}'
run heartbeat_misses    'pipeline_worker_heartbeat_misses{service="api"}'
run stuck_total         'sum(pipeline_stuck_sources{service="api"})'
run backlog_classification 'pipeline_inventory_sources{service="api",status="ready_for_classification"}'
run backlog_download    'pipeline_inventory_sources{service="api",status="ready_for_download"}'
run backlog_extraction  'pipeline_inventory_sources{service="api",status="ready_for_extraction"}'
run failures_24h        'sum(pipeline_attempt_failures_24h{service="api"})'
run open_bugs           'pipeline_open_failure_issues{service="api"}'
run inventory_total     'pipeline_inventory_total{service="api"}'
run violent_death       'pipeline_inventory_violent_death{service="api"}'
run raw_events          'pipeline_inventory_raw_events{service="api"}'
run unique_events       'pipeline_inventory_unique_events{service="api"}'
run last_ingest_min     '(time() - pipeline_cron_last_success_timestamp{service="worker",cron="ingest_cities_hourly"}) / 60'
run ram_pct             '(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100'
run disk_pct            '(1 - (node_filesystem_avail_bytes{mountpoint="/",fstype!="rootfs"} / node_filesystem_size_bytes{mountpoint="/",fstype!="rootfs"})) * 100'
run cpu_pct             '100 - (avg by (host) (rate(node_cpu_seconds_total{mode="idle"}[2m])) * 100)'
run scrape_up           'up'
echo "# end metrics-snapshot"
