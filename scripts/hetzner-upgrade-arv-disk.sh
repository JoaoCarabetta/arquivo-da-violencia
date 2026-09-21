#!/usr/bin/env bash
# Grow the ARV Hetzner primary disk to the size already included in cx33
# (40 → 80 GB). Reboots the server. Does not print the API token.
#
#   bash scripts/hetzner-upgrade-arv-disk.sh           # dry-run
#   bash scripts/hetzner-upgrade-arv-disk.sh --execute
#
# After reboot, Ubuntu cloud-init often growparts automatically. The next
# ops-checkup `check-host-disk.sh --remediate` also expand_root_if_unused_space.
set -euo pipefail

API="${HETZNER_API:-https://api.hetzner.cloud/v1}"
SERVER_ID="${ARV_HETZNER_SERVER_ID:-115850201}"
SERVER_TYPE="${ARV_HETZNER_SERVER_TYPE:-cx33}"
EXECUTE=false

for arg in "$@"; do
  case "$arg" in
    --execute) EXECUTE=true ;;
    --dry-run) EXECUTE=false ;;
  esac
done

if [[ -z "${HETZNER_API_TOKEN:-}" ]]; then
  echo "HETZNER_API_TOKEN is not set" >&2
  exit 2
fi

export HETZNER_API="$API"
python3 - "$EXECUTE" "$SERVER_ID" "$SERVER_TYPE" <<'PY'
import json, os, sys, time, urllib.request

execute = sys.argv[1] == "true"
server_id = sys.argv[2]
server_type = sys.argv[3]
token = os.environ["HETZNER_API_TOKEN"]
api = os.environ.get("HETZNER_API", "https://api.hetzner.cloud/v1")


def req(method, path, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    r = urllib.request.Request(
        api + path,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(r, timeout=60) as resp:
        return json.load(resp)


info = req("GET", f"/servers/{server_id}")["server"]
current_type = info["server_type"]["name"]
included = info["server_type"]["disk"]
primary = info["primary_disk_size"]
status = info["status"]
print(
    f"server={info['name']} status={status} type={current_type} "
    f"type_disk={included}G primary_disk_size={primary}G"
)

if current_type != server_type:
    print(f"refusing: type is {current_type}, expected {server_type}", file=sys.stderr)
    sys.exit(3)
if primary >= included:
    print(f"already at full disk ({primary}G ≥ {included}G); nothing to do")
    sys.exit(0)
if status != "running":
    print(f"refusing: server status is {status}, expected running", file=sys.stderr)
    sys.exit(4)

if not execute:
    print(f"dry-run: would change_type {server_type} upgrade_disk=true ({primary}→{included}G). Reboots the box.")
    sys.exit(0)

print(f"executing change_type upgrade_disk {primary}→{included}G (server will reboot)")
action = req(
    "POST",
    f"/servers/{server_id}/actions/change_type",
    {"server_type": server_type, "upgrade_disk": True},
)
action_id = (action.get("action") or {}).get("id")
print(f"action_id={action_id} command={(action.get('action') or {}).get('command')}")

deadline = time.time() + 15 * 60
last_status = None
while time.time() < deadline:
    info = req("GET", f"/servers/{server_id}")["server"]
    last_status = info["status"]
    primary = info["primary_disk_size"]
    print(f"wait status={last_status} primary_disk_size={primary}G")
    if last_status == "running" and primary >= included:
        print(f"done: primary_disk_size={primary}G type_disk={included}G")
        sys.exit(0)
    time.sleep(10)

print(f"timeout waiting for running+{included}G (last status={last_status} primary={primary}G)", file=sys.stderr)
sys.exit(5)
PY
