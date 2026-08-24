# Adding a Country to Arquivo da Violência

**Canonical agent playbook for multi-country expansion.**

This document describes the complete pipeline work required to add a new country to Arquivo da Violência. Ingest-only PRs are not sufficient—the entire pipeline from Google News RSS to public API must handle the new country.

## Definition of Done

A country is **ready on STAGING** when:

1. ✅ **Unique events exist** with `UniqueEvent.country = {ISO alpha-2}` after a full live pipeline cycle: ingest → classify → extract → enrich → dedup → geocode
2. ✅ **Public API returns them**: `GET /api/events?country={XX}` returns the new country's events
3. ✅ **Geocoding works**: Events have correct coordinates in the new country (not Brazilian coordinates)
4. ✅ **Counts are non-zero**: Staging proof counts show at least some events made it through all layers

**Critical rule**: Do NOT start country N+1 while country N still has 0 unique events on staging. The pipeline must prove it works end-to-end before adding more countries.

Do NOT call the country "production-ready" until staging verification is complete. Only after staging is proven should the code be merged to `master` and deployed to production.

## Canonical Codes and Conventions

### Country Codes

- **Use ISO 3166-1 alpha-2** everywhere in the data pipeline: `BR`, `CL`, `AR`, etc.
- Codes flow through: `SourceGoogleNews.country` → `RawEvent.country` → `UniqueEvent.country`
- **Display names** (Brasil, Chile, Argentina) are **UI-only**. The backend stores and filters by ISO codes.
- **Legacy support**: Old data may have `country="Brasil"` instead of `"BR"`. Filters must handle both formats.

### Taxonomy Slugs

- **Taxonomy slugs stay Portuguese** even when the news language is Spanish or another language.
- Event families (`homicidio`, `latrocinio`, `feminicidio`), subtypes (`simples`, `chacina`, `policial`), and content classes (`incident`, `statistics`, `foreign_death`) remain in Portuguese across all countries.
- This keeps the taxonomy consistent and avoids translation mismatches.

### Display Names

- Display names are localized per country: `COUNTRY_NAMES = {"BR": "Brasil", "CL": "Chile"}` in `backend/app/geography.py`
- The frontend can show localized names, but the API and database use ISO codes.

## Pipeline Layers: The 8 Brazil-Locks

Each layer below is a **Brazil-lock until you modify it**. Adding ingest config alone (layer 2) is not enough. All 8 layers must be touched.

### Layer 1: Geography Configuration

**File**: `backend/app/geography.py`

- Add the country code to the `Country` type literal: `Country = Literal["BR", "CL", "AR"]`
- Add to `COUNTRIES` list: `COUNTRIES: list[Country] = ["BR", "CL", "AR"]`
- Add display name: `COUNTRY_NAMES = {"BR": "Brasil", "CL": "Chile", "AR": "Argentina"}`
- Define regions/states for the new country (e.g., `ARGENTINIAN_PROVINCES`)
- Implement `get_regions_for_country()` branch for the new country
- Add major cities list (if using city-level geography)

**Tests**: Write a fixture that references the new country code (e.g., `test_geography.py` checking region lookup).

### Layer 2: Ingest Configuration

**Files**: `backend/app/services/cities_{country}.py`, `backend/app/services/ingestion.py`

**Create `cities_{country}.py`** (e.g., `cities_argentina.py`):
- Major cities list (200k+ population + all regional/provincial capitals)
- Format: `"City Region"` for Google News queries
- News source domains for query sharding (when a city hits 100 results)
- Google News RSS params: `hl` (language), `gl` (country), `ceid` (edition)
  - Example: `{"hl": "es-AR", "gl": "AR", "ceid": "AR:es-419"}`
- Local homicide/violence query terms in the country's language
  - Example for Spanish: `["homicidio", "asesinato", "balacera", "tiroteo"]`

**Update `ingestion.py`**:
- Import the new city/source/params modules
- Add country branch to `build_rss_url()` for country-specific Google News params
- Update `ingest_all_countries()` to include the new country

**Critical trap**: Explicit city lists currently default to Brazil. When calling `ingest_all_cities(cities=[...])` with a hardcoded list, you MUST pass `country="XX"` or it will use Brazilian parameters and sources.

**Hourly cron behavior**: `ingest_cities_task(cities=None)` must call `ingest_all_countries()` to ingest ALL configured countries, not just Brazil. This is the production hourly path.

**Tests**: Write a test that calls `ingest_all_cities(country="XX")` and verifies it uses the correct Google News params and query terms.

### Layer 3: Persist Country Through the Pipeline

**Files**: `backend/app/models/unique_event.py`, `backend/app/services/*.py`

