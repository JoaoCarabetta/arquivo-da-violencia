#!/usr/bin/env bash
# Host disk check + safe cleanup for the ARV prod VPS.
# Never touches Postgres/Redis volumes, gbrain, or carabetta.xyz tiles.
#
#   bash scripts/check-host-disk.sh
#   bash scripts/check-host-disk.sh --remediate   # prune unused docker + old dumps + journals
#   bash scripts/check-host-disk.sh --json
#   bash scripts/check-host-disk.sh --notify --remediate
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
if [[ -f "$REPO_DIR/.env" ]]; then set -a; # shellcheck disable=SC1091
  source "$REPO_DIR/.env"; set +a; fi

REMEDIATE=false
NOTIFY=false
JSON=false
WARN_PCT=75
CRIT_PCT=90
BACKUP_DIR="${HOST_DISK_BACKUP_DIR:-/root/backups}"
BACKUP_KEEP_DAYS="${HOST_DISK_BACKUP_KEEP_DAYS:-7}"

for arg in "$@"; do
  case "$arg" in
    --remediate) REMEDIATE=true ;;
    --notify) NOTIFY=true ;;
    --json) JSON=true ;;
  esac
done

pct_used() { df -P / | awk 'NR==2 {gsub("%","",$5); print $5}'; }
avail_human() { df -h / | awk 'NR==2 {print $4}'; }

USED="$(pct_used)"
AVAIL="$(avail_human)"
ACTIONS=()
FAILURES=()
WARNINGS=()

if (( USED >= CRIT_PCT )); then
  FAILURES+=("disk_critical(${USED}%_used,${AVAIL}_free)")
elif (( USED >= WARN_PCT )); then
  WARNINGS+=("disk_elevated(${USED}%_used,${AVAIL}_free)")
fi

if $REMEDIATE && (( USED >= WARN_PCT )); then
  before="$USED"
  # Dangling images only (never -a: that can delete tags still referenced by compose).
  if docker image prune -f >/tmp/host-disk-prune.txt 2>&1; then
    ACTIONS+=("docker_image_prune")
  fi
  if docker builder prune -af --filter until=48h >/tmp/host-disk-builder.txt 2>&1; then
    ACTIONS+=("docker_builder_prune_48h")
  fi
  if command -v journalctl >/dev/null; then
    journalctl --vacuum-size=200M >/dev/null 2>&1 || true
    ACTIONS+=("journal_vacuum_200M")
  fi
  if [[ -d "$BACKUP_DIR" ]]; then
    deleted="$(find "$BACKUP_DIR" -type f -mtime "+${BACKUP_KEEP_DAYS}" -print -delete 2>/dev/null | wc -l | tr -d ' ')"
    ACTIONS+=("backups_deleted_older_than_${BACKUP_KEEP_DAYS}d(${deleted})")
  fi
  # Cap huge container json logs (safe: docker recreates on write).
  while IFS= read -r -d '' log; do
    truncate -s 20M "$log" || true
    ACTIONS+=("truncated_$(basename "$(dirname "$log")")_json.log")
  done < <(find /var/lib/docker/containers -name '*-json.log' -size +200M -print0 2>/dev/null || true)

  USED="$(pct_used)"
  AVAIL="$(avail_human)"
  ACTIONS+=("after_prune_${USED}%_${AVAIL}_free_was_${before}%")
  FAILURES=()
  WARNINGS=()
  if (( USED >= CRIT_PCT )); then
    FAILURES+=("disk_critical_after_prune(${USED}%_used,${AVAIL}_free)")
  elif (( USED >= WARN_PCT )); then
    WARNINGS+=("disk_elevated_after_prune(${USED}%_used,${AVAIL}_free)")
  fi
fi

STATUS="healthy"
(( ${#FAILURES[@]} > 0 )) && STATUS="unhealthy"

json_array() {
  if [ "$#" -eq 0 ]; then echo '[]'; else
    printf '%s\n' "$@" | python3 -c 'import json,sys; print(json.dumps([l for l in sys.stdin.read().splitlines() if l]))'
  fi
}

if $JSON; then
  python3 - <<PY
import json
print(json.dumps({
  "status": "${STATUS}",
  "used_pct": int("${USED}"),
  "avail": "${AVAIL}",
  "failures": $(json_array ${FAILURES[@]+"${FAILURES[@]}"}),
  "warnings": $(json_array ${WARNINGS[@]+"${WARNINGS[@]}"}),
  "actions": $(json_array ${ACTIONS[@]+"${ACTIONS[@]}"}),
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
}))
PY
else
  echo "disk / ${USED}% used, ${AVAIL} free — ${STATUS}"
  (( ${#FAILURES[@]} )) && printf '  FAIL %s\n' "${FAILURES[@]}"
  (( ${#WARNINGS[@]} )) && printf '  WARN %s\n' "${WARNINGS[@]}"
  (( ${#ACTIONS[@]} )) && printf '  DID  %s\n' "${ACTIONS[@]}"
fi

send_telegram() {
  local text="$1"
  [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ] || return 0
  curl -sf -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
    -d "chat_id=${TELEGRAM_CHAT_ID}" --data-urlencode "text=${text}" >/dev/null || true
}

if $NOTIFY && [[ "$STATUS" == "unhealthy" ]]; then
  send_telegram "ARV disk UNHEALTHY: ${USED}% used, ${AVAIL} free. Actions: ${ACTIONS[*]:-none}. Grow primary disk 40→80 GB (already included in cx33) if prune is not enough."
  if [ -n "${PIPELINE_HEALTH_WEBHOOK_URL:-}" ]; then
    token="${PIPELINE_HEALTH_WEBHOOK_AUTH:-}"
    token="${token#Bearer }"
    curl -sf -X POST "$PIPELINE_HEALTH_WEBHOOK_URL" \
      -H "Content-Type: application/json" \
      ${token:+-H "Authorization: Bearer ${token}"} \
      -d "{\"status\":\"unhealthy\",\"failures\":$(json_array ${FAILURES[@]+"${FAILURES[@]}"}),\"host\":\"$(hostname -s)\",\"prompt\":\"ARV root disk still critical after safe prune. SSH hetzner-arv, run bash scripts/check-host-disk.sh --json, df -h, docker system df. Do NOT delete postgres/redis/gbrain. If still >90%, grow the Hetzner primary disk 40→80GB (cx33 included; rescale same type with upgrade_disk). Do not push master.\"}" \
      >/dev/null || true
  fi
fi

[[ "$STATUS" == "healthy" ]]
