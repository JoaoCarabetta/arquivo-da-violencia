import feedparser
import trafilatura
import googlenewsdecoder
import urllib.parse
import concurrent.futures
import time
from datetime import datetime, timedelta
from loguru import logger
from app.extensions import db
from app.models import Source
from flask import current_app
from app.services.extraction import extract_content_and_metadata, get_best_publication_date

RSS_URL = "https://news.google.com/rss/search?q=Rio+de+Janeiro&hl=pt-BR&gl=BR&ceid=BR:pt-419"

def fetch_feed(query=None, after_date=None, before_date=None):
    """Fetch RSS feed and return entries."""
    base_query = query or "Rio de Janeiro"
    
    # Construct query with dates
    full_query = base_query
    if after_date:
        full_query += f" after:{after_date}"
    if before_date:
        full_query += f" before:{before_date}"
    
    encoded_query = urllib.parse.quote(full_query)
    url = f"https://news.google.com/rss/search?q={encoded_query}&hl=pt-BR&gl=BR&ceid=BR:pt-419"
    
    logger.info(f"Fetching feed for query: '{full_query}'...")
    feed = feedparser.parse(url)
    logger.info(f"Found {len(feed.entries)} entries.")
    return feed.entries

def fetch_all_feeds(start_date=None, end_date=None, query=None):
    """Generator to fetch feeds in chunks."""
    if not start_date:
        yield fetch_feed(query=query)
        return

    current_start = start_date
    current_start = start_date
    while current_start < end_date:
        # User feedback: 30 days is too coarse and hits 100 limit or missing items.
        # Switching to 1 day chunks to maximize content.
        current_end = current_start + timedelta(days=1)
        if current_end > end_date:
            current_end = end_date
            
        yield fetch_feed(
            query=query, 
            after_date=current_start.strftime('%Y-%m-%d'),
            before_date=current_end.strftime('%Y-%m-%d')
        )
        current_start = current_end

def resolve_url(url):
    """Resolve Google News URL to real URL."""
    if 'news.google.com' not in url:
        return url
        
    try:
        res = googlenewsdecoder.new_decoderv1(url, interval=1)
        if res.get('status'):
            return res.get('decoded_url')
    except Exception as e:
        logger.error(f"Error resolving {url}: {e}")
    return url

def process_source_task(app, source_id, force=False):
    """Worker task: Download content for a source (runs in thread)."""
    with app.app_context():
        source = Source.query.get(source_id)
        if not source:
            return

        changed = False

        # 1. Resolve URL
        if not source.resolved_url or force:
            resolved = resolve_url(source.url)
            if resolved != source.url:
                source.resolved_url = resolved
                changed = True
        
        target_url = source.resolved_url or source.url

        # 2. Download Content and Extract Metadata
        if (not source.content or force) and source.status != 'failed':
            try:
                downloaded = trafilatura.fetch_url(target_url)
                if downloaded:
                    content, metadata, trafilatura_date = extract_content_and_metadata(downloaded)
                    if content:
                        source.content = content
                        source.status = 'downloaded' # Ready for extraction
                        changed = True
                        
                        # Update published_at if trafilatura found a better date
                        if trafilatura_date:
                            best_date = get_best_publication_date(
                                trafilatura_date,
                                source.published_at,
                                source.fetched_at
                            )
                            if best_date and best_date != source.published_at:
                                logger.info(f"  -> Updated publication date from {source.published_at} to {best_date.strftime('%Y-%m-%d')}")
                                source.published_at = best_date
                                changed = True
                    else:
                        pass # No content extracted
                else:
                    pass # Download failed
            except Exception as e:
                logger.error(f"  -> Error downloading {target_url}: {e}")

        if changed:
            db.session.commit()

from app.services.locations import get_geo_queries

EXPANSION_TERMS = [
    "homicídio", "assassinato", "morto", "tiroteio", "baleado", 
    "corpo encontrado", "polícia", "milícia", "tráfico"
]

