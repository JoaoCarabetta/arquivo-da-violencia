"""Ingestion service - fetches Google News RSS and creates SourceGoogleNews records."""

import asyncio
import urllib.parse
from datetime import datetime

import feedparser
import googlenewsdecoder
from loguru import logger
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import async_session_maker
from app.models import SourceGoogleNews, SourceStatus, CityStats
from app.services.cities import (
    CITIES,
    BRAZILIAN_NEWS_SOURCES,
    REQUEST_INTERVAL_SECONDS,
    REQUESTS_PER_MINUTE,
    SHARDING_THRESHOLD,
    DEFAULT_WHEN,
)


# Google News RSS configuration for Brazil
GOOGLE_NEWS_BASE_URL = "https://news.google.com/rss/search"
DEFAULT_PARAMS = {
    "hl": "pt-BR",
    "gl": "BR",
    "ceid": "BR:pt-419",
}

# Default search queries for violence-related news in Rio de Janeiro
DEFAULT_QUERIES = [
    "homicídio Rio de Janeiro",
    "assassinato Rio de Janeiro",
    "tiroteio Rio de Janeiro",
]


def build_rss_url(query: str, when: str | None = "7d") -> str:
    """Build Google News RSS URL with proper encoding."""
    full_query = query
    if when:
        full_query = f"{query} when:{when}"
    
    params = {
        "q": full_query,
        **DEFAULT_PARAMS,
    }
    
    query_string = urllib.parse.urlencode(params, safe=":")
    return f"{GOOGLE_NEWS_BASE_URL}?{query_string}"


def parse_headline_and_publisher(title: str) -> tuple[str, str | None]:
    """
    Parse RSS title to extract headline and publisher.
    Format: "Headline text - Publisher Name"
    """
    if " - " in title:
        parts = title.rsplit(" - ", 1)
        return parts[0].strip(), parts[1].strip()
    return title.strip(), None


def resolve_google_news_url(obfuscated_url: str) -> str | None:
    """Resolve obfuscated Google News URL to the real publisher URL."""
    if "news.google.com" not in obfuscated_url:
        return obfuscated_url
    
    try:
        result = googlenewsdecoder.new_decoderv1(obfuscated_url, interval=0.5)
        if result.get("status"):
            return result.get("decoded_url")
    except Exception as e:
        logger.warning(f"Failed to decode URL: {e}")
    
    return None


def fetch_rss_feed(query: str, when: str | None = "7d") -> list[dict]:
    """
    Fetch RSS feed entries for a query.
    
    Args:
        query: Search query
        when: Time filter (e.g., "7d" for 7 days, "1h" for 1 hour)
    
    Returns:
        List of parsed feed entries
    """
    url = build_rss_url(query, when)
    logger.info(f"Fetching RSS feed: {url}")
    
    feed = feedparser.parse(url)
    
    if feed.bozo:
        logger.warning(f"Feed parsing error: {feed.bozo_exception}")
    
    logger.info(f"Found {len(feed.entries)} entries for query: {query}")
    return feed.entries


async def ingest_feeds(
    queries: list[str] | None = None,
    when: str | None = "7d",
    resolve_urls: bool = True,
) -> list[SourceGoogleNews]:
    """
    Main ingestion function - fetches RSS feeds and saves to database.
    
    Args:
        queries: List of search queries (uses DEFAULT_QUERIES if None)
        when: Time filter for recency
        resolve_urls: Whether to resolve obfuscated URLs (slower but provides real URLs)
    
    Returns:
        List of newly created SourceGoogleNews records
    """
    queries = queries or DEFAULT_QUERIES
    all_entries = []
    
    # Fetch all RSS feeds
    for query in queries:
        entries = fetch_rss_feed(query, when)
        for entry in entries:
            entry["_search_query"] = query
        all_entries.extend(entries)
    
    logger.info(f"Total entries fetched: {len(all_entries)}")
    
    # Process and save to database
    new_sources = []
    
    async with async_session_maker() as session:
        for entry in all_entries:
            # Extract Google News ID from the link (the guid)
            google_news_id = entry.get("id") or entry.get("link", "")
            
            # Check if already exists
            existing = await session.exec(
                select(SourceGoogleNews).where(
                    SourceGoogleNews.google_news_id == google_news_id
                )
            )
            if existing.first():
                logger.debug(f"Skipping duplicate: {google_news_id[:50]}...")
                continue
            
            # Parse headline and publisher from title
            title = entry.get("title", "")
            headline, publisher_name = parse_headline_and_publisher(title)
            
            # Get publisher URL from source tag
            source_info = entry.get("source", {})
            publisher_url = source_info.get("href") if isinstance(source_info, dict) else None
            
            # Parse publication date
            published_at = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                try:
                    published_at = datetime(*entry.published_parsed[:6])
                except Exception:
                    pass
            
            # Resolve URL if requested
            google_news_url = entry.get("link", "")
            resolved_url = None
            if resolve_urls:
                resolved_url = resolve_google_news_url(google_news_url)
                if resolved_url:
                    logger.debug(f"Resolved: {resolved_url[:60]}...")
            
            # Create new source record
            source = SourceGoogleNews(
                google_news_id=google_news_id,
                google_news_url=google_news_url,
                resolved_url=resolved_url,
                headline=headline,
                publisher_name=publisher_name,
                publisher_url=publisher_url,
                published_at=published_at,
                search_query=entry.get("_search_query"),
                status=SourceStatus.ready_for_classification,
                fetched_at=datetime.utcnow(),
            )
            
            session.add(source)
            new_sources.append(source)
        
        if new_sources:
            await session.commit()
            # Refresh to get IDs
            for source in new_sources:
                await session.refresh(source)
    
    logger.info(f"Created {len(new_sources)} new sources")
    return new_sources


