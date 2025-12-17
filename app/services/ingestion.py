import feedparser
import trafilatura
import googlenewsdecoder
import urllib.parse
import concurrent.futures
from datetime import datetime, timedelta
from app.extensions import db
from app.models import Source
from flask import current_app

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
    
    print(f"Fetching feed for query: '{full_query}'...")
    feed = feedparser.parse(url)
    print(f"Found {len(feed.entries)} entries.")
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
        print(f"Error resolving {url}: {e}")
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

        # 2. Download Content
        if (not source.content or force) and source.status != 'failed':
            try:
                downloaded = trafilatura.fetch_url(target_url)
                if downloaded:
                    content = trafilatura.extract(downloaded)
                    if content:
                        source.content = content
                        source.status = 'downloaded' # Ready for extraction
                        changed = True
                    else:
                        pass # No content extracted
                else:
                    pass # Download failed
            except Exception as e:
                print(f"  -> Error downloading {target_url}: {e}")

        if changed:
            db.session.commit()

from app.services.locations import get_geo_queries

EXPANSION_TERMS = [
    "homicídio", "assassinato", "morto", "tiroteio", "baleado", 
    "corpo encontrado", "polícia", "milícia", "tráfico"
]

def run_ingestion(start_date=None, end_date=None, query=None, force=False, expand_queries=False, expand_geo=False):
    """Stage 1: Ingestion - Fetch RSS, Save Sources, Download Content."""
    
    # Date parsing
    s_date = datetime.strptime(start_date, '%Y-%m-%d') if start_date else None
    e_date = datetime.strptime(end_date, '%Y-%m-%d') if end_date else datetime.now()

    base_query = query or "Rio de Janeiro"
    queries = [base_query]
    
    if expand_queries:
        print(f"Expanding query '{base_query}' with {len(EXPANSION_TERMS)} topics...")
        for term in EXPANSION_TERMS:
            queries.append(f'{base_query} "{term}"')

    if expand_geo:
        geo_queries = get_geo_queries()
        print(f"Expanding with {len(geo_queries)} geo-locations...")
        queries.extend(geo_queries)

    # 1. Fetch from RSS
    all_entries = []
    print(f"Starting ingestion fetch job for {len(queries)} queries...")
    
    for q in queries:
        print(f"--- Query: {q} ---")
        for entries in fetch_all_feeds(s_date, e_date, q):
            all_entries.extend(entries)
    
    print(f"Total entries fetched: {len(all_entries)}")
    
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
    
    print(f"Ingestion complete. Added {new_count} new sources.")
    print(f"Queuing {len(source_ids_to_process)} sources for content download (Parallel)...")

    # 3. Parallel Download
    # Capture real app object for threads
    real_app = current_app._get_current_object()
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [
            executor.submit(process_source_task, real_app, sid, force) 
            for sid in source_ids_to_process
        ]
        
        # Simple wait
        concurrent.futures.wait(futures)

    print("Content download complete.")