**Problem**: `UniqueEvent.country` has a default value of `"Brasil"`. This is a Brazil-lock.

**Solution**:
- When creating `RawEvent` from `SourceGoogleNews`, copy `source.country` to `raw.country`
- When creating `UniqueEvent` from `RawEvent`, copy `raw.country` to `unique.country`
- **Never hardcode `"Brasil"` or `"BR"`** when creating pipeline records

**Files to check**:
- `backend/app/services/classification.py` — when creating `RawEvent`
- `backend/app/services/deduplication.py` — when creating `UniqueEvent`
- `backend/app/services/enrichment.py` — when updating `UniqueEvent`

**Tests**: Create a fixture with `country="CL"` at the source level and verify it flows through to `UniqueEvent.country` after classification and dedup.

### Layer 4: Classifier + Content-Gate

**Files**: `backend/app/services/classification.py`, `backend/app/services/content_filters.py`

The classifier and content-gate use LLM prompts and heuristics to determine if an article is about a violent death. These are Brazil-specific by default.

**Required changes**:

1. **In-language prompts**: Write or adapt prompts in the country's language (Spanish for Chile/Argentina, Portuguese for Brazil)
   - Classification prompt: "Is this article about a violent death?"
   - Content-gate prompt: "Does this article describe a specific incident?"

2. **Police/security force names**: Add the country's police force names to heuristics
   - Brazil: "PM", "Polícia Militar", "Polícia Civil"
   - Chile: "Carabineros", "PDI" (Policía de Investigaciones)
   - Argentina: "Policía Federal", "Policía Bonaerense", etc.

3. **Remove country from foreign death denylists**: Articles about Chilean deaths should not be classified as `foreign_death` when the source is Chilean
   - Update the foreign death heuristic to check `if article.country != "CL" and "Chile" in headline: foreign_death`

4. **Remove country from earthquake/disaster denylists**: If the heuristic rejects earthquakes, don't reject Chilean earthquake articles when `country == "CL"`

5. **Accept-Language header for downloads**: When downloading full article HTML, send `Accept-Language: es-CL` for Chilean ccTLDs to get Spanish content

**Tests**:
- Heuristic test: A Chilean article with "Carabineros disparo" should be classified as violent death, not foreign
- Content-gate test: A Chilean incident article should pass content-gate with Spanish prompts
- Foreign death test: An article from Brazil about a Chilean tourist death should be `foreign_death`, but a Chilean article about a Chilean death should not

### Layer 5: Extraction (Language Detection + Prompt Switching)

**Files**: `backend/app/services/extraction.py`

The extraction stage uses LLM prompts to extract structured data (victim count, location, date, etc.) from article text. The prompts are in Portuguese by default.

**Required changes**:

1. **Language detection**: Detect the article's language from `UniqueEvent.country` or the raw text
   - Brazil → Portuguese prompts
   - Chile/Argentina → Spanish prompts

2. **Language-specific system prompts**: Write or adapt extraction prompts in the country's language
   - Spanish prompt: "Extrae la siguiente información del artículo: víctimas, ubicación, fecha..."
   - Portuguese prompt: "Extraia as seguintes informações do artigo: vítimas, localização, data..."

3. **Don't leave PT-only field copy on non-PT path**: If the extraction code copies default text like `"Dados não disponíveis"` for missing fields, make sure this text is translated or removed for non-Portuguese articles

**Tests**: Extract from a Spanish-language Chilean article and verify the extraction uses Spanish prompts and returns correct structured data.

### Layer 6: Enrich + Dedup Must Keep Country

**Files**: `backend/app/services/enrichment.py`, `backend/app/services/deduplication.py`

Enrichment adds missing fields and merges duplicate events. Dedup must not lose the country field.

**Required changes**:
- When merging `RawEvent` → `UniqueEvent`, ensure `country` is preserved
- When enriching a `UniqueEvent`, do not overwrite `country` with a default value

**Tests**: Create two `RawEvent` records for the same Chilean incident. After dedup, verify `UniqueEvent.country == "CL"` and not `"Brasil"`.

### Layer 7: Geocoding (Region, Language, Country Codes)

**Files**: `backend/app/services/geocoding.py`

Geocoding converts city/neighborhood names to lat/lon coordinates. The geocoder is Brazil-specific by default.

**Required changes**:

1. **Region/language/country codes for Google Maps API**:
   - Pass `region="cl"` and `language="es"` to Google Maps API for Chilean locations
   - Pass `region="br"` and `language="pt"` for Brazilian locations
   - Pass `components="country:CL"` to restrict results to Chile

