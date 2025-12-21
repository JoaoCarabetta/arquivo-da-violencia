"""Pipeline control API router."""

from fastapi import APIRouter, HTTPException, Query
from arq import create_pool
from arq.jobs import Job
from loguru import logger

from app.tasks.worker import get_redis_settings

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


async def get_arq_pool():
    """Get ARQ Redis pool."""
    try:
        return await create_pool(get_redis_settings())
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Redis connection failed: {e}. Is Redis running? Try: docker compose up -d redis",
        )


# =============================================================================
# Pipeline Control Endpoints
# =============================================================================


@router.post("/run")
async def run_pipeline(
    query: str | None = Query(None, description="Search query for Google News"),
    when: str = Query("3d", description="Time filter (e.g., '1d', '3d', '7d')"),
):
    """
    Run the full pipeline: ingest -> download -> extract -> enrich.
    
    Each stage automatically chains to the next.
    """
    pool = await get_arq_pool()
    job = await pool.enqueue_job("run_full_pipeline", query, when)
    await pool.close()

    return {
        "status": "queued",
        "job_id": job.job_id,
        "task": "run_full_pipeline",
        "message": "Full pipeline started",
    }


@router.post("/ingest")
async def run_ingestion(
    query: str | None = Query(None, description="Search query for Google News"),
    when: str = Query("3d", description="Time filter"),
):
    """
    Stage 1: Ingest Google News RSS feeds.
    
    Fetches news, resolves URLs, and creates SourceGoogleNews records.
    Automatically enqueues download tasks for new sources.
    """
    pool = await get_arq_pool()
    job = await pool.enqueue_job("ingest_task", query, when)
    await pool.close()

    return {
        "status": "queued",
        "job_id": job.job_id,
        "task": "ingest_task",
        "message": "Ingestion task queued",
    }


@router.post("/ingest-cities")
async def run_city_ingestion(
    when: str = Query("1h", description="Time filter (default 1h for hourly)"),
):
    """
    Ingest news for ALL configured Brazilian cities with adaptive sharding.
    
    - Fetches news for 52+ major cities
    - Automatically shards high-volume cities (São Paulo, Rio, etc.)
    - Rate limited to respect Google's limits
    
    This is the main production ingestion endpoint for hourly runs.
    """
    pool = await get_arq_pool()
    job = await pool.enqueue_job("ingest_cities_task", None, when)
    await pool.close()

    return {
        "status": "queued",
        "job_id": job.job_id,
        "task": "ingest_cities_task",
        "message": "City ingestion task queued (52+ cities)",
    }


@router.post("/ingest-cities-pipeline")
async def run_city_pipeline(
    when: str = Query("1h", description="Time filter"),
):
    """
    Run FULL city pipeline: ingest cities -> classify -> download -> extract.
    
    This is the complete hourly production pipeline.
    """
    pool = await get_arq_pool()
    job = await pool.enqueue_job("ingest_cities_full_pipeline", None, when)
    await pool.close()

    return {
        "status": "queued",
        "job_id": job.job_id,
        "task": "ingest_cities_full_pipeline",
        "message": "Full city pipeline queued (ingest -> classify -> download -> extract)",
    }


@router.post("/classify")
async def run_classify_batch(
    limit: int = Query(50, description="Maximum sources to classify"),
):
    """
    Stage 1.5 (batch): Classify headlines for all pending sources.
    
    Uses lightweight LLM to determine if headlines indicate violent death.
    Sources that pass classification move to ready-for-download.
    """
    pool = await get_arq_pool()
    job = await pool.enqueue_job("classify_pending_task", limit)
    await pool.close()

    return {
        "status": "queued",
        "job_id": job.job_id,
        "task": "classify_pending_task",
        "message": f"Classification batch task queued (limit: {limit})",
    }


@router.post("/classify/{source_id}")
async def run_classify_single(source_id: int):
    """Stage 1.5: Classify headline for a single source."""
    pool = await get_arq_pool()
    job = await pool.enqueue_job("classify_task", source_id)
    await pool.close()

    return {
        "status": "queued",
        "job_id": job.job_id,
        "task": "classify_task",
        "source_id": source_id,
    }


@router.post("/download")
async def run_download_batch(
    limit: int = Query(50, description="Maximum sources to download"),
):
    """
    Stage 2 (batch): Download content for all classified sources.
    
    Only downloads sources that passed headline classification.
    """
    pool = await get_arq_pool()
    job = await pool.enqueue_job("download_classified_task", limit)
    await pool.close()

    return {
        "status": "queued",
        "job_id": job.job_id,
        "task": "download_classified_task",
        "message": f"Download batch task queued (limit: {limit})",
    }


@router.post("/download/{source_id}")
async def run_download_single(source_id: int):
    """Stage 2: Download content for a single source."""
    pool = await get_arq_pool()
    job = await pool.enqueue_job("download_task", source_id)
    await pool.close()

    return {
        "status": "queued",
        "job_id": job.job_id,
        "task": "download_task",
        "source_id": source_id,
    }


