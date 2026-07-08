"""Content download service.

Fetches article HTML with an explicit httpx client (browser-like User-Agent,
timeout, redirects) so we (a) get past most anti-bot blocks and (b) capture the
HTTP status code, then extracts the main text with trafilatura. Every attempt is
logged to ``pipeline_attempt`` with a classified failure reason.

After a successful fetch, a content gate (heuristic + LLM) may discard aggregate
or foreign articles before extraction (AQV-32).
"""

from __future__ import annotations

import enum

import httpx
import trafilatura
from loguru import logger

from app.config import get_settings
from app.database import async_session_maker
from app.services import diagnostics
from app.services.classification import (
    classify_article_content,
    format_content_gate_reasoning,
    passes_content_gate,
)
from app.services.content_filters import HeuristicMatch, apply_content_heuristics


class DownloadOutcome(str, enum.Enum):
    """Result of downloading and gating a source."""

    ready_for_extraction = "ready_for_extraction"
    discarded = "discarded"
    failed = "failed"


def extract_content_and_metadata(html: str) -> tuple[str | None, dict | None]:
    """
    Extract main content and metadata from HTML using trafilatura.
    
    Args:
        html: Raw HTML content
    
    Returns:
        Tuple of (content, metadata)
    """
    # Extract main content
    content = trafilatura.extract(
        html,
        include_comments=False,
        include_tables=True,
        no_fallback=False,
        favor_precision=True,
    )
    
    # Extract metadata
    metadata = None
    try:
        meta_result = trafilatura.extract(
            html,
            output_format="json",
            include_comments=False,
        )
        if meta_result:
            import json
            metadata = json.loads(meta_result)
    except Exception as e:
        logger.debug(f"Failed to extract metadata: {e}")
    
    return content, metadata


async def _fetch_html(url: str) -> tuple[int, str]:
    """Fetch a URL with a browser-like client.

    Returns (status_code, html). Raises ``httpx.HTTPStatusError`` for non-2xx
    responses and other ``httpx`` errors for transport failures, so the caller
    can classify the reason.
    """
    settings = get_settings()
    headers = {
        "User-Agent": settings.download_user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    }
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=settings.download_timeout_seconds,
        headers=headers,
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.status_code, response.text


def _heuristic_failure_reason(match: HeuristicMatch) -> str:
    if match.hint == "aggregate_statistics":
        return diagnostics.AGGREGATE_CONTENT
    if match.hint == "foreign":
        return diagnostics.FOREIGN_CONTENT
    return diagnostics.NON_INCIDENT_CONTENT


async def _discard_after_content_gate(
    *,
    source_id: int,
    reasoning: str,
    failure_reason: str,
    failure_detail: str,
    content_length: int,
    duration_ms: int,
    attempt_number: int,
) -> DownloadOutcome:
    from sqlalchemy import text

    async with async_session_maker() as session:
        await session.execute(
            text("""
                UPDATE source_google_news
                SET status = 'discarded',
                    classification_reasoning = :reasoning,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
            """),
            {"id": source_id, "reasoning": reasoning[:500]},
        )
        await session.commit()

    await diagnostics.record_attempt(
        stage=diagnostics.STAGE_CONTENT_GATE,
        outcome=diagnostics.OUTCOME_DISCARDED,
        source_google_news_id=source_id,
        failure_reason=failure_reason,
        failure_detail=failure_detail,
        content_length=content_length,
        duration_ms=duration_ms,
        attempt_number=attempt_number,
    )
    return DownloadOutcome.discarded


