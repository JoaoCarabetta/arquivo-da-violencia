#!/usr/bin/env bash
# Grow the ARV Hetzner primary disk to the size already included in cx33
# (40 → 80 GB). Powers the server off, upgrades the disk, powers it back on.
# Does not print the API token.
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
import json, os, sys, time, urllib.error, urllib.request

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
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        print(f"HTTP {e.code} {method} {path}: {body}", file=sys.stderr)
        raise


def server():
    return req("GET", f"/servers/{server_id}")["server"]


def wait_status(wanted, seconds):
    deadline = time.time() + seconds
    last = None
    while time.time() < deadline:
        info = server()
        last = info["status"]
        print(f"wait status={last} primary_disk_size={info['primary_disk_size']}G")
        if last == wanted:
            return info
        time.sleep(5)
    return server()


info = server()
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
if status not in ("running", "off"):
    print(f"refusing: server status is {status}", file=sys.stderr)
    sys.exit(4)

if not execute:
    print(
        f"dry-run: would shutdown, change_type {server_type} upgrade_disk=true "
        f"({primary}→{included}G), then poweron. Prod sites go down briefly."
    )
    sys.exit(0)

if status == "running":
    print("shutdown (ACPI); poweroff if it stays up")
    req("POST", f"/servers/{server_id}/actions/shutdown")
    info = wait_status("off", 90)
    if info["status"] != "off":
        print("ACPI shutdown timed out; poweroff")
        req("POST", f"/servers/{server_id}/actions/poweroff")
        info = wait_status("off", 90)
    if info["status"] != "off":
        print(f"could not stop server (status={info['status']})", file=sys.stderr)
        sys.exit(6)

print(f"change_type upgrade_disk {primary}→{included}G")
action = req(
    "POST",
    f"/servers/{server_id}/actions/change_type",
    {"server_type": server_type, "upgrade_disk": True},
)
print(
    f"action_id={(action.get('action') or {}).get('id')} "
    f"command={(action.get('action') or {}).get('command')}"
)

deadline = time.time() + 12 * 60
info = server()
while time.time() < deadline:
    info = server()
    print(f"wait status={info['status']} primary_disk_size={info['primary_disk_size']}G")
    if info["primary_disk_size"] >= included and info["status"] in ("off", "running"):
        break
    time.sleep(8)
else:
    print(
        f"timeout waiting for {included}G "
        f"(status={info['status']} primary={info['primary_disk_size']}G)",
        file=sys.stderr,
    )
    sys.exit(5)

if info["status"] != "running":
    print("poweron")
    req("POST", f"/servers/{server_id}/actions/poweron")
    info = wait_status("running", 180)

if info["status"] == "running" and info["primary_disk_size"] >= included:
    print(
        f"done: primary_disk_size={info['primary_disk_size']}G "
        f"type_disk={included}G status={info['status']}"
    )
    sys.exit(0)

print(
    f"not running at full disk (status={info['status']} "
    f"primary={info['primary_disk_size']}G)",
    file=sys.stderr,
)
sys.exit(5)
PY
