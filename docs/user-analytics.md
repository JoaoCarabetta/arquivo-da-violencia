# User analytics (self-hosted Umami)

Product analytics for the public portal — page views and core interactions.
This is **not** pipeline observability (Prometheus/Grafana). See
[observability-self-hosted.md](observability-self-hosted.md) for ops metrics.

| Resource | Value |
|----------|-------|
| Dashboard | https://analytics.carabetta.xyz |
| Host | Observability VPS `62.238.12.182` |
| Stack directory | `/opt/arquivo-umami` |
| Tracker script | `https://analytics.carabetta.xyz/metrics.js` |

Umami is cookieless and privacy-friendly (no Google scripts, no consent banner
required for the tracker itself).

## Architecture

```
Public SPA  --metrics.js + /api/send-->  Umami (:3001 localhost)
                                        └── Postgres (umami_db_data)
You  ----HTTPS nginx---->  analytics.carabetta.xyz
```

Pipeline Grafana stays on `observability.carabetta.xyz` (port 3000). Umami uses
port **3001** on the same VPS so the two stacks do not collide.

## Deploy

### Prerequisites (one-time)

1. DNS **A** record: `analytics.carabetta.xyz` → `62.238.12.182`
2. From laptop (SSH key as for observability):

```bash
bash infra/umami/deploy.sh
```

3. Open https://analytics.carabetta.xyz — default login is Umami’s first-run
   admin (change password immediately).
4. **Settings → Websites → Add website** twice:
   - Prod: domain `arquivodaviolencia.com.br`
   - Staging: domain `staging.arquivodaviolencia.com.br`
5. Copy each website UUID into GitHub Actions secrets:
   - `UMAMI_WEBSITE_ID_PROD`
   - `UMAMI_WEBSITE_ID_STAGING`

Frontend CI ([`.github/workflows/deploy-frontend.yml`](../.github/workflows/deploy-frontend.yml))
bakes `VITE_UMAMI_URL` + the branch-appropriate website ID into the image.

### Update / redeploy

```bash
bash infra/umami/deploy.sh
```

Secrets in `/opt/arquivo-umami/.env` are preserved across redeploys.

## Frontend env

| Variable | Purpose |
|----------|---------|
| `VITE_UMAMI_URL` | Base URL (default `https://analytics.carabetta.xyz`) |
| `VITE_UMAMI_WEBSITE_ID` | Website UUID; empty = tracking disabled |

Local Docker leaves these unset (no tracking). To test against staging Umami,
set both in the frontend service env and rebuild/restart Vite.

Client code: [`frontend/src/lib/analytics.ts`](../frontend/src/lib/analytics.ts).

## Event taxonomy

| Event | When | Props |
|-------|------|-------|
| *(pageview)* | SPA route change | path via Umami |
| `mode_switch` | Stats / Feed / Data tab | `mode`: stats\|feed\|data |
| `search` | Successful locate | `kind`: place\|cep\|geocode\|brasil |
| `filter_toggle` | Type/method/period/state/city chip | `group`, `action`: add\|remove |
| `filter_clear` | Clear all filters | — |
| `date_range` | Date preset or custom range | `preset`: 30d\|90d\|365d\|custom\|clear |
| `event_open` | Open event detail | `event_id` |
| `csv_export` | CSV download click | `column_count` |
| `source_click` | Outbound news source link | `event_id` |
| `language_toggle` | PT ↔ EN | `lang`: pt\|en |

About (`/sobre`) and methodology (`/metodologia`) are covered by pageviews.
Map pan/zoom and **admin routes** (`/admin/*`) are **not** tracked in v1
(`RouteTracker` skips them).

## Reading the dashboard

- **Visitors / views** — overall usage
- **Pages** — `/`, `/eventos`, `/eventos/:id`, `/dados`, `/sobre`, `/metodologia`
- **Events** — custom events above; filter by name and inspect properties
- Use separate websites for prod vs staging so traffic is not mixed

## Troubleshooting

| Symptom | Likely cause |
|---------|----------------|
| No data in Umami | Website ID missing from frontend build secrets, or DNS/TLS not ready |
| `/metrics.js` 404 | Umami not up, or `TRACKER_SCRIPT_NAME` mismatch |
| Events missing, pageviews OK | `trackEvent` called before script load — usually transient; retry interaction |
| Ad blockers | Tracker renamed to `metrics.js`; still may be blocked — proxy via main domain later if needed |