async def _apply_content_gate(
    *,
    source_id: int,
    headline: str | None,
    content: str,
    gate_started: float,
    attempt_number: int,
) -> DownloadOutcome:
    """Run heuristic + LLM gate. Returns ready_for_extraction or discarded."""
    import asyncio
    import time

    content_length = len(content)
    heuristic = apply_content_heuristics(headline, content)
    if heuristic:
        duration_ms = int((time.monotonic() - gate_started) * 1000)
        reasoning = (
            f"Heuristic content filter ({heuristic.rule}): {heuristic.detail} "
            f"[content_gate=heuristic, hint={heuristic.hint}]"
        )
        logger.info(
            f"Source {source_id}: content gate HEURISTIC discard ({heuristic.rule})"
        )
        return await _discard_after_content_gate(
            source_id=source_id,
            reasoning=reasoning,
            failure_reason=_heuristic_failure_reason(heuristic),
            failure_detail=heuristic.detail,
            content_length=content_length,
            duration_ms=duration_ms,
            attempt_number=attempt_number,
        )

    try:
        classification = await asyncio.to_thread(
            classify_article_content,
            headline or "",
            content,
        )
    except Exception as e:
        duration_ms = int((time.monotonic() - gate_started) * 1000)
        logger.error(f"Content gate LLM failed for source {source_id}: {e}")
        await diagnostics.record_attempt(
            stage=diagnostics.STAGE_CONTENT_GATE,
            outcome=diagnostics.OUTCOME_FAILURE,
            source_google_news_id=source_id,
            failure_reason=diagnostics.LLM_UNKNOWN,
            failure_detail=str(e),
            content_length=content_length,
            duration_ms=duration_ms,
            attempt_number=attempt_number,
        )
        # On LLM failure, allow extraction rather than blocking the pipeline.
        return DownloadOutcome.ready_for_extraction

    duration_ms = int((time.monotonic() - gate_started) * 1000)

    if passes_content_gate(classification):
        await diagnostics.record_attempt(
            stage=diagnostics.STAGE_CONTENT_GATE,
            outcome=diagnostics.OUTCOME_SUCCESS,
            source_google_news_id=source_id,
            content_length=content_length,
            duration_ms=duration_ms,
            attempt_number=attempt_number,
        )
        return DownloadOutcome.ready_for_extraction

    reasoning = format_content_gate_reasoning(classification, method="llm")
    logger.info(f"Source {source_id}: content gate LLM discard")
    return await _discard_after_content_gate(
        source_id=source_id,
        reasoning=reasoning,
        failure_reason=diagnostics.LLM_CONTENT_REJECT,
        failure_detail=classification.reasoning,
        content_length=content_length,
        duration_ms=duration_ms,
        attempt_number=attempt_number,
    )


async def download_source_content(source_id: int) -> DownloadOutcome:
    """
    Download and extract content for a single source.

    Args:
        source_id: ID of the SourceGoogleNews to process

    Returns:
        DownloadOutcome indicating extraction readiness, discard, or failure
    """
    import asyncio
    import time
    from sqlalchemy import text

    # Step 1: read the target URL in a short-lived session, then release the
    # connection so we don't hold it during the (slow) network fetch.
    async with async_session_maker() as session:
        result = await session.execute(
            text(
                "SELECT resolved_url, google_news_url, headline "
                "FROM source_google_news WHERE id = :id"
            ),
            {"id": source_id},
        )
        row = result.fetchone()

        if not row:
            logger.warning(f"Source {source_id} not found")
            return DownloadOutcome.failed

        # Use resolved URL if available, otherwise the Google News URL
        target_url = row[0] or row[1]
        headline = row[2]

    attempt_number = await diagnostics.count_attempts(source_id, diagnostics.STAGE_DOWNLOAD) + 1
    url_domain = diagnostics.domain_of(target_url)

    async def _mark_failed(reason: str, detail: str | None, http_status: int | None, duration_ms: int):
        async with async_session_maker() as session:
            await session.execute(
                text("""
                    UPDATE source_google_news 
                    SET status = 'failed_in_download', updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                """),
                {"id": source_id}
            )
            await session.commit()
        await diagnostics.record_attempt(
            stage=diagnostics.STAGE_DOWNLOAD,
            outcome=diagnostics.OUTCOME_FAILURE,
            source_google_news_id=source_id,
            failure_reason=reason,
            failure_detail=detail,
            http_status=http_status,
            url_domain=url_domain,
            duration_ms=duration_ms,
            attempt_number=attempt_number,
        )

    if not target_url:
        await _mark_failed(diagnostics.NO_URL, "Source has no resolved or google_news URL", None, 0)
        return DownloadOutcome.failed

    logger.info(f"Downloading content from: {target_url[:80]}...")

    # Step 2: fetch over the network, then extract off the event loop. Neither
    # step holds a DB connection.
    started = time.monotonic()
    try:
        status_code, html = await _fetch_html(target_url)
    except Exception as e:
        duration_ms = int((time.monotonic() - started) * 1000)
        reason = diagnostics.classify_download_exception(e)
        http_status = e.response.status_code if isinstance(e, httpx.HTTPStatusError) else None
        logger.warning(f"Fetch failed for source {source_id} ({reason}): {e}")
        await _mark_failed(reason, str(e), http_status, duration_ms)
        return DownloadOutcome.failed

    try:
        content, metadata = await asyncio.to_thread(extract_content_and_metadata, html)
    except Exception as e:
        duration_ms = int((time.monotonic() - started) * 1000)
        logger.error(f"Error extracting content for source {source_id}: {e}")
        await _mark_failed(diagnostics.EMPTY_CONTENT, str(e), status_code, duration_ms)
        return DownloadOutcome.failed

    duration_ms = int((time.monotonic() - started) * 1000)

    if not content:
        # Fetched fine (HTTP 2xx) but trafilatura found no article text. This is a
        # parser/content problem, not a transport failure - record it as such.
        logger.warning(f"No content extracted from: {target_url}")
        await _mark_failed(diagnostics.EMPTY_CONTENT, "trafilatura returned no content", status_code, duration_ms)
        return DownloadOutcome.failed

    gate_started = time.monotonic()
    gate_attempt = (
        await diagnostics.count_attempts(source_id, diagnostics.STAGE_CONTENT_GATE) + 1
    )
    gate_outcome = await _apply_content_gate(
        source_id=source_id,
        headline=headline,
        content=content,
        gate_started=gate_started,
        attempt_number=gate_attempt,
    )

    if gate_outcome == DownloadOutcome.discarded:
        logger.info(
            f"Downloaded {len(content)} chars for source {source_id}, discarded by content gate"
        )
        return DownloadOutcome.discarded

    # Step 3: persist the content in a fresh short-lived session.
    async with async_session_maker() as session:
        await session.execute(
            text("""
                UPDATE source_google_news 
                SET content = :content, status = 'ready_for_extraction', updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
            """),
            {"id": source_id, "content": content}
        )
        await session.commit()

    await diagnostics.record_attempt(
        stage=diagnostics.STAGE_DOWNLOAD,
        outcome=diagnostics.OUTCOME_SUCCESS,
        source_google_news_id=source_id,
        http_status=status_code,
        url_domain=url_domain,
        content_length=len(content),
        duration_ms=duration_ms,
        attempt_number=attempt_number,
    )

    logger.info(f"Downloaded {len(content)} chars for source {source_id}")
    return DownloadOutcome.ready_for_extraction