@router.post("/extract")
async def run_extract_batch(
    limit: int = Query(10, description="Maximum sources to extract"),
):
    """
    Stage 3 (batch): Extract events from all sources ready for extraction.
    """
    pool = await get_arq_pool()
    job = await pool.enqueue_job("extract_ready_task", limit)
    await pool.close()

    return {
        "status": "queued",
        "job_id": job.job_id,
        "task": "extract_ready_task",
        "message": f"Extract batch task queued (limit: {limit})",
    }


@router.post("/extract/{source_id}")
async def run_extract_single(source_id: int):
    """Stage 3: Extract event from a single source."""
    pool = await get_arq_pool()
    job = await pool.enqueue_job("extract_task", source_id)
    await pool.close()

    return {
        "status": "queued",
        "job_id": job.job_id,
        "task": "extract_task",
        "source_id": source_id,
    }


@router.post("/enrich/{raw_event_id}")
async def run_enrichment(raw_event_id: int):
    """Stage 4: Enrich a raw event (deduplicate, geocode)."""
    pool = await get_arq_pool()
    job = await pool.enqueue_job("enrich_task", raw_event_id)
    await pool.close()

    return {
        "status": "queued",
        "job_id": job.job_id,
        "task": "enrich_task",
        "raw_event_id": raw_event_id,
    }


@router.post("/batch-dedup")
async def run_batch_deduplication(
    limit: int = Query(100, description="Maximum RawEvents to process"),
):
    """
    Batch deduplication: Process pending RawEvents through clustering.
    
    This is Phase 2 of deduplication:
    - Gets all RawEvents with deduplication_status='pending'
    - Groups by date+city
    - Clusters within each group (using victim names + LLM)
    - Creates UniqueEvents for each cluster
    """
    pool = await get_arq_pool()
    job = await pool.enqueue_job("batch_dedup_task", limit)
    await pool.close()

    return {
        "status": "queued",
        "job_id": job.job_id,
        "task": "batch_dedup_task",
        "message": f"Batch deduplication queued (limit: {limit})",
    }


@router.post("/batch-enrich")
async def run_batch_enrichment(
    limit: int = Query(50, description="Maximum UniqueEvents to enrich"),
):
    """
    Batch enrichment: Enrich UniqueEvents that need enrichment.
    
    Processes all UniqueEvents with needs_enrichment=True:
    - Fetches all linked RawEvents and source content
    - Uses LLM to synthesize best information
    - Updates UniqueEvent fields
    """
    pool = await get_arq_pool()
    job = await pool.enqueue_job("batch_enrich_task", limit)
    await pool.close()

    return {
        "status": "queued",
        "job_id": job.job_id,
        "task": "batch_enrich_task",
        "message": f"Batch enrichment queued (limit: {limit})",
    }


# =============================================================================
# Job Status & Queue Monitoring
# =============================================================================


@router.get("/status")
async def get_pipeline_status():
    """Get queue status and worker health."""
    try:
        pool = await get_arq_pool()
        queued_jobs = await pool.queued_jobs()
        await pool.close()

        return {
            "redis": "connected",
            "queued_jobs": len(queued_jobs),
            "jobs": [
                {
                    "job_id": job.job_id,
                    "function": job.function,
                    "enqueue_time": job.enqueue_time.isoformat() if job.enqueue_time else None,
                }
                for job in queued_jobs[:20]
            ],
        }
    except HTTPException:
        raise
    except Exception as e:
        return {
            "redis": "disconnected",
            "error": str(e),
            "queued_jobs": 0,
        }


@router.get("/city-stats")
async def get_city_stats():
    """
    Get ingestion statistics for all cities.
    
    Shows which cities have sharding enabled and last result counts.
    """
    from sqlmodel import select
    from app.database import async_session_maker
    from app.models import CityStats
    from app.services.cities import CITIES
    
    async with async_session_maker() as session:
        result = await session.exec(select(CityStats).order_by(CityStats.last_result_count.desc()))
        all_stats = result.all()
    
    sharded_cities = [s for s in all_stats if s.needs_sharding]
    
    return {
        "configured_cities": len(CITIES),
        "tracked_cities": len(all_stats),
        "sharded_cities": len(sharded_cities),
        "stats": [
            {
                "city": s.city_name,
                "last_count": s.last_result_count,
                "needs_sharding": s.needs_sharding,
                "hit_limit_count": s.hit_limit_count,
                "last_fetch": s.last_fetch_at.isoformat() if s.last_fetch_at else None,
            }
            for s in all_stats
        ],
    }


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Get status and result of a specific job."""
    pool = await get_arq_pool()
    job = Job(job_id, pool)
    
    try:
        status = await job.status()
        info = await job.info()
        
        # Try to get result (non-blocking)
        result = None
        if status.name in ("complete", "not_found"):
            try:
                result = await job.result(poll_delay=0, timeout=0.1)
            except Exception:
                pass
        
        await pool.close()
        
        # Safely extract info fields
        response = {
            "job_id": job_id,
            "status": status.name,
            "result": result,
        }
        
        if info:
            response["function"] = getattr(info, "function", None)
            if hasattr(info, "enqueue_time") and info.enqueue_time:
                response["enqueue_time"] = info.enqueue_time.isoformat()
        
        return response
    except Exception as e:
        await pool.close()
        raise HTTPException(status_code=500, detail=str(e))
