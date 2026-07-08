"""Pull a read-only SQLite snapshot from the production API for offline detect."""

from __future__ import annotations

import json
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import Any


def _get_json(url: str, *, retries: int = 4) -> dict[str, Any]:
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "arquivo-eval-improvement/1.0",
                },
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code in (429, 500, 502, 503) and attempt + 1 < retries:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise
        except Exception as e:
            last_err = e
            if attempt + 1 < retries:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise
    raise last_err  # type: ignore[misc]


def _paginate(base_url: str, *, max_pages: int | None = None) -> list[dict]:
    items: list[dict] = []
    page = 1
    while True:
        sep = "&" if "?" in base_url else "?"
        url = f"{base_url}{sep}page={page}&per_page=5"
        data = _get_json(url)
        batch = data.get("items") or []
        if not batch:
            break
        items.extend(batch)
        if page >= data.get("pages", page):
            break
        if max_pages and page >= max_pages:
            break
        page += 1
        time.sleep(0.25)
    return items


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def pull_snapshot(
    *,
    base_url: str,
    output: Path,
    date_from: date,
    date_to: date,
    max_source_pages: int = 30,
) -> dict[str, Any]:
    """Download prod data and write a SQLite file compatible with improvement detect."""
    base_url = base_url.rstrip("/")

    unique_events = _paginate(
        f"{base_url}/api/unique-events?"
        f"date_from={date_from.isoformat()}&date_to={date_to.isoformat()}"
    )
    raw_events = _paginate(
        f"{base_url}/api/raw-events?"
        f"date_from={date_from.isoformat()}&date_to={date_to.isoformat()}"
    )

    # Recent sources (API orders by fetched_at desc); filter client-side to window.
    source_pages = _paginate(f"{base_url}/api/sources", max_pages=max_source_pages)
    window_start = datetime.combine(date_from, datetime.min.time())
    window_end = datetime.combine(date_to, datetime.max.time())
    sources: list[dict] = []
    for row in source_pages:
        fetched = _parse_dt(row.get("fetched_at"))
        if fetched and window_start <= fetched.replace(tzinfo=None) <= window_end:
            sources.append(row)

    if output.exists():
        output.unlink()
    conn = sqlite3.connect(output)
    conn.executescript(
        """
        CREATE TABLE source_google_news (
            id INTEGER PRIMARY KEY,
            headline TEXT,
            content TEXT,
            status TEXT,
            is_violent_death INTEGER,
            updated_at TEXT,
            fetched_at TEXT
        );
        CREATE TABLE raw_event (
            id INTEGER PRIMARY KEY,
            source_google_news_id INTEGER,
            title TEXT,
            event_date TEXT,
            city TEXT,
            state TEXT,
            neighborhood TEXT,
            homicide_type TEXT,
            extraction_success INTEGER,
            extraction_data TEXT,
            deduplication_status TEXT,
            unique_event_id INTEGER,
            chronological_description TEXT,
            victim_count INTEGER,
            created_at TEXT,
            updated_at TEXT
        );
        CREATE TABLE unique_event (
            id INTEGER PRIMARY KEY,
            title TEXT,
            city TEXT,
            state TEXT,
            event_date TEXT,
            neighborhood TEXT,
            needs_enrichment INTEGER,
            source_count INTEGER,
            victim_count INTEGER,
            victims_summary TEXT,
            chronological_description TEXT,
            merged_data TEXT,
            content_class TEXT,
            homicide_type TEXT,
            created_at TEXT,
            updated_at TEXT
        );
        """
    )

    for s in sources:
        conn.execute(
            """
            INSERT INTO source_google_news
            (id, headline, content, status, is_violent_death, updated_at, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                s["id"],
                s.get("headline"),
                s.get("content"),
                s.get("status"),
                1 if s.get("is_violent_death") else 0 if s.get("is_violent_death") is False else None,
                s.get("updated_at"),
                s.get("fetched_at"),
            ),
        )

    for r in raw_events:
        extraction_data = r.get("extraction_data")
        if isinstance(extraction_data, dict):
            extraction_data = json.dumps(extraction_data, ensure_ascii=False)
        conn.execute(
            """
            INSERT INTO raw_event
            (id, source_google_news_id, title, event_date, city, state, neighborhood,
             homicide_type, extraction_success, extraction_data, deduplication_status,
             unique_event_id, chronological_description, victim_count, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                r["id"],
                r.get("source_google_news_id"),
                r.get("title"),
                (r.get("event_date") or "")[:10] or None,
                r.get("city"),
                r.get("state"),
                r.get("neighborhood"),
                r.get("homicide_type"),
                1 if r.get("extraction_success") else 0,
                extraction_data,
                r.get("deduplication_status"),
                r.get("unique_event_id"),
                r.get("chronological_description"),
                r.get("victim_count"),
                r.get("created_at"),
                r.get("updated_at"),
            ),
        )

    seen_ue: set[int] = set()
    for ue in unique_events:
        if ue["id"] in seen_ue:
            continue
        seen_ue.add(ue["id"])
        merged = ue.get("merged_data")
        if isinstance(merged, dict):
            merged = json.dumps(merged, ensure_ascii=False)
        conn.execute(
            """
            INSERT INTO unique_event
            (id, title, city, state, event_date, neighborhood, needs_enrichment,
             source_count, victim_count, victims_summary, chronological_description,
             merged_data, content_class, homicide_type, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ue["id"],
                ue.get("title"),
                ue.get("city"),
                ue.get("state"),
                (ue.get("event_date") or "")[:10] or None,
                ue.get("neighborhood"),
                1 if ue.get("needs_enrichment") else 0,
                ue.get("source_count") or 0,
                ue.get("victim_count"),
                ue.get("victims_summary"),
                ue.get("chronological_description"),
                merged,
                ue.get("content_class"),
                ue.get("homicide_type"),
                ue.get("created_at"),
                ue.get("updated_at"),
            ),
        )

    conn.commit()
    conn.close()

    return {
        "base_url": base_url,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "unique_events": len(unique_events),
        "raw_events": len(raw_events),
        "sources_in_window": len(sources),
        "output": str(output),
    }
