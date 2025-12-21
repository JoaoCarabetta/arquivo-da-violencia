"""Content download service using trafilatura."""

from datetime import datetime

import trafilatura
from loguru import logger
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import async_session_maker
from app.models import SourceGoogleNews, SourceStatus


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


async def download_source_content(source_id: int) -> bool:
    """
    Download and extract content for a single source.
    
    Args:
        source_id: ID of the SourceGoogleNews to process
    
    Returns:
        True if successful, False otherwise
    """
    from sqlalchemy import text
    
    async with async_session_maker() as session:
        # Get the source URL using raw SQL to avoid enum issues
        result = await session.execute(
            text("SELECT resolved_url, google_news_url FROM source_google_news WHERE id = :id"),
            {"id": source_id}
        )
        row = result.fetchone()
        
        if not row:
            logger.warning(f"Source {source_id} not found")
            return False
        
        # Use resolved URL if available, otherwise the Google News URL
        target_url = row[0] or row[1]
        
        logger.info(f"Downloading content from: {target_url[:80]}...")
        
        try:
            # Download the page
            downloaded = trafilatura.fetch_url(target_url)
            
            if not downloaded:
                logger.warning(f"Failed to download: {target_url}")
                await session.execute(
                    text("""
                        UPDATE source_google_news 
                        SET status = 'failed_in_download', updated_at = CURRENT_TIMESTAMP
                        WHERE id = :id
                    """),
                    {"id": source_id}
                )
                await session.commit()
                return False
            
            # Extract content
            content, metadata = extract_content_and_metadata(downloaded)
            
            if content:
                await session.execute(
                    text("""
                        UPDATE source_google_news 
                        SET content = :content, status = 'ready_for_extraction', updated_at = CURRENT_TIMESTAMP
                        WHERE id = :id
                    """),
                    {"id": source_id, "content": content}
                )
                await session.commit()
                
                logger.info(f"Downloaded {len(content)} chars for source {source_id}")
                return True
            else:
                logger.warning(f"No content extracted from: {target_url}")
                await session.execute(
                    text("""
                        UPDATE source_google_news 
                        SET status = 'failed_in_download', updated_at = CURRENT_TIMESTAMP
                        WHERE id = :id
                    """),
                    {"id": source_id}
                )
                await session.commit()
                return False
                
        except Exception as e:
            logger.error(f"Error downloading source {source_id}: {e}")
            await session.execute(
                text("""
                    UPDATE source_google_news 
                    SET status = 'failed_in_download', updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                """),
                {"id": source_id}
            )
            await session.commit()
            return False


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
    failed = 0
    
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Download failed with exception: {result}")
            failed += 1
        elif result is True:
            successful += 1
        else:
            failed += 1
    
    logger.info(f"Download complete: {successful} successful, {failed} failed")
    
    return {
        "processed": len(source_ids),
        "successful": successful,
        "failed": failed,
    }

