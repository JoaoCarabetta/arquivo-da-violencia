# Chile Ingest Integration - Changes Summary

## Problem
Chile support landed in PR #119 (merged to develop), but the live cron and API endpoints did not actually call the Chile ingestion functions. The hourly ingest path (`ingest_cities_hourly` → `ingest_cities_task`) was hard-coded to only ingest Brazilian cities.

## Solution
Modified `ingest_cities_task` to automatically ingest **both** Brazil and Chile when no explicit city list is provided (the hourly/cron path). When an explicit city list is provided, the behavior remains unchanged (Brazilian cities only).

## Changes Made

### 1. `backend/app/tasks/pipeline.py` - `ingest_cities_task()`

**Before:**
```python
from app.services.ingestion import ingest_all_cities

result = await ingest_all_cities(cities=cities, when=when, resolve_urls=True)
```

**After:**
```python
from app.services.ingestion import ingest_all_cities, ingest_all_countries

# When cities is None (hourly/cron path), ingest all countries.
# When an explicit city list is provided, use Brazil as default.
if cities is None:
    result = await ingest_all_countries(when=when, resolve_urls=True)
else:
    result = await ingest_all_cities(cities=cities, when=when, resolve_urls=True, country="BR")
```

### 2. `backend/app/routers/pipeline.py` - API Endpoint Docstrings

Updated the following endpoints to reflect multi-country support:

- **`POST /pipeline/ingest-cities`**: Changed from "Brazilian cities" to "cities across all countries (BR + CL)"
- **`POST /pipeline/full`**: Updated to indicate ingestion from all configured cities (BR + CL)

## Behavior

### Hourly Cron (cities=None)
```python
# Worker cron at minute :05
ingest_cities_hourly()
  → ingest_cities_task(ctx, cities=None, when="1h")
    → ingest_all_countries(when="1h", resolve_urls=True)
      → ingest_all_cities(country="BR") + ingest_all_cities(country="CL")
```

**Result**: Both Brazilian and Chilean news sources are collected.

### API Call Without Cities (cities=None)
```bash
curl -X POST "http://localhost:8010/api/pipeline/ingest-cities?when=1h"
```

**Result**: Same as hourly cron - both countries are ingested.

### API Call With Explicit Cities
```bash
curl -X POST "http://localhost:8010/api/pipeline/ingest-cities?when=1h&cities=São%20Paulo,Rio%20de%20Janeiro"
```

**Result**: Only the specified Brazilian cities are ingested (existing behavior preserved).

## Testing

### Manual Verification Steps (requires Docker)

1. **Start the dev stack:**
   ```bash
   docker compose -f docker-compose.dev.yml -f docker-compose.dev.override.yml up -d --build
   ```

2. **Trigger a manual ingest:**
   ```bash
   curl -X POST "http://localhost:8010/api/pipeline/ingest-cities?when=1h"
   ```

3. **Check the logs for both BR and CL:**
   ```bash
   docker compose -f docker-compose.dev.yml logs -f worker
   ```

   Expected log output:
   ```
   [INGEST_CITIES] Starting with when=1h
   Starting multi-country ingestion (BR + CL)
   Starting PARALLEL city ingestion for 52 cities in BR
   Starting PARALLEL city ingestion for 15 cities in CL
   ...
   MULTI-COUNTRY INGESTION COMPLETE
   Total entries: <count>
   Total sources: <count>
   ```

4. **Verify Chilean sources in database:**
   ```bash
   docker compose -f docker-compose.dev.yml exec api python -c "
   import asyncio
   from app.database import async_session_maker
   from app.models import SourceGoogleNews
   from sqlmodel import select

   async def check():
       async with async_session_maker() as session:
           # Check for Chilean news sources
           result = await session.exec(
               select(SourceGoogleNews)
               .where(SourceGoogleNews.search_query.like('%Santiago%'))
               .limit(5)
           )
           sources = result.all()
           print(f'Found {len(sources)} Chilean sources')
           for s in sources:
               print(f'  - {s.headline} ({s.search_query})')
   
   asyncio.run(check())
   "
   ```

## Deployment

These changes should be deployed following the standard workflow:

1. ✅ **Local** - Develop and test on feature branch (this PR)
2. ⏳ **Develop** - Merge to `develop` → auto-deploy to staging
3. ⏳ **Production** - After staging verification, merge `develop` to `master`

### Staging Verification Checklist

Before promoting to production:

- [ ] Hourly cron runs successfully at :05
- [ ] Chilean sources appear in staging database
- [ ] Classification/download/extract works for Chilean sources
- [ ] Pipeline metrics show Chilean city processing
- [ ] No errors in staging worker logs

## Related Files

- `backend/app/services/ingestion.py` - Contains `ingest_all_countries()`
- `backend/app/services/cities_chile.py` - Chilean city configuration
- `backend/app/tasks/worker.py` - Worker cron configuration
- `.github/workflows/deploy-backend.yml` - Backend CI/CD pipeline