2. **Remove Brazil-only geocoding services**: ViaCEP is a Brazilian ZIP code API. Do not call it for non-Brazilian addresses.

3. **City name disambiguation**: If a city name exists in both Brazil and the new country (e.g., "Santiago" in Brazil and Chile), use the country code to disambiguate
   - Query: `"Santiago, Chile"` with `components="country:CL"`
   - Not: `"Santiago"` (may return Brazilian Santiago)

**Tests**:
- Geocode a Chilean city and verify lat/lon are in Chile (not Brazil)
- Geocode a city name that exists in both countries (e.g., "Santiago") with `country="CL"` and verify it returns Chilean coordinates
- Verify ViaCEP is not called for Chilean addresses

### Layer 8: Public API Filter + No Fake Brazilian UF

**Files**: `backend/app/routers/public.py`, `backend/app/routers/unique_events.py`

The public API must support filtering by country and not assign fake Brazilian state codes to foreign cities.

**Required changes**:

1. **Country filter**: `GET /api/events?country=CL` must filter `UniqueEvent.country == "CL"`
   - Legacy support: `?country=Brasil` should be treated as `?country=BR`

2. **Region filter**: `GET /api/events?region=Metropolitana` should work for Chilean regions
   - Do NOT assign a fake Brazilian UF (e.g., `state="SP"`) to Chilean cities

3. **Frontend display**: The frontend map and filters must show Chilean regions, not Brazilian states, when `country="CL"`

**Tests**:
- `GET /api/events?country=CL` returns only Chilean events
- `GET /api/events?country=CL&region=Metropolitana` returns only Santiago Metropolitan Region events
- Chilean events do NOT have a Brazilian state code (`state` should be `null` or a Chilean region)

## Testing at Seams

Write tests at pipeline layer boundaries. Do NOT mock full LLM calls for every test. Focus on data flow and heuristics.

**Test checklist**:
1. ✅ **Persist country fixture**: Create a `SourceGoogleNews(country="CL")` → verify `UniqueEvent.country == "CL"` after full pipeline
2. ✅ **Heuristic violent death vs foreign**: Chilean article with "Carabineros" should be classified as violent, not foreign
3. ✅ **Content-gate**: Spanish-language incident article should pass content-gate
4. ✅ **Geocode region disambiguation**: Geocode "Santiago" with `country="CL"` should return Chilean coordinates, not Brazilian
5. ✅ **Public filter**: `GET /api/events?country=CL` returns only Chilean events

## Staging Proof Counts

After deploying to staging (`develop` branch), report the following metrics to verify the pipeline works end-to-end:

1. **New sources ingested** (last 24h): `SELECT COUNT(*) FROM source_google_news WHERE country='CL' AND created_at > NOW() - INTERVAL '24 hours'`
2. **Discarded vs extracted**: How many articles were classified as violent death? How many passed content-gate?
3. **Unique events by country**: `SELECT country, COUNT(*) FROM unique_event GROUP BY country`
4. **Geocoded share**: What % of Chilean unique events have `latitude IS NOT NULL`?
5. **Sample headline**: Show 1-2 sample Chilean headlines that made it to `UniqueEvent` to prove the pipeline works

**How to interpret 0 unique events**:
- **0 unique but many sources ingested**: Classifier or content-gate is rejecting everything (check prompts and heuristics)
- **0 unique and country still `"Brasil"`**: Persist country layer is broken (check `RawEvent` and `UniqueEvent` creation)
- **Unique events exist but coords in Brazil**: Geocoding layer is broken (check region/language/country params)

**Do NOT promote to production** until staging proof counts are healthy and the public API returns correct Chilean events.

## Rates Per 100k and Official Stats Overlay

**These are OUT OF THE CRITICAL PATH.**

- Counts-only pipeline is sufficient to launch the country
- Rates per 100k require a population data source (IBGE for Brazil, INE for Chile, INDEC for Argentina)
- Official stats overlay (Anuário, SIM, CPHDV for Brazil; Subsecretaría de Prevención del Delito for Chile) is a later enhancement

**Do NOT** mix official stats (e.g., annual homicide counts from government reports) into the news nowcast pipeline. They serve different purposes:
- **News nowcast**: Real-time counts from Google News (this pipeline)
- **Official stats**: Annual/monthly aggregates from government sources (separate overlay)

## Worked Example: Chile

Chile was added in PRs #119–#121 (ingest-only), but this was **not sufficient** to make Chile production-ready. The following additional PRs were required:

