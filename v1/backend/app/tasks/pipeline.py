"""Pipeline task definitions for ARQ."""

from loguru import logger


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
    
    # Enqueue download tasks for new sources
    if sources and ctx.get("redis"):
        for source in sources:
            await ctx["redis"].enqueue_job("download_task", source.id)
        logger.info(f"[INGEST] Enqueued {len(sources)} download tasks")
    
    return {
        "status": "completed",
        "task": "ingest",
        "sources_created": len(sources),
        "source_ids": [s.id for s in sources],
    }


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
    
    from app.services.download import download_source_content
    
    success = await download_source_content(source_id)
    
    if success:
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
    else:
        logger.warning(f"[DOWNLOAD] Failed for source_id: {source_id}")
        return {
            "status": "failed",
            "task": "download",
            "source_id": source_id,
        }


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
        return {
            "status": "failed",
            "task": "extract",
            "source_id": source_id,
        }


async def enrich_task(ctx: dict, raw_event_id: int) -> dict:
    """
    Stage 4: Enrich - Deduplicate and link to UniqueEvent, geocode.
    
    Args:
        ctx: ARQ context
        raw_event_id: ID of the RawEvent to process
    
    Returns:
        dict with enrichment results
    """
    logger.info(f"[ENRICH] Starting for raw_event_id: {raw_event_id}")
    
    # TODO: Implement enrichment service
    # from app.services.enrichment import enrich_event
    # unique_event = await enrich_event(raw_event_id)
    
    return {
        "status": "pending",
        "task": "enrich",
        "raw_event_id": raw_event_id,
        "message": "Enrichment not yet implemented",
    }


async def download_pending_task(ctx: dict, limit: int = 50) -> dict:
    """
    Batch task: Download content for all pending sources.
    """
    logger.info(f"[DOWNLOAD_BATCH] Starting for up to {limit} sources")
    
    from app.services.download import download_pending_sources
    
    result = await download_pending_sources(limit=limit)
    
    logger.info(f"[DOWNLOAD_BATCH] Complete: {result}")
    return {
        "status": "completed",
        "task": "download_batch",
        **result,
    }


async def extract_downloaded_task(ctx: dict, limit: int = 10) -> dict:
    """
    Batch task: Extract events from all downloaded sources.
    """
    logger.info(f"[EXTRACT_BATCH] Starting for up to {limit} sources")
    
    from app.services.extraction import extract_downloaded_sources
    
    result = await extract_downloaded_sources(limit=limit)
    
    logger.info(f"[EXTRACT_BATCH] Complete: {result}")
    return {
        "status": "completed",
        "task": "extract_batch",
        **result,
    }


async def run_full_pipeline(ctx: dict, query: str | None = None, when: str = "3d") -> dict:
    """
    Run the full pipeline: ingest -> download -> extract -> enrich.
    
    Each stage automatically enqueues tasks for the next stage.
    """
    logger.info("[PIPELINE] Starting full pipeline run")
    
    # Start with ingestion (which will chain to download -> extract -> enrich)
    result = await ingest_task(ctx, query=query, when=when)
    
    return {
        "status": "started",
        "task": "full_pipeline",
        "message": "Pipeline started - tasks will chain automatically",
        "ingestion_result": result,
    }


async def ingest_cities_task(
    ctx: dict, 
    cities: list[str] | None = None, 
    when: str = "1h"
) -> dict:
    """
    Ingest news for all configured cities with adaptive sharding.
    
    This is the main task for hourly city-based ingestion.
    Cities that hit the 100-result limit will automatically switch
    to source-based sharding on subsequent runs.
    
    Args:
        ctx: ARQ context (contains redis connection)
        cities: Optional list of cities. If None, uses CITIES from config.
        when: Time filter (default "1h" for hourly)
    
    Returns:
        dict with ingestion results
    """
    logger.info(f"[INGEST_CITIES] Starting with when={when}")
    
    from app.services.ingestion import ingest_all_cities
    
    result = await ingest_all_cities(cities=cities, when=when, resolve_urls=True)
    
    logger.info(f"[INGEST_CITIES] Complete: {result['total_sources_created']} new sources")
    
    # Enqueue download tasks for new sources
    # Note: We could collect all source IDs and batch enqueue them here
    # For now, the sources are created but downloads need to be triggered separately
    
    return {
        "status": "completed",
        "task": "ingest_cities",
        **result,
    }


async def ingest_cities_full_pipeline(
    ctx: dict,
    cities: list[str] | None = None,
    when: str = "1h",
) -> dict:
    """
    Run city ingestion followed by download and extraction.
    
    This is the complete hourly pipeline for city-based ingestion.
    """
    logger.info("[CITIES_PIPELINE] Starting full city pipeline")
    
    # Step 1: Ingest cities
    ingest_result = await ingest_cities_task(ctx, cities=cities, when=when)
    
    # Step 2: Download pending sources
    download_result = await download_pending_task(ctx, limit=500)
    
    # Step 3: Extract downloaded sources
    extract_result = await extract_downloaded_task(ctx, limit=100)
    
    return {
        "status": "completed",
        "task": "cities_full_pipeline",
        "ingest": ingest_result,
        "download": download_result,
        "extract": extract_result,
    }


# List of all task functions for the worker
TASK_FUNCTIONS = [
    ingest_task,
    download_task,
    extract_task,
    enrich_task,
    download_pending_task,
    extract_downloaded_task,
    run_full_pipeline,
    ingest_cities_task,
    ingest_cities_full_pipeline,
]