async def download_classified_sources(limit: int = 50, concurrency: int = 10) -> dict:
    """
    Download content for all sources that passed classification (in parallel).
    
    Args:
        limit: Maximum number of sources to process
        concurrency: Maximum number of parallel downloads
    
    Returns:
        Dict with download statistics
    """
    import asyncio
    from sqlalchemy import text
    
    async with async_session_maker() as session:
        # Get sources ready for download (passed classification)
        # Use raw SQL to avoid SQLAlchemy enum caching issues
        result = await session.execute(
            text("""
                SELECT id FROM source_google_news 
                WHERE status = 'ready_for_download' 
                AND resolved_url IS NOT NULL 
                LIMIT :limit
            """),
            {"limit": limit}
        )
        candidate_ids = [row[0] for row in result.fetchall()]
        
        if not candidate_ids:
            logger.info(f"Found 0 classified sources to download")
            return {
                "processed": 0,
                "successful": 0,
                "discarded": 0,
                "failed": 0,
            }
        
        # Atomically claim these sources by updating status to prevent race conditions
        await session.execute(
            text("""
                UPDATE source_google_news 
                SET status = 'downloading', updated_at = CURRENT_TIMESTAMP
                WHERE id IN ({}) AND status = 'ready_for_download'
            """.format(",".join(str(id) for id in candidate_ids)))
        )
        await session.commit()
        
        # Get the IDs we actually claimed
        result = await session.execute(
            text("""
                SELECT id FROM source_google_news 
                WHERE id IN ({}) AND status = 'downloading'
            """.format(",".join(str(id) for id in candidate_ids)))
        )
        source_ids = [row[0] for row in result.fetchall()]
    
    logger.info(f"Claimed {len(source_ids)} sources for download")
    
    if not source_ids:
        return {
            "processed": 0,
            "successful": 0,
            "discarded": 0,
            "failed": 0,
        }
    
    # Semaphore to limit concurrency
    semaphore = asyncio.Semaphore(concurrency)
    
    async def download_with_limit(source_id: int):
        async with semaphore:
            return await download_source_content(source_id)
    
    # Run downloads in parallel with concurrency limit
    logger.info(f"Starting parallel download with concurrency={concurrency}")
    results = await asyncio.gather(
        *[download_with_limit(sid) for sid in source_ids],
        return_exceptions=True
    )
    
    successful = 0
    discarded = 0
    failed = 0
    
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Download failed with exception: {result}")
            failed += 1
        elif result == DownloadOutcome.ready_for_extraction:
            successful += 1
        elif result == DownloadOutcome.discarded:
            discarded += 1
        else:
            failed += 1
    
    logger.info(
        f"Download complete: {successful} ready for extraction, "
        f"{discarded} discarded by content gate, {failed} failed"
    )
    
    return {
        "processed": len(source_ids),
        "successful": successful,
        "discarded": discarded,
        "failed": failed,
    }
