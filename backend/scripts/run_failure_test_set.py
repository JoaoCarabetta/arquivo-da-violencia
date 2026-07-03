#!/usr/bin/env python3
"""Run the NEW download/extraction logic against the failure test set (dry-run).

This validates how much the fixes recover and what failure reasons remain, WITHOUT
writing anything to the database. It reuses the exact production fetch + classify +
extraction code paths.

  - download stage: re-fetches each URL with the new httpx client and reports the
    recovered count + remaining reason breakdown. No LLM cost.
  - extraction stage: re-runs the LLM on the stored content (incurs Gemini cost),
    so it is opt-in.

Run from the backend/ directory (so `app` is importable):

    # cheap, no LLM:
    python scripts/run_failure_test_set.py --stages download

    # include extraction (needs OPENROUTER_API_KEY, costs tokens):
    python scripts/run_failure_test_set.py --stages download,extraction
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from pathlib import Path

# Ensure the backend root (which contains the `app` package) is importable
# regardless of the directory this script is launched from.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.services import diagnostics
from app.services.download import _fetch_html, extract_content_and_metadata

DEFAULT_FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "failure_test_set.json"


async def _try_download(case: dict) -> tuple[bool, str | None, int | None]:
    """Returns (success, failure_reason, http_status) for one download case."""
    import httpx

    url = case.get("resolved_url") or case.get("google_news_url")
    if not url:
        return False, diagnostics.NO_URL, None
    try:
        status, html = await _fetch_html(url)
    except Exception as e:
        reason = diagnostics.classify_download_exception(e)
        http_status = e.response.status_code if isinstance(e, httpx.HTTPStatusError) else None
        return False, reason, http_status
    try:
        content, _ = await asyncio.to_thread(extract_content_and_metadata, html)
    except Exception:
        return False, diagnostics.EMPTY_CONTENT, status
    if not content:
        return False, diagnostics.EMPTY_CONTENT, status
    return True, None, status


async def run_download(cases: list[dict], concurrency: int) -> None:
    print(f"\n=== DOWNLOAD: re-fetching {len(cases)} previously-failed URLs ===")
    sem = asyncio.Semaphore(concurrency)

    async def worker(case):
        async with sem:
            return await _try_download(case)

    results = await asyncio.gather(*[worker(c) for c in cases], return_exceptions=True)

    recovered = 0
    reasons: Counter = Counter()
    statuses: Counter = Counter()
    for r in results:
        if isinstance(r, Exception):
            reasons[diagnostics.FETCH_NETWORK_ERROR] += 1
            continue
        ok, reason, status = r
        if ok:
            recovered += 1
        else:
            reasons[reason] += 1
            if status:
                statuses[status] += 1

    total = len(cases)
    print(f"  RECOVERED: {recovered}/{total} ({recovered / total * 100:.1f}%) now succeed")
    print(f"  still failing by reason: {dict(reasons)}")
    if statuses:
        print(f"  failing HTTP statuses: {dict(statuses)}")


def _try_extraction(case: dict) -> tuple[bool, str | None]:
    # Imported lazily so download-only runs don't load the heavy LLM stack.
    from app.services.extraction import extract_event_from_content

    settings = get_settings()
    content = case.get("content") or ""
    if not content:
        return False, diagnostics.EMPTY_EXTRACTION
    if len(content) > settings.extraction_max_chars:
        content = content[: settings.extraction_max_chars]
    metadata = {
        "headline": case.get("headline"),
        "publisher": case.get("publisher_name"),
        "url": case.get("resolved_url"),
        "published_at": case.get("published_at"),
    }
    try:
        extract_event_from_content(content, metadata)
        return True, None
    except Exception as e:
        return False, diagnostics.classify_extraction_exception(e)


async def run_extraction(cases: list[dict], concurrency: int) -> None:
    print(f"\n=== EXTRACTION: re-running LLM on {len(cases)} stored contents (costs tokens) ===")
    sem = asyncio.Semaphore(concurrency)

    async def worker(case):
        async with sem:
            return await asyncio.to_thread(_try_extraction, case)

    results = await asyncio.gather(*[worker(c) for c in cases], return_exceptions=True)

    recovered = 0
    reasons: Counter = Counter()
    for r in results:
        if isinstance(r, Exception):
            reasons[diagnostics.LLM_UNKNOWN] += 1
            continue
        ok, reason = r
        if ok:
            recovered += 1
        else:
            reasons[reason] += 1

    total = len(cases)
    print(f"  RECOVERED: {recovered}/{total} ({recovered / total * 100:.1f}%) now succeed")
    print(f"  still failing by reason: {dict(reasons)}")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Dry-run the fixes against the failure test set")
    parser.add_argument("--fixture", default=str(DEFAULT_FIXTURE))
    parser.add_argument("--stages", default="download", help="Comma list: download,extraction")
    parser.add_argument("--download-concurrency", type=int, default=10)
    parser.add_argument("--extraction-concurrency", type=int, default=5)
    args = parser.parse_args()

    fixture = Path(args.fixture)
    if not fixture.exists():
        raise SystemExit(f"Fixture not found: {fixture}. Run build_failure_test_set.py first.")

    data = json.loads(fixture.read_text())
    stages = {s.strip() for s in args.stages.split(",") if s.strip()}

    print(f"Loaded fixture: {data['meta']}")

    if "download" in stages:
        await run_download(data.get("download", []), args.download_concurrency)
    if "extraction" in stages:
        if not get_settings().openrouter_api_key:
            print("\n[skip] extraction stage requires OPENROUTER_API_KEY")
        else:
            await run_extraction(data.get("extraction", []), args.extraction_concurrency)


if __name__ == "__main__":
    asyncio.run(main())