def run_ingestion(start_date=None, end_date=None, query=None, force=False, expand_queries=False, expand_geo=False, max_workers=10):
    """Stage 1: Ingestion - Fetch RSS, Save Sources, Download Content."""
    
    # Date parsing
    s_date = datetime.strptime(start_date, '%Y-%m-%d') if start_date else None
    e_date = datetime.strptime(end_date, '%Y-%m-%d') if end_date else datetime.now()

    base_query = query or "Rio de Janeiro"
    queries = [base_query]
    
    if expand_queries:
        logger.info(f"Expanding query '{base_query}' with {len(EXPANSION_TERMS)} topics...")
        for term in EXPANSION_TERMS:
            queries.append(f'{base_query} "{term}"')

    if expand_geo:
        geo_queries = get_geo_queries()
        logger.info(f"Expanding with {len(geo_queries)} geo-locations...")
        queries.extend(geo_queries)

    # 1. Fetch from RSS
    all_entries = []
    logger.info(f"Starting ingestion fetch job for {len(queries)} queries...")
    
    for q in queries:
        logger.info(f"--- Query: {q} ---")
        for entries in fetch_all_feeds(s_date, e_date, q):
            all_entries.extend(entries)
    
    logger.info(f"Total entries fetched: {len(all_entries)}")
    
    source_ids_to_process = []
    new_count = 0

    # 2. Save/Queue Sources
    for entry in all_entries:
        url = entry.link
        existing = Source.query.filter_by(url=url).first()
        
        # Parse publication date from RSS feed
        published_at = None
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            try:
                import time
                published_at = datetime(*entry.published_parsed[:6])
            except:
                pass
        
        if not existing:
            source = Source(
                url=url,
                title=entry.title,
                source_type='news_article',
                status='pending',
                published_at=published_at,
                fetched_at=datetime.utcnow()
            )
            db.session.add(source)
            db.session.commit()
            source_ids_to_process.append(source.id)
            new_count += 1
        elif force or existing.status == 'pending':
            # Update published_at if we didn't have it before
            if not existing.published_at and published_at:
                existing.published_at = published_at
                db.session.commit()
            source_ids_to_process.append(existing.id)
        # If existing and status='downloaded', we skip unless force=True
        # Actually logic above: if force or status='pending'. 
        # If status='downloaded' and not force, we ignore. Correct.
    
    logger.info(f"Ingestion complete. Added {new_count} new sources.")
    logger.info(f"Queuing {len(source_ids_to_process)} sources for content download (Parallel, {max_workers} workers)...")

    # 3. Parallel Download
    # Capture real app object for threads
    real_app = current_app._get_current_object()
    
    completed = 0
    errors = 0
    total = len(source_ids_to_process)
    download_start = time.time()
    
    if total == 0:
        logger.info("No sources to download.")
        return
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(process_source_task, real_app, sid, force): sid
            for sid in source_ids_to_process
        }
        
        # Process as they complete with progress tracking and time estimates
        for future in concurrent.futures.as_completed(futures):
            sid = futures[future]
            try:
                future.result()  # Wait for completion
                completed += 1
            except Exception as e:
                errors += 1
                logger.warning(f"Error processing source {sid}: {e}")
            
            # Progress update with time estimates
            if completed % 10 == 0 or completed == total:
                elapsed = time.time() - download_start
                if completed > 0:
                    avg_time_per_item = elapsed / completed
                    remaining = total - completed
                    estimated_remaining = avg_time_per_item * remaining
                    estimated_total = elapsed + estimated_remaining
                    
                    logger.info(
                        f"Download progress: {completed}/{total} ({completed/total*100:.1f}%) | "
                        f"Elapsed: {elapsed:.1f}s | "
                        f"ETA: {estimated_remaining:.1f}s | "
                        f"Est. total: {estimated_total:.1f}s | "
                        f"Errors: {errors}"
                    )

    total_elapsed = time.time() - download_start
    logger.info(f"Content download complete. Processed: {completed}/{total}, Errors: {errors}, Time: {total_elapsed:.1f}s")
