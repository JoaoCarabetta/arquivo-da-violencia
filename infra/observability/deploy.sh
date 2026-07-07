#!/bin/bash
# Bootstrap the self-hosted observability VPS (Prometheus + Grafana).
set -euo pipefail

OBS_HOST="${OBS_HOST:-hetzner-arv-obs}"
OBS_DIR="/opt/arquivo-observability"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
GRAFANA_PASSWORD="${GRAFANA_ADMIN_PASSWORD:-$(openssl rand -base64 18)}"

echo "==> Installing Docker on $OBS_HOST (if needed)"
ssh "$OBS_HOST" 'command -v docker >/dev/null || (
  apt-get update -qq
  apt-get install -y -qq ca-certificates curl
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo ${VERSION_CODENAME}) stable" > /etc/apt/sources.list.d/docker.list
  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
)'

echo "==> Syncing observability stack"
ssh "$OBS_HOST" "mkdir -p $OBS_DIR"
rsync -az --delete "$REPO_ROOT/infra/observability/" "$OBS_HOST:$OBS_DIR/"

echo "==> Starting Prometheus + Grafana"
ssh "$OBS_HOST" "cd $OBS_DIR && cat > .env <<EOF
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=$GRAFANA_PASSWORD
GRAFANA_ROOT_URL=http://$(ssh -G $OBS_HOST | awk '/^hostname /{print $2}'):3000
EOF
ufw allow 22/tcp >/dev/null 2>&1 || true
ufw allow 3000/tcp >/dev/null 2>&1 || true
ufw --force enable >/dev/null 2>&1 || true
docker compose up -d"

echo "==> Locking down prod scrape ports to observability VPS only"
OBS_IP=$(ssh -G "$OBS_HOST" | awk '/^hostname /{print $2}')
PROD_HOST="${PROD_HOST:-hetzner-arv-public}"
ssh "$PROD_HOST" "
  ufw allow from $OBS_IP to any port 8000 proto tcp comment 'obs-prometheus-api' >/dev/null 2>&1 || true
  ufw allow from $OBS_IP to any port 9091 proto tcp comment 'obs-prometheus-worker' >/dev/null 2>&1 || true
  ufw reload >/dev/null 2>&1 || true
"

echo ""
echo "Grafana URL:  http://$OBS_IP:3000"
echo "Login:        admin / $GRAFANA_PASSWORD"
echo "Dashboard:    http://$OBS_IP:3000/dashboards"
