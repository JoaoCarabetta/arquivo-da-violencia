#!/usr/bin/env bash
# Refresh QR PNGs on the box. Never prints API keys.
set -euo pipefail

WAHA_ENV=/etc/waha/env
WAHA_PORT=3140
QR_DIR=/opt/waha/qr

api_key() {
  awk -F= '/^WAHA_API_KEY=/ && $1=="WAHA_API_KEY" {print $2; exit}' "$WAHA_ENV"
}

[[ -f $WAHA_ENV ]] || { echo "missing $WAHA_ENV — WAHA not installed"; exit 1; }
mkdir -p "$QR_DIR"
chmod 700 "$QR_DIR"

echo "=== waha containers ==="
docker ps --filter name=waha --format '{{.Names}} {{.Status}} {{.Ports}}'
echo "=== sessions ==="
sessions_json=$(curl -sS "http://127.0.0.1:${WAHA_PORT}/api/sessions" -H "X-Api-Key: $(api_key)" -H "Accept: application/json")
printf '%s' "$sessions_json" | python3 -c "
import json,sys
d=json.load(sys.stdin)
items=d if isinstance(d,list) else d.get('data', d.get('sessions', []))
for s in items:
    me=s.get('me') or {}
    print(s.get('name'), s.get('status'), me.get('id') or me.get('pushName') or '-')
"

for name in personal second; do
  dest="${QR_DIR}/${name}.png"
  ok=0
  for i in $(seq 1 20); do
    if curl -sf -H "X-Api-Key: $(api_key)" -H "Accept: image/png" \
        "http://127.0.0.1:${WAHA_PORT}/api/${name}/auth/qr?format=image" \
        -o "$dest"; then
      # reject tiny/error JSON saved as png
      if file "$dest" | grep -qi 'PNG\|JPEG\|image'; then
        chmod 600 "$dest"
        echo "QR_OK ${name} bytes=$(wc -c < "$dest")"
        ok=1
        break
      fi
      echo "QR_WAIT ${name} not-an-image attempt=${i}"
    else
      echo "QR_WAIT ${name} http-fail attempt=${i}"
    fi
    sleep 3
  done
  [[ $ok -eq 1 ]] || echo "QR_MISSING ${name}"
done

echo "QR_COUNT=$(find "$QR_DIR" -name '*.png' | wc -l)"
ls -la "$QR_DIR"
