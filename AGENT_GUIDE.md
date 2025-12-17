# Agent Guide - Arquivo da Violencia

This document provides context for AI agents working on this repository.

## Project Overview
**Goal**: Track violence (specifically murders) in Rio de Janeiro using news articles and social media.
**Current State**:
- Fetches news from Google News RSS.
- Resolves encrypted Google News URLs.
- Extracts content and matches keywords ("tiroteio", "homicídio", etc.).
- Stores data in SQLite.
- Displays a simple list of incidents in a Flask web app.

## Tech Stack
- **Language**: Python 3.11+
- **Manager**: `uv`
- **Web**: Flask, Jinja2
- **Database**: SQLite, SQLAlchemy
- **Crawler**: `feedparser`, `trafilatura`, `googlenewsdecoder`
- **CLI**: `click`

## Directory Structure
```text
arquivo-da-violencia/
├── app/
│   ├── __init__.py          # App Factory
│   ├── models.py            # DB Models (Source, ExtractedEvent, Incident)
│   ├── routes.py            # Web Routes
│   ├── templates/           # HTML Templates
│   └── services/            # Core Logic (The Pipeline)
│       ├── ingestion.py     # Stage 1: RSS -> Source
│       ├── extraction.py    # Stage 2: Content/Keywords -> ExtractedEvent
│       └── enrichment.py    # Stage 3: Link -> Incident
├── scripts/
│   ├── ingest_data.py       # Manual Data Entry CLI
│   ├── run_crawler.py       # Legacy/Debug Crawler Script
│   ├── migrate_db.py        # Database Migration Helper
│   └── debug/               # Debugging scripts
├── manage.py                # Main CLI Orchestrator
├── run.py                   # Web Server Entry Point
└── instance/
    └── violence.db          # SQLite Database
```

## Data Pipeline
The data ingestion follows a 3-stage pipeline orchestrated by `manage.py`:

1.  **Ingestion (`manage.py fetch`)**:
    - Reads Google News RSS.
    - Creates `Source` records with `status='pending'`.
2.  **Extraction (`manage.py extract`)**:
    - Resolves `news.google.com` URLs to original publisher URLs.
    - Downloads HTML/Text using `trafilatura`.
    - Checks for keywords (stored in `Keyword` table).
    - Creates `ExtractedEvent` if matches found.
3.  **Enrichment (`manage.py enrich`)**:
    - (Future) Deduplicates events.
    - (Future) Links extractions to `Incident` records.

## Key Commands
*   **Run Web Server**: `uv run run.py` (http://127.0.0.1:5000)
*   **Run Full Pipeline**: `uv run manage.py run-all`
*   **Run Full Pipeline (Force Update)**: `uv run manage.py run-all --force`
*   **Manual Data Entry**: `uv run scripts/ingest_data.py --help`

## Database Models (`app/models.py`)
*   `Source`: Raw URL entry. Has `url`, `resolved_url`, `content`, `status`.
*   `ExtractedEvent`: A potential incident found in a source. Has `confidence_score`, `summary`.
*   `Incident`: A canonical, confirmed event (e.g. "Murder in Copacabana"). Linked to multiple extractions.
*   `Keyword`: Terms used to filter news (e.g. "baleado", "tiroteio").