- **#128 Persist country**: Fixed `RawEvent` and `UniqueEvent` creation to copy `country` instead of hardcoding `"Brasil"`
- **#129 Classifier + content-gate**: Added Spanish prompts, Carabineros heuristics, removed Chile from foreign death denylist
- **#131 Geocode**: Added Chilean region codes, Google Maps `region="cl"` param, city disambiguation

**Production is still Brazil-locked on classifier** until #129 is merged to `master`. Staging (`develop`) has the fixes, but production (`master`) does not.

**Lesson**: Ingest-only PRs are not enough. All 8 pipeline layers must be modified to make the country production-ready.

## Config vs Hardcoded Branches

When adding the **third country** (e.g., Argentina after Brazil and Chile), prefer a **country config dictionary** over copying `if country == "CL"` branches everywhere.

**Example config**:
```python
COUNTRY_CONFIGS = {
    "BR": {
        "google_news_params": {"hl": "pt-BR", "gl": "BR", "ceid": "BR:pt-419"},
        "language": "pt",
        "geocode_region": "br",
        "query_terms": ["homicídio", "assassinato", "tiroteio"],
        "police_forces": ["PM", "Polícia Militar", "Polícia Civil"],
    },
    "CL": {
        "google_news_params": {"hl": "es-CL", "gl": "CL", "ceid": "CL:es-419"},
        "language": "es",
        "geocode_region": "cl",
        "query_terms": ["homicidio", "asesinato", "balacera"],
        "police_forces": ["Carabineros", "PDI"],
    },
}
```

Then code branches become:
```python
config = COUNTRY_CONFIGS[country]
google_params = config["google_news_params"]
```

This is cleaner than:
```python
if country == "BR":
    google_params = BRAZIL_PARAMS
elif country == "CL":
    google_params = CHILE_PARAMS
elif country == "AR":
    google_params = ARGENTINA_PARAMS
```

## Deploy Flow and Verification

Always follow: **local → develop (staging) → master (prod)**.

### Step 1: Local Docker Testing
- Start dev stack: `docker compose -f docker-compose.dev.yml -f docker-compose.dev.override.yml up -d --build`
- Trigger manual ingest: `curl -X POST "http://localhost:8010/api/pipeline/ingest-cities?when=1h"`
- Verify new country sources in logs: `docker compose -f docker-compose.dev.yml logs -f worker`
- Check database: Sources, raw events, and unique events with `country={XX}`

### Step 2: Deploy to Staging (develop branch)
- Merge to `develop` branch
- CI/CD builds `:develop` Docker images and deploys to staging (`staging-arquivo-*` containers)
- Staging API: `https://staging.arquivodaviolencia.com.br` (port 8001 internally)

**Staging verification checklist**:
- [ ] Hourly cron runs successfully (check staging worker logs)
- [ ] New country sources appear in staging database
- [ ] Classification/download/extract works for new country sources
- [ ] `UniqueEvent.country` is correct (ISO alpha-2, not "Brasil")
- [ ] Geocoded coordinates are in the new country (not Brazil)
- [ ] `GET /api/events?country={XX}` returns new country events
- [ ] Sample headlines look correct (violent deaths, not foreign/earthquake articles)
- [ ] No errors in staging worker logs

**Verify worker image SHA**: Confirm the staging worker container is running the commit you just pushed, not an old image. Check `docker ps` and `docker inspect` on the staging server.

### Step 3: Promote to Production (master branch)
- After staging verification is complete, merge `develop` to `master`
- CI/CD builds `:latest` Docker images and deploys to production (`arquivo-*` containers)
- Production API: `https://arquivodaviolencia.com.br` (port 8000 internally)
- After production deploy, the production database is synced to staging (staging gets a copy of prod data)

**Production verification**:
- [ ] Hourly cron runs successfully (check production worker logs)
- [ ] New country events appear in production database
- [ ] Public website shows new country events: `https://arquivodaviolencia.com.br?country={XX}`
- [ ] No errors in production worker logs

## Summary: What Makes a Country Production-Ready?

A country is **not production-ready** until:

1. ✅ All 8 pipeline layers are modified (not just ingest)
2. ✅ Staging has `UniqueEvent.country = {ISO alpha-2}` records after a full live cycle
3. ✅ Staging public API returns new country events (`?country={XX}`)
4. ✅ Geocoded coordinates are in the new country (not Brazil)
5. ✅ Staging proof counts are healthy (non-zero unique events, reasonable geocoded %)
6. ✅ Tests cover the seams (persist country, heuristics, geocode disambiguation)

**Do NOT:**
- Start country N+1 while country N has 0 unique events on staging
- Call ingest-only PRs "done" (they are not)
- Deploy straight to production without staging verification

This playbook is agent-executable. Follow it step-by-step when adding Argentina, Colombia, or any other country.
