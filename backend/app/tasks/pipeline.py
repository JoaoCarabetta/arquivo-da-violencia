"""Pipeline task definitions for ARQ."""

import functools
import time
from typing import Any, Callable

from loguru import logger

from app.metrics import CRON_TASKS, record_cron_outcome, record_task_outcome
from app.services.github import create_failure_issue
from app.services.telegram import (
    notify_job_started,
    notify_job_finished,
    notify_job_failed,
    notify_pipeline_summary,
)


def notify_on_failure(task_name: str):
    """
    Decorator that sends Telegram notification and creates GitHub issue on task failure.
    
    Args:
        task_name: Name of the task for the notification
    
    Usage:
        @notify_on_failure("my_task")
        async def my_task(ctx: dict, ...) -> dict:
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            start = time.monotonic()
            outcome: str | None = None
            try:
                result = await func(*args, **kwargs)
                outcome = "success"
                return result
            except Exception as e:
                outcome = "failure"
                # Extract context details from args/kwargs for the notification
                details = {}
                
                # Try to extract common parameters
                if "source_id" in kwargs:
                    details["source_id"] = kwargs["source_id"]
                elif len(args) > 1 and isinstance(args[1], int):
                    details["source_id"] = args[1]
                
                if "raw_event_id" in kwargs:
                    details["raw_event_id"] = kwargs["raw_event_id"]
                elif len(args) > 1 and isinstance(args[1], int) and "enrich" in task_name:
                    details["raw_event_id"] = args[1]
                
                if "limit" in kwargs:
                    details["limit"] = kwargs["limit"]
                
                if "query" in kwargs:
                    details["query"] = kwargs["query"] or "default"
                
                if "when" in kwargs:
                    details["when"] = kwargs["when"]
                
                logger.error(f"[{task_name.upper()}] Failed: {e}")
                
                # Send notifications in parallel
                await notify_job_failed(task_name, str(e), details if details else None)
                await create_failure_issue(task_name, str(e), details if details else None)
                
                raise
            finally:
                if outcome is not None:
                    record_task_outcome(task_name, outcome, time.monotonic() - start)
                    if task_name in CRON_TASKS:
                        record_cron_outcome(task_name, outcome)
        
        return wrapper
    return decorator


@notify_on_failure("ingest")
async def ingest_task(ctx: dict, query: str | None = None, when: str = "3d") -> dict:
    """
    Stage 1: Ingest - Fetch Google News RSS and create SourceGoogleNews records.
    
    Args:
        ctx: ARQ context (contains redis connection)
        query: Optional search query. If None, uses default queries.
        when: Time filter (e.g., "3d" for 3 days)
    
    Returns:
        dict with ingestion results
    """
    logger.info(f"[INGEST] Starting with query: {query or 'default queries'}")
    
    from app.services.ingestion import ingest_feeds, ingest_single_query
    
    if query:
        sources = await ingest_single_query(query=query, when=when, resolve_urls=True)
    else:
        sources = await ingest_feeds(when=when, resolve_urls=True)
    
    logger.info(f"[INGEST] Complete: created {len(sources)} new sources")
    
    # Enqueue classification tasks for new sources
    if sources and ctx.get("redis"):
        for source in sources:
            await ctx["redis"].enqueue_job("classify_task", source.id)
        logger.info(f"[INGEST] Enqueued {len(sources)} classification tasks")
    
    return {
        "status": "completed",
        "task": "ingest",
        "sources_created": len(sources),
        "source_ids": [s.id for s in sources],
    }


@notify_on_failure("classify")
async def classify_task(ctx: dict, source_id: int) -> dict:
    """
    Stage 1.5: Classify - Classify headline to filter violent death news.
    
    Args:
        ctx: ARQ context
        source_id: ID of the SourceGoogleNews to classify
    
    Returns:
        dict with classification results
    """
    logger.info(f"[CLASSIFY] Starting for source_id: {source_id}")
    
    from app.services.classification import classify_source
    
    is_violent_death = await classify_source(source_id)
    
    if is_violent_death:
        logger.info(f"[CLASSIFY] source_id {source_id}: VIOLENT DEATH - enqueueing download")
        # Enqueue download task
        if ctx.get("redis"):
            await ctx["redis"].enqueue_job("download_task", source_id)
        
        return {
            "status": "completed",
            "task": "classify",
            "source_id": source_id,
            "is_violent_death": True,
        }
    else:
        logger.info(f"[CLASSIFY] source_id {source_id}: DISCARDED")
        return {
            "status": "completed",
            "task": "classify",
            "source_id": source_id,
            "is_violent_death": False,
        }


@notify_on_failure("classify_batch")
async def classify_pending_task(
    ctx: dict,
    limit: int = 50,
    chain_next: bool = True,
    concurrency: int = 10,
) -> dict:
    """
    Batch task: Classify headlines for all pending sources.
    
    After classification, optionally enqueues batch download for sources
    that passed classification (marked as ready_for_download).
    """
    logger.info(f"[CLASSIFY_BATCH] Starting for up to {limit} sources")
    
    from app.services.classification import classify_pending_sources
    
    result = await classify_pending_sources(limit=limit, concurrency=concurrency)
    
    logger.info(f"[CLASSIFY_BATCH] Complete: {result}")
    
    # Chain to download if we have sources ready (standalone runs only).
    if (
        chain_next
        and result.get("violent_death", 0) > 0
        and ctx.get("redis")
    ):
        await ctx["redis"].enqueue_job("download_classified_task", limit=result["violent_death"] + 50)
        logger.info(f"[CLASSIFY_BATCH] Enqueued batch download task")
    
    return {
        "status": "completed",
        "task": "classify_batch",
        **result,
    }


@notify_on_failure("download")
async def download_task(ctx: dict, source_id: int) -> dict:
    """
    Stage 2: Download - Fetch article content using trafilatura.
    
    Args:
        ctx: ARQ context
        source_id: ID of the SourceGoogleNews to download
    
    Returns:
        dict with download results
    """
    logger.info(f"[DOWNLOAD] Starting for source_id: {source_id}")
    
    from app.services.download import DownloadOutcome, download_source_content
    
    outcome = await download_source_content(source_id)
    
    if outcome == DownloadOutcome.ready_for_extraction:
        logger.info(f"[DOWNLOAD] Success for source_id: {source_id}")
        # Enqueue extraction task
        if ctx.get("redis"):
            await ctx["redis"].enqueue_job("extract_task", source_id)
            logger.info(f"[DOWNLOAD] Enqueued extract task for source_id: {source_id}")
        
        return {
            "status": "completed",
            "task": "download",
            "source_id": source_id,
        }
    if outcome == DownloadOutcome.discarded:
        logger.info(f"[DOWNLOAD] Discarded by content gate for source_id: {source_id}")
        return {
            "status": "discarded",
            "task": "download",
            "source_id": source_id,
        }

    logger.warning(f"[DOWNLOAD] Failed for source_id: {source_id}")
    await notify_job_failed("download", "Download failed", {"source_id": source_id})
    await create_failure_issue("download", "Download failed", {"source_id": source_id})
    return {
        "status": "failed",
        "task": "download",
        "source_id": source_id,
    }


@notify_on_failure("extract")
async def extract_task(ctx: dict, source_id: int) -> dict:
    """
    Stage 3: Extract - Extract structured event data using LLM.
    
    Args:
        ctx: ARQ context
        source_id: ID of the SourceGoogleNews to process
    
    Returns:
        dict with extraction results
    """
    logger.info(f"[EXTRACT] Starting for source_id: {source_id}")
    
    from app.services.extraction import extract_source
    
    raw_event = await extract_source(source_id)
    
    if raw_event:
        logger.info(f"[EXTRACT] Created RawEvent {raw_event.id} from source {source_id}")
        
        # Enqueue enrichment task
        if ctx.get("redis"):
            await ctx["redis"].enqueue_job("enrich_task", raw_event.id)
            logger.info(f"[EXTRACT] Enqueued enrich task for raw_event_id: {raw_event.id}")
        
        return {
            "status": "completed",
            "task": "extract",
            "source_id": source_id,
            "raw_event_id": raw_event.id,
        }
    else:
        logger.warning(f"[EXTRACT] Failed for source_id: {source_id}")
        await notify_job_failed("extract", "Extraction failed", {"source_id": source_id})
        await create_failure_issue("extract", "Extraction failed", {"source_id": source_id})
        return {
            "status": "failed",
            "task": "extract",
            "source_id": source_id,
        }


@notify_on_failure("enrich")
async def enrich_task(ctx: dict, raw_event_id: int) -> dict:
    """
    Stage 4: Enrich - Try to match RawEvent to existing UniqueEvent.
    
    This is Phase 1 of deduplication: immediate matching.
    - Finds candidate UniqueEvents using blocking strategies
    - Uses LLM to determine if RawEvent matches any candidate
    - If match: links RawEvent to UniqueEvent
    - If no match: marks RawEvent as 'pending' for batch processing
    
    Args:
        ctx: ARQ context
        raw_event_id: ID of the RawEvent to process
    
    Returns:
        dict with enrichment results
    """
    logger.info(f"[ENRICH] Starting for raw_event_id: {raw_event_id}")
    
    from app.services.enrichment import process_single_raw_event
    
    result = await process_single_raw_event(raw_event_id)
    
    logger.info(f"[ENRICH] Result for raw_event_id {raw_event_id}: {result['status']}")
    
    return {
        "task": "enrich",
        **result,
    }


@notify_on_failure("download_batch")
async def download_classified_task(
    ctx: dict, limit: int = 50, chain_next: bool = True
) -> dict:
    """
    Batch task: Download content for all classified sources (ready for download).
    
    After download, optionally enqueues batch extraction for sources
    that were successfully downloaded (marked as ready_for_extraction).
    """
    logger.info(f"[DOWNLOAD_BATCH] Starting for up to {limit} sources")
    
    from app.services.download import download_classified_sources
    
    result = await download_classified_sources(limit=limit)
    
    logger.info(f"[DOWNLOAD_BATCH] Complete: {result}")
    
    # Chain to extraction if we have successful downloads (standalone runs only).
    if (
        chain_next
        and result.get("successful", 0) > 0
        and ctx.get("redis")
    ):
        await ctx["redis"].enqueue_job("extract_ready_task", limit=result["successful"] + 10)
        logger.info(f"[DOWNLOAD_BATCH] Enqueued batch extraction task")
    
    return {
        "status": "completed",
        "task": "download_batch",
        **result,
    }


@notify_on_failure("extract_batch")
async def extract_ready_task(
    ctx: dict, limit: int = 10, chain_next: bool = True
) -> dict:
    """
    Batch task: Extract events from all sources ready for extraction.
    
    After extraction, optionally enqueues enrichment for each created RawEvent.
    """
    logger.info(f"[EXTRACT_BATCH] Starting for up to {limit} sources")
    
    from app.services.extraction import extract_ready_sources
    
    result = await extract_ready_sources(limit=limit)
    
    logger.info(f"[EXTRACT_BATCH] Complete: {result}")
    
    # Enqueue per-raw-event enrichment (standalone runs only; full pipeline uses batch dedup).
    raw_event_ids = result.get("raw_event_ids", [])
    if chain_next and raw_event_ids and ctx.get("redis"):
        for raw_event_id in raw_event_ids:
            await ctx["redis"].enqueue_job("enrich_task", raw_event_id)
        logger.info(f"[EXTRACT_BATCH] Enqueued {len(raw_event_ids)} enrichment tasks")
    
    return {
        "status": "completed",
        "task": "extract_batch",
        **result,
    }


@notify_on_failure("batch_dedup")
async def batch_dedup_task(
    ctx: dict, limit: int = 200, chain_next: bool = True
) -> dict:
    """
    Periodic: Process pending RawEvents through batch clustering.
    
    This is Phase 2 of deduplication:
    - Gets all RawEvents with deduplication_status='pending'
    - Groups by date+city
    - Clusters within each group (using victim names + LLM)
    - Creates UniqueEvents for each cluster
    
    Should be run periodically (e.g., hourly) to process accumulated pending events.
    """
    logger.info(f"[BATCH_DEDUP] Starting for up to {limit} pending RawEvents")
    
    from app.services.enrichment import process_pending_deduplication
    
    result = await process_pending_deduplication(limit=limit)
    
    logger.info(f"[BATCH_DEDUP] Complete: {result}")
    
    # Enqueue enrichment for newly created UniqueEvents (standalone runs only).
    if (
        chain_next
        and result.get("unique_events_created", 0) > 0
        and ctx.get("redis")
    ):
        await ctx["redis"].enqueue_job("batch_enrich_task", limit=result["unique_events_created"] + 10)
        logger.info(f"[BATCH_DEDUP] Enqueued batch enrichment task")
    
    return {
        "task": "batch_dedup",
        **result,
    }


@notify_on_failure("batch_enrich")
async def batch_enrich_task(
    ctx: dict, limit: int = 50, chain_next: bool = True
) -> dict:
    """
    Periodic: Enrich UniqueEvents that need enrichment.
    
    Processes all UniqueEvents with needs_enrichment=True:
    - Fetches all linked RawEvents and source content
    - Uses LLM to synthesize best information
    - Updates UniqueEvent fields
    
    Should be run after batch_dedup_task or when new sources are linked.
    """
    logger.info(f"[BATCH_ENRICH] Starting for up to {limit} UniqueEvents")
    
    from app.services.enrichment import run_pending_enrichments
    
    result = await run_pending_enrichments(limit=limit)
    
    logger.info(f"[BATCH_ENRICH] Complete: {result}")
    
    # Chain to geocoding (standalone runs only).
    if chain_next and ctx.get("redis"):
        await ctx["redis"].enqueue_job("batch_geocode_task", limit=limit + 10)
        logger.info("[BATCH_ENRICH] Enqueued batch geocode task")
    
    return {
        "task": "batch_enrich",
        **result,
    }


@notify_on_failure("batch_geocode")
async def batch_geocode_task(ctx: dict, limit: int = 50) -> dict:
    """
    Periodic: Geocode UniqueEvents that have not been geocoded yet.
    
    Processes UniqueEvents where geocoding_source IS NULL and city is present:
    - Builds an address query from the structured location fields
    - Calls the Google Maps Geocoding API
    - Writes latitude/longitude/plus_code/place_id/formatted_address/
      location_precision/geocoding_confidence/geocoding_source
    
    No-ops gracefully when GOOGLE_MAPS_API_KEY is unset.
    Should run after batch_enrich_task.
    """
    logger.info(f"[BATCH_GEOCODE] Starting for up to {limit} UniqueEvents")
    
    from app.services.geocoding import geocode_pending
    
    result = await geocode_pending(limit=limit)
    
    logger.info(f"[BATCH_GEOCODE] Complete: {result}")
    
    return {
        "task": "batch_geocode",
        **result,
    }


@notify_on_failure("full_pipeline")
async def run_full_pipeline(ctx: dict, query: str | None = None, when: str = "3d") -> dict:
    """
    Run the full pipeline: ingest -> download -> extract -> enrich.
    
    Each stage automatically enqueues tasks for the next stage.
    """
    logger.info("[PIPELINE] Starting full pipeline run")
    start_time = time.time()
    
    # Notify job started
    await notify_job_started("full_pipeline", {"query": query or "default", "when": when})
    
    # Start with ingestion (which will chain to download -> extract -> enrich)
    result = await ingest_task(ctx, query=query, when=when)
    
    duration = time.time() - start_time
    await notify_job_finished("full_pipeline", result, duration)
    
    return {
        "status": "started",
        "task": "full_pipeline",
        "message": "Pipeline started - tasks will chain automatically",
        "ingestion_result": result,
    }


@notify_on_failure("ingest_cities")
async def ingest_cities_task(
    ctx: dict,
    cities: list[str] | None = None,
    when: str = "1h",
    enqueue_classify: bool = True,
) -> dict:
    """
    Ingest news for all configured cities with adaptive sharding.
    
    This is the main task for hourly city-based ingestion.
    Cities that hit the 100-result limit will automatically switch
    to source-based sharding on subsequent runs.
    
    After ingestion, optionally enqueues classification for new sources.
    Callers that run classify inline (e.g. ``ingest_cities_full_pipeline``)
    must pass ``enqueue_classify=False`` to avoid duplicate concurrent jobs.
    
    Args:
        ctx: ARQ context (contains redis connection)
        cities: Optional list of cities. If None, uses CITIES from config.
        when: Time filter (default "1h" for hourly)
        enqueue_classify: When True, enqueue ``classify_pending_task`` after ingest.
    
    Returns:
        dict with ingestion results
    """
    logger.info(f"[INGEST_CITIES] Starting with when={when}")
    start_time = time.time()
    
    # Notify job started
    await notify_job_started("ingest_cities", {"when": when})
    
    from app.services.ingestion import ingest_all_cities
    
    result = await ingest_all_cities(cities=cities, when=when, resolve_urls=True)
    
    total_sources = result['total_sources_created']
    logger.info(f"[INGEST_CITIES] Complete: {total_sources} new sources")
    
    # Enqueue classification tasks for all new sources (standalone runs only).
    if enqueue_classify and total_sources > 0 and ctx.get("redis"):
        classify_limit = min(total_sources + 50, 200)
        await ctx["redis"].enqueue_job("classify_pending_task", classify_limit)
        logger.info(
            f"[INGEST_CITIES] Enqueued batch classification task (limit={classify_limit})"
        )
    
    duration = time.time() - start_time
    await notify_job_finished("ingest_cities", result, duration)
    
    return {
        "status": "completed",
        "task": "ingest_cities",
        **result,
    }


async def _run_classify_until_drained(
    *,
    limit_per_batch: int = 150,
    max_batches: int = 12,
    concurrency: int = 15,
) -> dict:
    """Classify pending sources in batches until drained or batch cap hit."""
    from app.services.classification import classify_pending_sources

    totals = {
        "processed": 0,
        "violent_death": 0,
        "discarded": 0,
        "errors": 0,
    }
    for batch in range(1, max_batches + 1):
        result = await classify_pending_sources(
            limit=limit_per_batch,
            concurrency=concurrency,
        )
        for key in totals:
            totals[key] += int(result.get(key, 0))
        processed = int(result.get("processed", 0))
        logger.info(
            f"[CLASSIFY_BATCH] Batch {batch}/{max_batches}: {result} "
            f"(running total processed={totals['processed']})"
        )
        if processed < limit_per_batch:
            break
    return totals


async def _run_pipeline_maintenance() -> None:
    """Recover stuck rows and requeue transient failures. Best-effort, non-fatal."""
    from app.services.maintenance import (
        checkpoint_wal,
        recover_stuck_sources,
        requeue_retryable_failures,
    )

    try:
        await checkpoint_wal()
        await recover_stuck_sources(older_than_minutes=15)
        await requeue_retryable_failures()
    except Exception as e:
        logger.warning(f"[PIPELINE_MAINTENANCE] Failed (continuing): {e}")


async def _process_cities_backlog_steps(ctx: dict) -> dict:
    """Run classify → download → extract → dedup → enrich → geocode (no ingest)."""
    classify_result = await _run_classify_until_drained(
        limit_per_batch=150,
        max_batches=12,
        concurrency=15,
    )
    download_result = await download_classified_task(ctx, limit=500, chain_next=False)
    extract_result = await extract_ready_task(ctx, limit=100, chain_next=False)
    dedup_result = await batch_dedup_task(ctx, limit=200, chain_next=False)
    enrich_result = await batch_enrich_task(ctx, limit=50, chain_next=False)
    geocode_result = await batch_geocode_task(ctx, limit=200)
    return {
        "classify": classify_result,
        "download": download_result,
        "extract": extract_result,
        "dedup": dedup_result,
        "enrich": enrich_result,
        "geocode": geocode_result,
    }


@notify_on_failure("ingest_cities_hourly")
async def ingest_cities_hourly(
    ctx: dict,
    cities: list[str] | None = None,
    when: str = "1h",
) -> dict:
    """
    Hourly cron: ingest, then enqueue headline classification.

    Ingest stays short (no inline LLM). Classification is queued immediately so
    new sources are not left waiting until the :35 backlog cron — which can be
    delayed when a prior backlog run is still in progress (unique=True, 2h cap).
    """
    logger.info("[INGEST_HOURLY] Starting hourly city ingest")
    await _run_pipeline_maintenance()
    return await ingest_cities_task(
        ctx, cities=cities, when=when, enqueue_classify=True
    )


@notify_on_failure("process_cities_backlog")
async def process_cities_backlog(ctx: dict) -> dict:
    """
    Hourly cron: drain classify/download/extract/dedup backlog.

    Runs maintenance first, then processes accumulated sources from ingest and
    prior runs. May take up to 2 hours at peak load; unique=True prevents overlap.
    """
    logger.info("[CITIES_BACKLOG] Starting backlog processing")
    start_time = time.time()

    await notify_job_started("process_cities_backlog", {})
    await _run_pipeline_maintenance()

    steps = await _process_cities_backlog_steps(ctx)
    duration = time.time() - start_time

    classify_result = steps["classify"]
    download_result = steps["download"]
    extract_result = steps["extract"]
    dedup_result = steps["dedup"]

    await notify_pipeline_summary(
        total_sources=0,
        sources_classified=classify_result.get("violent_death", 0),
        sources_downloaded=download_result.get("successful", 0),
        raw_events_extracted=extract_result.get("raw_events_created", 0),
        unique_events_created=dedup_result.get("unique_events_created", 0),
        duration_seconds=duration,
    )

    return {
        "status": "completed",
        "task": "process_cities_backlog",
        "duration_seconds": duration,
        **steps,
    }


@notify_on_failure("cities_full_pipeline")
async def ingest_cities_full_pipeline(
    ctx: dict,
    cities: list[str] | None = None,
    when: str = "1h",
) -> dict:
    """
    Run city ingestion followed by classify, download, extraction, and deduplication.
    
    This is the complete hourly pipeline for city-based ingestion.
    Pipeline: ingest -> classify -> download -> extract -> batch_dedup -> batch_enrich -> batch_geocode
    """
    logger.info("[CITIES_PIPELINE] Starting full city pipeline")
    start_time = time.time()
    
    # Notify job started
    await notify_job_started("cities_full_pipeline", {"when": when})
    
    await _run_pipeline_maintenance()

    # Step 1: Ingest cities (classify runs inline in Step 2 — do not enqueue).
    ingest_result = await ingest_cities_task(
        ctx, cities=cities, when=when, enqueue_classify=False
    )

    steps = await _process_cities_backlog_steps(ctx)
    duration = time.time() - start_time

    classify_result = steps["classify"]
    download_result = steps["download"]
    extract_result = steps["extract"]
    dedup_result = steps["dedup"]

    await notify_pipeline_summary(
        total_sources=ingest_result.get("total_sources_created", 0),
        sources_classified=classify_result.get("violent_death", 0),
        sources_downloaded=download_result.get("successful", 0),
        raw_events_extracted=extract_result.get("raw_events_created", 0),
        unique_events_created=dedup_result.get("unique_events_created", 0),
        duration_seconds=duration,
    )

    return {
        "status": "completed",
        "task": "cities_full_pipeline",
        "duration_seconds": duration,
        "ingest": ingest_result,
        **steps,
    }


# ARQ function wrappers with per-job timeouts (manual enqueues inherit these).
from arq.worker import func

ingest_cities_full_pipeline_job = func(
    ingest_cities_full_pipeline,
    timeout=7200,
    max_tries=1,
)
ingest_cities_task_job = func(
    ingest_cities_task,
    timeout=1800,
)
ingest_cities_hourly_job = func(
    ingest_cities_hourly,
    timeout=1800,
    max_tries=1,
)
process_cities_backlog_job = func(
    process_cities_backlog,
    timeout=7200,
    max_tries=1,
)
classify_pending_task_job = func(
    classify_pending_task,
    timeout=1800,
    max_tries=2,
)

# List of all task functions for the worker
TASK_FUNCTIONS = [
    ingest_task,
    classify_task,
    classify_pending_task_job,
    download_task,
    download_classified_task,
    extract_task,
    extract_ready_task,
    enrich_task,
    batch_dedup_task,
    batch_enrich_task,
    batch_geocode_task,
    run_full_pipeline,
    ingest_cities_task_job,
    ingest_cities_full_pipeline_job,
    ingest_cities_hourly_job,
    process_cities_backlog_job,
]