async def ingest_single_query(
    query: str,
    when: str | None = "7d",
    resolve_urls: bool = True,
) -> list[SourceGoogleNews]:
    """Convenience function to ingest a single query."""
    return await ingest_feeds(queries=[query], when=when, resolve_urls=resolve_urls)


# =============================================================================
# Adaptive City-Based Ingestion with Sharding
# =============================================================================

async def get_or_create_city_stats(
    city: str, 
    session: AsyncSession
) -> CityStats:
    """Get or create a CityStats record for a city."""
    result = await session.exec(
        select(CityStats).where(CityStats.city_name == city)
    )
    stats = result.first()
    
    if not stats:
        stats = CityStats(city_name=city)
        session.add(stats)
        await session.commit()
        await session.refresh(stats)
    
    return stats


async def get_queries_for_city(
    city: str,
    session: AsyncSession,
    when: str = DEFAULT_WHEN,
) -> list[str]:
    """
    Get queries for a city based on its sharding status.
    
    - Standard mode: Single query "{city} when:{when}"
    - Sharded mode: One query per source "{city} when:{when} site:{source}"
    """
    stats = await get_or_create_city_stats(city, session)
    
    if stats.needs_sharding:
        logger.info(f"[{city}] Using sharded mode ({len(BRAZILIAN_NEWS_SOURCES)} sources)")
        return [f"{city} when:{when} site:{src}" for src in BRAZILIAN_NEWS_SOURCES]
    else:
        logger.info(f"[{city}] Using standard mode")
        return [f"{city} when:{when}"]


async def update_city_stats(
    city: str,
    total_count: int,
    session: AsyncSession,
) -> CityStats:
    """
    Update city stats after fetching.
    If count >= SHARDING_THRESHOLD, enable sharding for next run.
    """
    stats = await get_or_create_city_stats(city, session)
    
    stats.last_result_count = total_count
    stats.last_fetch_at = datetime.utcnow()
    stats.updated_at = datetime.utcnow()
    
    if total_count >= SHARDING_THRESHOLD and not stats.needs_sharding:
        stats.needs_sharding = True
        stats.hit_limit_count += 1
        logger.warning(f"[{city}] Hit {SHARDING_THRESHOLD} limit! Enabling sharding for next run.")
    
    await session.commit()
    await session.refresh(stats)
    
    return stats


# Global rate limiter for parallel requests
class AsyncRateLimiter:
    """Token bucket rate limiter for async operations."""
    
    def __init__(self, requests_per_minute: float):
        self.interval = 60.0 / requests_per_minute
        self.lock = asyncio.Lock()
        self.last_request = 0.0
    
    async def acquire(self):
        """Wait until we can make a request."""
        async with self.lock:
            import time
            now = time.time()
            wait_time = self.interval - (now - self.last_request)
            if wait_time > 0:
                await asyncio.sleep(wait_time)
            self.last_request = time.time()


# Shared rate limiter instance
_rate_limiter: AsyncRateLimiter | None = None


