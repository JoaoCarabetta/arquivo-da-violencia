#!/usr/bin/env python3
"""Build a diverse failure test set from a prod DB copy.

Samples currently-failed sources so we can validate the download/extraction
fixes against varied, representative cases before any mass reprocessing:

  - download failures: spread across distinct publisher domains
  - extraction failures: spread across content-length buckets and publishers
    (article content is already stored, so reruns need no re-fetch)

The script only READS the given SQLite file. Pull a safe copy first, e.g.:

    # on prod
    sqlite3 backend/app/instance/violence.db ".backup '/tmp/violence-copy.db'"
    # then scp /tmp/violence-copy.db locally

Usage:
    python scripts/build_failure_test_set.py \
        --db /tmp/violence-copy.db \
        --download-n 60 --extraction-n 60
"""

from __future__ import annotations

import argparse
import json
import random
import sqlite3
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "failure_test_set.json"


def domain_of(url: str | None) -> str | None:
    if not url:
        return None
    try:
        host = urlparse(url).hostname
        if not host:
            return None
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return None


def length_bucket(n: int) -> str:
    if n < 2000:
        return "short"
    if n <= 10000:
        return "medium"
    return "long"


def _round_robin(groups: dict[str, list], total: int) -> list:
    """Pick up to ``total`` items, one per group per pass, for max diversity."""
    selected: list = []
    pools = {k: list(v) for k, v in groups.items()}
    for pool in pools.values():
        random.shuffle(pool)
    keys = list(pools.keys())
    random.shuffle(keys)
    while len(selected) < total and any(pools.values()):
        for k in keys:
            if not pools[k]:
                continue
            selected.append(pools[k].pop())
            if len(selected) >= total:
                break
    return selected


def sample_download_failures(conn: sqlite3.Connection, n: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT id, headline, resolved_url, google_news_url, publisher_name
        FROM source_google_news
        WHERE status = 'failed_in_download'
        """
    ).fetchall()

    by_domain: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        url = r["resolved_url"] or r["google_news_url"]
        by_domain[domain_of(url) or "unknown"].append(
            {
                "id": r["id"],
                "headline": r["headline"],
                "resolved_url": r["resolved_url"],
                "google_news_url": r["google_news_url"],
                "publisher_name": r["publisher_name"],
                "domain": domain_of(url),
            }
        )

    picked = _round_robin(by_domain, n)
    print(f"  download: {len(rows)} failed across {len(by_domain)} domains -> sampled {len(picked)}")
    return picked


def sample_extraction_failures(conn: sqlite3.Connection, n: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT id, headline, content, published_at, publisher_name, resolved_url
        FROM source_google_news
        WHERE status = 'failed_in_extraction' AND content IS NOT NULL AND content != ''
        """
    ).fetchall()

    by_key: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        content = r["content"] or ""
        bucket = length_bucket(len(content))
        key = f"{bucket}|{r['publisher_name'] or 'unknown'}"
        by_key[key].append(
            {
                "id": r["id"],
                "headline": r["headline"],
                "content": content,
                "content_length": len(content),
                "length_bucket": bucket,
                "published_at": r["published_at"],
                "publisher_name": r["publisher_name"],
                "resolved_url": r["resolved_url"],
            }
        )

    picked = _round_robin(by_key, n)
    buckets = defaultdict(int)
    for p in picked:
        buckets[p["length_bucket"]] += 1
    print(
        f"  extraction: {len(rows)} failed -> sampled {len(picked)} "
        f"(by length: {dict(buckets)})"
    )
    return picked


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a diverse failure test set")
    parser.add_argument("--db", required=True, help="Path to a (copied) SQLite DB to sample from")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Output fixture JSON path")
    parser.add_argument("--download-n", type=int, default=60)
    parser.add_argument("--extraction-n", type=int, default=60)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)

    db_path = Path(args.db)
    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    print(f"Sampling from {db_path} ...")
    download = sample_download_failures(conn, args.download_n)
    extraction = sample_extraction_failures(conn, args.extraction_n)
    conn.close()

    out = {
        "meta": {
            "source_db": str(db_path),
            "seed": args.seed,
            "download_count": len(download),
            "extraction_count": len(extraction),
        },
        "download": download,
        "extraction": extraction,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"Wrote {out_path} ({len(download)} download + {len(extraction)} extraction cases)")


if __name__ == "__main__":
    main()
