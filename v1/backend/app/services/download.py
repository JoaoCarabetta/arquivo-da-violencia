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
    async with async_session_maker() as session:
        # Get the source
        source = await session.get(SourceGoogleNews, source_id)
        if not source:
            logger.warning(f"Source {source_id} not found")
            return False
        
        # Use resolved URL if available, otherwise the Google News URL
        target_url = source.resolved_url or source.google_news_url
        
        logger.info(f"Downloading content from: {target_url[:80]}...")
        
        try:
            # Download the page
            downloaded = trafilatura.fetch_url(target_url)
            
            if not downloaded:
                logger.warning(f"Failed to download: {target_url}")
                source.status = SourceStatus.failed
                source.updated_at = datetime.utcnow()
                await session.commit()
                return False
            
            # Extract content
            content, metadata = extract_content_and_metadata(downloaded)
            
            if content:
                source.content = content
                source.status = SourceStatus.downloaded
                source.updated_at = datetime.utcnow()
                await session.commit()
                
                logger.info(f"Downloaded {len(content)} chars for source {source_id}")
                return True
            else:
                logger.warning(f"No content extracted from: {target_url}")
                source.status = SourceStatus.failed
                source.updated_at = datetime.utcnow()
                await session.commit()
                return False
                
        except Exception as e:
            logger.error(f"Error downloading source {source_id}: {e}")
            source.status = SourceStatus.failed
            source.updated_at = datetime.utcnow()
            await session.commit()
            return False


async def download_pending_sources(limit: int = 50) -> dict:
    """
    Download content for all pending sources.
    
    Args:
        limit: Maximum number of sources to process
    
    Returns:
        Dict with download statistics
    """
    async with async_session_maker() as session:
        # Get pending sources
        result = await session.exec(
            select(SourceGoogleNews)
            .where(SourceGoogleNews.status == SourceStatus.pending)
            .where(SourceGoogleNews.resolved_url.isnot(None))
            .limit(limit)
        )
        sources = result.all()
    
    logger.info(f"Found {len(sources)} pending sources to download")
    
    if not sources:
        return {
            "processed": 0,
            "successful": 0,
            "failed": 0,
        }
    
    successful = 0
    failed = 0
    
    for source in sources:
        success = await download_source_content(source.id)
        if success:
            successful += 1
        else:
            failed += 1
    
    logger.info(f"Download complete: {successful} successful, {failed} failed")
    
    return {
        "processed": len(sources),
        "successful": successful,
        "failed": failed,
    }