def get_rate_limiter() -> AsyncRateLimiter:
    """Get or create the shared rate limiter."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = AsyncRateLimiter(REQUESTS_PER_MINUTE)
    return _rate_limiter


async def rate_limited_fetch(query: str, when: str | None = None) -> list[dict]:
    """
    Fetch RSS feed with rate limiting.
    Uses a shared rate limiter to coordinate parallel requests.
    """
    limiter = get_rate_limiter()
    await limiter.acquire()
    return fetch_rss_feed(query, when=when)


async def ingest_city(
    city: str,
    when: str = DEFAULT_WHEN,
    resolve_urls: bool = True,
) -> tuple[list[SourceGoogleNews], int]:
    """
    Ingest news for a single city with adaptive sharding.
    
    Returns:
        Tuple of (new sources created, total entries fetched)
    """
    all_entries = []
    
    async with async_session_maker() as session:
        # Get queries based on sharding status
        queries = await get_queries_for_city(city, session, when)
        
        # Fetch all queries with rate limiting
        for query in queries:
            # Rate limited fetch (when is already in the query string)
            entries = await rate_limited_fetch(query, when=None)
            
            # Tag entries with their query
            for entry in entries:
                entry["_search_query"] = query
                entry["_city"] = city
            
            all_entries.extend(entries)
            logger.info(f"  Query '{query[:50]}...' returned {len(entries)} entries")
        
        total_count = len(all_entries)
        logger.info(f"[{city}] Total entries: {total_count}")
        
        # Update city stats (this may enable sharding for next run)
        await update_city_stats(city, total_count, session)
    
    # Now save the entries to database
    new_sources = []
    
    async with async_session_maker() as session:
        for entry in all_entries:
            # Extract Google News ID
            google_news_id = entry.get("id") or entry.get("link", "")
            
            # Check if already exists
            existing = await session.exec(
                select(SourceGoogleNews).where(
                    SourceGoogleNews.google_news_id == google_news_id
                )
            )
            if existing.first():
                continue
            
            # Parse headline and publisher
            title = entry.get("title", "")
            headline, publisher_name = parse_headline_and_publisher(title)
            
            # Get publisher URL
            source_info = entry.get("source", {})
            publisher_url = source_info.get("href") if isinstance(source_info, dict) else None
            
            # Parse publication date
            published_at = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                try:
                    published_at = datetime(*entry.published_parsed[:6])
                except Exception:
                    pass
            
            # Resolve URL if requested
            google_news_url = entry.get("link", "")
            resolved_url = None
            if resolve_urls:
                resolved_url = resolve_google_news_url(google_news_url)
            
            # Create source record
            source = SourceGoogleNews(
                google_news_id=google_news_id,
                google_news_url=google_news_url,
                resolved_url=resolved_url,
                headline=headline,
                publisher_name=publisher_name,
                publisher_url=publisher_url,
                published_at=published_at,
                search_query=entry.get("_search_query"),
                status=SourceStatus.ready_for_classification,
                fetched_at=datetime.utcnow(),
            )
            
            session.add(source)
            new_sources.append(source)
        
        if new_sources:
            await session.commit()
            for source in new_sources:
                await session.refresh(source)
    
    logger.info(f"[{city}] Created {len(new_sources)} new sources")
    return new_sources, total_count


async def ingest_all_cities(
    cities: list[str] | None = None,
    when: str = DEFAULT_WHEN,
    resolve_urls: bool = True,
    max_concurrent: int = 10,
) -> dict:
    """
    Ingest news for all configured cities with adaptive sharding.
    Runs cities in PARALLEL with rate limiting.
    
    Args:
        cities: List of cities to process (uses CITIES from config if None)
        when: Time filter (default "1h" for hourly ingestion)
        resolve_urls: Whether to resolve obfuscated URLs
        max_concurrent: Maximum concurrent city ingestions (default 10)
    
    Returns:
        Summary dict with statistics
    """
    cities = cities or CITIES
    
    logger.info(f"Starting PARALLEL city ingestion for {len(cities)} cities")
    logger.info(f"Max concurrent: {max_concurrent}")
    logger.info(f"Rate limit: 1 request per {REQUEST_INTERVAL_SECONDS:.1f}s")
    
    # Semaphore to limit concurrent operations
    semaphore = asyncio.Semaphore(max_concurrent)
    
    # Results storage
    city_results = {}
    
    async def process_city(city: str) -> tuple[str, dict]:
        """Process a single city with semaphore control."""
        async with semaphore:
            logger.info(f"[{city}] Starting...")
            try:
                sources, entry_count = await ingest_city(city, when, resolve_urls)
                result = {
                    "sources_created": len(sources),
                    "entries_fetched": entry_count,
                    "status": "success",
                }
                logger.info(f"[{city}] Done: {entry_count} entries, {len(sources)} new")
                return city, result
            except Exception as e:
                logger.error(f"[{city}] Error: {e}")
                return city, {
                    "sources_created": 0,
                    "entries_fetched": 0,
                    "status": "error",
                    "error": str(e),
                }
    
    # Run all cities in parallel (semaphore limits concurrency)
    import time
    start_time = time.time()
    
    tasks = [process_city(city) for city in cities]
    results = await asyncio.gather(*tasks)
    
    elapsed = time.time() - start_time
    
    # Aggregate results
    for city, result in results:
        city_results[city] = result
    
    total_sources = sum(r["sources_created"] for r in city_results.values())
    total_entries = sum(r["entries_fetched"] for r in city_results.values())
    errors = sum(1 for r in city_results.values() if r["status"] == "error")
    
    logger.info(f"\n{'='*60}")
    logger.info(f"INGESTION COMPLETE")
    logger.info(f"Cities processed: {len(cities)}")
    logger.info(f"Total entries fetched: {total_entries}")
    logger.info(f"Total new sources created: {total_sources}")
    logger.info(f"Errors: {errors}")
    logger.info(f"Time: {elapsed:.1f}s")
    logger.info(f"{'='*60}")
    
    # Log cities that hit the limit
    for city, result in city_results.items():
        if result["entries_fetched"] >= SHARDING_THRESHOLD:
            logger.warning(f"⚠️  {city}: HIT 100 LIMIT - sharding enabled for next run")
    
    return {
        "cities_processed": len(cities),
        "total_entries": total_entries,
        "total_sources_created": total_sources,
        "errors": errors,
        "elapsed_seconds": elapsed,
        "city_results": city_results,
    }

