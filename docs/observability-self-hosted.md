# Self-hosted observability (dedicated Hetzner VPS)

Prometheus + Grafana on **`arquivo-observability`** (`62.238.12.182`), scraping
metrics from the production app VPS.

## Architecture

```
Prod VPS (77.42.72.111)              Observability VPS (62.238.12.182)
  arquivo-api:8000/metrics  ──scrape──►  Prometheus
  arquivo-worker:9091/metrics ─scrape─►  Grafana :3000
```

Prod ports `8000` and `9091` are **firewall-restricted** to the observability
VPS IP only.

## Deploy / update

From your laptop (repo root):

```bash
bash infra/observability/deploy.sh
```

The script installs Docker on the obs VPS, syncs configs, starts the stack, and
prints the Grafana URL + admin password.

## SSH

```bash
ssh hetzner-arv-obs    # 62.238.12.182
```

## Dashboard

After deploy, open:

- **Grafana home:** http://62.238.12.182:3000
- **Pipeline dashboard:** Dashboards → Arquivo → *Arquivo da Violência - Pipeline*

## Prod requirements

The prod worker must expose port `9091` (metrics HTTP server) and the API must
expose `8000`. Rebuild/restart prod after pulling the observability branch:

```bash
ssh hetzner-arv-public
cd /root/arquivo-da-violencia
docker compose -p prod build api worker
docker compose -p prod up -d --no-deps api worker
```

## Cost

~€6.50/month (Hetzner CX23, hel1).
