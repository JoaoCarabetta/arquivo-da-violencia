import trafilatura
import googlenewsdecoder
import vertexai
from vertexai.generative_models import GenerativeModel
from google.oauth2 import service_account
import os
import re
from bs4 import BeautifulSoup
from app.extensions import db
from app.models import Source, Keyword, ExtractedEvent
from app.services.keywords import MURDER_KEYWORDS

# Configure Vertex AI (Gemini)
SA_PATH = "/Users/joaoc/Documents/service_accounts/rj-ia-desenvolvimento-bb81db62d872.json"
MODEL_NAME = "gemini-2.5-flash" 

try:
    if os.path.exists(SA_PATH):
        credentials = service_account.Credentials.from_service_account_file(
            SA_PATH,
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        vertexai.init(project=credentials.project_id, location="us-central1", credentials=credentials)
        print(f"✅ Vertex AI initialized for {credentials.service_account_email} (Project: {credentials.project_id})")
    else:
        print(f"⚠️ Service Account file not found at {SA_PATH}. LLM will be skipped.")
        credentials = None
except Exception as e:
    print(f"⚠️ Error initializing Vertex AI: {e}")
    credentials = None

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

def check_keywords_fast(text):
    """Fast check against static murder keywords."""
    if not text:
        return []
    
    text_lower = text.lower()
    matches = []
    # Check static list first (faster)
    for kw in MURDER_KEYWORDS:
        if kw in text_lower:
            matches.append(kw)
    
    return list(set(matches)) # Unique matches

import json
import re
from datetime import datetime, timezone
from dateutil import parser as date_parser

def parse_and_validate_date(date_str, min_year=2000):
    """
    Parse a date string and validate it's reasonable.
    
    Args:
        date_str: Date string in ISO format or other parseable format
        min_year: Minimum valid year (default 2000)
    
    Returns:
        datetime object if valid, None otherwise
    """
    if not date_str:
        return None
    
    try:
        # Parse the date string
        parsed_date = date_parser.parse(date_str)
        
        # Ensure timezone-aware datetime (convert to UTC if naive)
        if parsed_date.tzinfo is None:
            parsed_date = parsed_date.replace(tzinfo=timezone.utc)
        else:
            parsed_date = parsed_date.astimezone(timezone.utc)
        
        # Convert to naive UTC datetime for storage
        parsed_date = parsed_date.replace(tzinfo=None)
        
        # Validate: not in the future, not too old
        now = datetime.utcnow()
        min_date = datetime(min_year, 1, 1)
        
        if parsed_date > now:
            # Date is in the future, invalid
            return None
        
        if parsed_date < min_date:
            # Date is too old, invalid
            return None
        
        return parsed_date
    except (ValueError, TypeError, OverflowError):
        return None

def get_best_publication_date(trafilatura_date, existing_published_at, fetched_at):
    """
    Determine the best publication date using priority logic.
    
    Priority:
    1. Trafilatura metadata date (if valid)
    2. Existing published_at (from RSS)
    3. Never use fetched_at as publication date (return None if no valid date)
    
    Args:
        trafilatura_date: datetime from trafilatura metadata (can be None)
        existing_published_at: datetime from RSS feed (can be None)
        fetched_at: datetime when article was fetched (for reference only)
    
    Returns:
        Best datetime object or None
    """
    # Priority 1: Trafilatura metadata date
    if trafilatura_date:
        return trafilatura_date
    
    # Priority 2: Existing published_at from RSS
    if existing_published_at:
        return existing_published_at
    
    # Never use fetched_at as publication date
    return None

def extract_meta_content(html):
    """
    Extract content from meta tags (description, og:description, etc.)
    These often contain article summaries or lead paragraphs.
    
    Args:
        html: HTML content as string
    
    Returns:
        list of text snippets from meta tags
    """
    meta_content = []
    try:
        soup = BeautifulSoup(html, 'html.parser')
        
        # Extract from meta description
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc and meta_desc.get('content'):
            content = meta_desc.get('content').strip()
            if content and len(content) > 50:  # Only meaningful descriptions
                meta_content.append(content)
        
        # Extract from og:description
        og_desc = soup.find('meta', attrs={'property': 'og:description'})
        if og_desc and og_desc.get('content'):
            content = og_desc.get('content').strip()
            if content and len(content) > 50 and content not in meta_content:
                meta_content.append(content)
        
        # Extract from twitter:description
        twitter_desc = soup.find('meta', attrs={'name': 'twitter:description'})
        if twitter_desc and twitter_desc.get('content'):
            content = twitter_desc.get('content').strip()
            if content and len(content) > 50 and content not in meta_content:
                meta_content.append(content)
                
    except Exception as e:
        # If BeautifulSoup fails, try regex fallback
        try:
            # Simple regex to find meta description
            desc_match = re.search(r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']+)["\']', html, re.IGNORECASE)
            if desc_match:
                content = desc_match.group(1).strip()
                if content and len(content) > 50:
                    meta_content.append(content)
        except:
            pass
    
    return meta_content

def extract_content_and_metadata(downloaded_html):
    """
    Extract both content and metadata from HTML using trafilatura.
    Uses multiple extraction strategies to capture all relevant content sections.
    Also extracts content from meta tags which often contain article summaries.
    
    Args:
        downloaded_html: HTML content from trafilatura.fetch_url()
    
    Returns:
        tuple: (content_text, metadata_dict, publication_date)
        - content_text: str or None
        - metadata_dict: dict or None
        - publication_date: datetime or None
    """
    if not downloaded_html:
        return None, None, None
    
    try:
        # Strategy 1: Use bare_extraction with favor_recall=True to capture more content
        # favor_recall makes trafilatura more inclusive, capturing more sections
        result = trafilatura.bare_extraction(
            downloaded_html,
            include_comments=False,
            include_tables=False,
            favor_recall=True,  # More inclusive extraction
            with_metadata=True
        )
        
        if not result:
            return None, None, None
        
        # Extract text and metadata from Document object
        primary_content = result.text if hasattr(result, 'text') else ''
        result_dict = result.as_dict() if hasattr(result, 'as_dict') else {}
        metadata = {k: v for k, v in result_dict.items() if k not in ['text', 'body', 'raw_text', 'comments', 'commentsbody']}
        
        # Strategy 2: Try with include_comments=True to capture additional content sections
        # Some sites put important content in comment-like structures or additional sections
        try:
            result_with_comments = trafilatura.bare_extraction(
                downloaded_html,
                include_comments=True,
                include_tables=False,
                favor_recall=True,
                with_metadata=True
            )
            if result_with_comments:
                secondary_content = result_with_comments.text if hasattr(result_with_comments, 'text') else ''
                # Always try to merge unique paragraphs from secondary extraction
                # This helps capture content that might be in different HTML sections
                if secondary_content and secondary_content != primary_content:
                    # Merge content: use primary as base, add unique paragraphs from secondary
                    # Split by double newlines (paragraphs) or single newlines if no double newlines
                    if '\n\n' in primary_content:
                        primary_paragraphs = [p.strip() for p in primary_content.split('\n\n') if p.strip()]
                    else:
                        primary_paragraphs = [p.strip() for p in primary_content.split('\n') if p.strip() and len(p.strip()) > 20]
                    
                    if '\n\n' in secondary_content:
                        secondary_paragraphs = [p.strip() for p in secondary_content.split('\n\n') if p.strip()]
                    else:
                        secondary_paragraphs = [p.strip() for p in secondary_content.split('\n') if p.strip() and len(p.strip()) > 20]
                    
                    # Create a set of primary paragraph signatures (first 100 chars) for comparison
                    primary_signatures = {}
                    for p in primary_paragraphs:
                        sig = p[:100].lower().strip()
                        if sig:
                            primary_signatures[sig] = p
                    
                    # Add paragraphs from secondary that aren't already in primary
                    merged_paragraphs = primary_paragraphs[:]
                    for para in secondary_paragraphs:
                        if not para or len(para) < 20:  # Skip very short paragraphs
                            continue
                            
                        para_sig = para[:100].lower().strip()
                        # Check if this paragraph is already in primary (exact or similar)
                        is_duplicate = False
                        
                        # First check exact signature match
                        if para_sig in primary_signatures:
                            is_duplicate = True
                        else:
                            # Check for high similarity with existing paragraphs
                            for existing_sig, existing_para in primary_signatures.items():
                                # Check word overlap (if >70% words match, consider duplicate)
                                existing_words = set(existing_para.lower().split())
                                new_words = set(para.lower().split())
                                if existing_words and new_words and len(existing_words) > 5:
                                    # Use Jaccard similarity
                                    overlap = len(existing_words & new_words) / len(existing_words | new_words)
                                    if overlap > 0.7:
                                        is_duplicate = True
                                        break
                        
                        if not is_duplicate and para not in merged_paragraphs:
                            merged_paragraphs.append(para)
                    
                    # Reconstruct content if we found new paragraphs
                    if len(merged_paragraphs) > len(primary_paragraphs):
                        primary_content = '\n\n'.join(merged_paragraphs)
        except Exception as e:
            # If secondary extraction fails, continue with primary
            pass
        
        # Strategy 3: Extract content from meta tags (description, og:description, etc.)
        # These often contain article summaries or lead paragraphs that trafilatura might miss
        try:
            meta_contents = extract_meta_content(downloaded_html)
            if meta_contents:
                # Merge meta content with main content
                for meta_text in meta_contents:
                    # Check if this meta content is already in the main content
                    # (sometimes meta description is a summary of the article)
                    meta_words = set(meta_text.lower().split())
                    if len(meta_words) > 10:  # Only process substantial meta content
                        # Check if meta content is substantially different from main content
                        is_duplicate = False
                        main_sentences = primary_content.split('.')
                        for sentence in main_sentences:
                            if len(sentence.strip()) > 20:
                                sentence_words = set(sentence.lower().split())
                                if sentence_words and meta_words:
                                    # Check if meta content overlaps significantly with any sentence
                                    overlap = len(sentence_words & meta_words) / len(sentence_words | meta_words)
                                    if overlap > 0.6:  # High overlap means it's likely already in main content
                                        is_duplicate = True
                                        break
                        
                        # If meta content is unique and substantial, prepend it to main content
                        if not is_duplicate and meta_text not in primary_content:
                            # Prepend meta content as it's usually a summary/lead
                            primary_content = meta_text + '\n\n' + primary_content
        except Exception as e:
            # If meta extraction fails, continue with what we have
            pass
        
        content = primary_content.strip()
        
        # Extract and parse publication date from metadata
        date_str = metadata.get('date')
        publication_date = None
        if date_str:
            publication_date = parse_and_validate_date(date_str)
            if publication_date:
                print(f"  -> Extracted publication date from article: {publication_date.strftime('%Y-%m-%d')}")
        
        return content, metadata, publication_date
    except Exception as e:
        print(f"  -> Error extracting metadata: {e}")
        # Fallback to simple extract with favor_recall
        try:
            result = trafilatura.bare_extraction(
                downloaded_html,
                favor_recall=True,
                with_metadata=False
            )
            if result and hasattr(result, 'text'):
                content = result.text
                return content, None, None
            else:
                # Last resort: use simple extract
                content = trafilatura.extract(downloaded_html)
                return content, None, None
        except:
            return None, None, None

def extract_with_llm(text, matches, publication_date=None):
    """Extract structured data from text using LLM.
    
    Args:
        text: The article content
        matches: Keywords that matched
        publication_date: When the article was fetched/published (for date inference)
    """
    if not credentials:
        return {"is_valid": True, "summary": "Skipped (No Creds)", "confidence": 0.5}, "Skipped (No Creds)"
    
    # Format publication date context
    date_context = ""
    if publication_date:
        date_context = f"""
Article Publication Date: {publication_date.strftime('%Y-%m-%d')} ({publication_date.strftime('%A, %d %B %Y')})
Use this date as reference to interpret relative dates like "hoje", "ontem", "esta sexta-feira (28)", "na última semana", etc.
"""
        
    try:
        model = GenerativeModel(MODEL_NAME)
        
        prompt = f"""Analyze the following news text and extract information about a SPECIFIC violent death/homicide.

{date_context}
Return a JSON object with the following fields:
- "is_valid": boolean (true if it describes a specific murder/homicide/body found, false otherwise)
- "summary": string (concise summary of the event, 1-2 sentences. In Portuguese.)
- "victim_name": string or null (name(s) of ALL victims if mentioned. If multiple victims, separate them with commas and "e" or "and". Example: "João Silva e Maria Santos" or "João Silva, Maria Santos e Pedro Costa")
- "location": string or null (specific location like street, neighborhood, or city if mentioned)
- "date": string or null (date of the EVENT in YYYY-MM-DD format. Use the publication date above to convert relative dates like "sexta-feira (28)" or "ontem" to absolute dates. Return null only if completely impossible to infer.)
- "confidence": float (0.0 to 1.0, how sure you are this is a violent crime report)

Text Snippet:
\"{text[:3000]}\"...

Keywords found: {matches}

JSON Response:
"""
        
        response = model.generate_content(prompt)
        raw_text = response.text.strip()
        
        # Clean up markdown code blocks if present
        if "```json" in raw_text:
            raw_text = raw_text.split("```json")[1].split("```")[0].strip()
        elif "```" in raw_text:
            raw_text = raw_text.split("```")[1].split("```")[0].strip()
            
        data = json.loads(raw_text)
        return data, "Extracted by LLM"
            
    except Exception as e:
        print(f"LLM Error: {e}")
        # Fallback
        return {"is_valid": True, "summary": "LLM Error (Fallback)", "confidence": 0.5}, f"LLM Error: {e}"


def process_source_extraction(source, force=False):
    """Process a single source for extraction."""
    changed = False
    
    # Early check: skip if already processed (unless force=True)
    if not force:
        if source.status == 'processed':
            # Already processed, skip
            return False
    
    # 1. Resolve URL
    if not source.resolved_url or force:
        if not source.resolved_url: 
             print(f"Resolving {source.url}")
        resolved = resolve_url(source.url)
        if resolved != source.url:
            source.resolved_url = resolved
            changed = True
    
    target_url = source.resolved_url or source.url

    # 2. Download valid content and extract metadata
    if (not source.content or force) and source.status != 'failed':
        try:
            downloaded = trafilatura.fetch_url(target_url)
            if downloaded:
                content, metadata, trafilatura_date = extract_content_and_metadata(downloaded)
                if content:
                    source.content = content
                    source.status = 'downloaded'
                    changed = True
                    
                    # Update published_at if trafilatura found a better date
                    if trafilatura_date:
                        best_date = get_best_publication_date(
                            trafilatura_date,
                            source.published_at,
                            source.fetched_at
                        )
                        if best_date and best_date != source.published_at:
                            print(f"  -> Updated publication date from {source.published_at} to {best_date.strftime('%Y-%m-%d')}")
                            source.published_at = best_date
                            changed = True
        except Exception as e:
             print(f"Download error: {e}")

    # 3. Identify Extractions (The Core Logic)
    if source.content:
        # A. Fast Keyword Filter
        matches = check_keywords_fast(source.content)
        
        if matches:
            # B. LLM Extraction (use published_at if available, never use fetched_at as publication date)
            # Only use fetched_at as fallback for LLM context if absolutely no publication date exists
            pub_date = source.published_at
            if not pub_date:
                # Log warning if we have to use fetched_at (shouldn't happen with proper date extraction)
                print(f"  -> Warning: No publication date found, using fetched_at for LLM context only")
                pub_date = source.fetched_at
            data, status = extract_with_llm(source.content, matches, pub_date)
            
            if data.get("is_valid"):
                # Parse date if possible
                event_date = None
                if data.get("date"):
                    try:
                        event_date = datetime.strptime(data["date"], "%Y-%m-%d")
                    except:
                        pass

                extraction = ExtractedEvent(
                    source=source,
                    confidence_score=data.get("confidence", 0.5),
                    summary=data.get("summary", "No summary"),
                    extracted_victim_name=data.get("victim_name"),
                    extracted_location=data.get("location"),
                    extracted_date=event_date
                )
                db.session.add(extraction)
                print(f"[+] Extraction Created: {source.title[:30]}... (Victim: {data.get('victim_name')})")
                changed = True
            else:
                print(f"[-] Ignored (Invalid): {source.title[:30]}...")
        
        # Mark processed
        if source.status != 'processed':
            source.status = 'processed'
            changed = True
    
    if changed:
        db.session.commit()
    return changed

import concurrent.futures
from flask import current_app

def process_single_source(app_obj, source_id, force):
    """Worker function to process a single source in its own context."""
    with app_obj.app_context():
        source = Source.query.get(source_id)
        if source:
            try:
                process_source_extraction(source, force=force)
                # process_source_extraction commits its own changes
                return True
            except Exception as e:
                print(f"Error processing source {source_id}: {e}")
                return False
    return False

def extract_event(source_id, force=False):
    """
    Extract structured event data from a single source.
    
    This is the main API for on-demand extraction. Can be called from routes,
    CLI, or any other context.
    
    Args:
        source_id: ID of the Source to process
        force: If True, re-extract even if already processed
        
    Returns:
        dict with:
            - success: bool
            - source_id: int
            - extraction: dict or None (the extracted data)
            - message: str (status/error message)
    """
    source = Source.query.get(source_id)
    
    if not source:
        return {
            "success": False, 
            "source_id": source_id,
            "extraction": None,
            "message": "Source not found"
        }
    
    # Re-resolve URL if force=True (in case URL changed or needs updating)
    if force:
        resolved = resolve_url(source.url)
        if resolved != source.url:
            source.resolved_url = resolved
            db.session.commit()
    
    # Check if already processed
    if source.status == 'processed' and not force:
        # Return existing extraction if available, otherwise just indicate it's processed
        existing = ExtractedEvent.query.filter_by(source_id=source_id).first()
        if existing:
            return {
                "success": True,
                "source_id": source_id,
                "extraction": {
                    "id": existing.id,
                    "summary": existing.summary,
                    "victim_name": existing.extracted_victim_name,
                    "location": existing.extracted_location,
                    "date": existing.extracted_date.strftime('%Y-%m-%d') if existing.extracted_date else None,
                    "confidence": existing.confidence_score
                },
                "message": "Source already processed"
            }
        else:
            return {
                "success": True,
                "source_id": source_id,
                "extraction": None,
                "message": "Source already processed (no extraction found)"
            }
    
    # Ensure we have content (re-download if force=True)
    if not source.content or force:
        # Try to download content first (or re-download if force=True)
        target_url = source.resolved_url or source.url
        if force and source.content:
            print(f"  -> Force re-extraction: Re-downloading content from {target_url}")
        try:
            downloaded = trafilatura.fetch_url(target_url)
            if downloaded:
                content, metadata, trafilatura_date = extract_content_and_metadata(downloaded)
                if content:
                    source.content = content
                    source.status = 'downloaded'
                    
                    # Update published_at if trafilatura found a better date
                    if trafilatura_date:
                        best_date = get_best_publication_date(
                            trafilatura_date,
                            source.published_at,
                            source.fetched_at
                        )
                        if best_date and best_date != source.published_at:
                            print(f"  -> Updated publication date from {source.published_at} to {best_date.strftime('%Y-%m-%d')}")
                            source.published_at = best_date
                    
                    db.session.commit()
        except Exception as e:
            return {
                "success": False,
                "source_id": source_id,
                "extraction": None,
                "message": f"Failed to download content: {e}"
            }
    
    if not source.content:
        return {
            "success": False,
            "source_id": source_id,
            "extraction": None,
            "message": "No content available for extraction"
        }
    
    # Run keyword check
    matches = check_keywords_fast(source.content)
    
    if not matches:
        source.status = 'processed'
        db.session.commit()
        return {
            "success": True,
            "source_id": source_id,
            "extraction": None,
            "message": "No relevant keywords found"
        }
    
    # Run LLM extraction (use published_at if available, never use fetched_at as publication date)
    # Only use fetched_at as fallback for LLM context if absolutely no publication date exists
    pub_date = source.published_at
    if not pub_date:
        # Log warning if we have to use fetched_at (shouldn't happen with proper date extraction)
        print(f"  -> Warning: No publication date found, using fetched_at for LLM context only")
        pub_date = source.fetched_at
    data, status = extract_with_llm(source.content, matches, pub_date)
    
    if not data.get("is_valid"):
        source.status = 'processed'
        db.session.commit()
        return {
            "success": True,
            "source_id": source_id,
            "extraction": None,
            "message": "LLM determined content is not a valid violent event"
        }
    
    # Create or update extraction
    # If force=True, check for existing extraction to update
    existing = None
    if force:
        existing = ExtractedEvent.query.filter_by(source_id=source_id).first()
    
    if existing:
        # Update existing extraction
        event_date = None
        if data.get("date"):
            try:
                event_date = datetime.strptime(data["date"], "%Y-%m-%d")
            except:
                pass
                
        existing.summary = data.get("summary")
        existing.extracted_victim_name = data.get("victim_name")
        existing.extracted_location = data.get("location")
        existing.extracted_date = event_date
        existing.confidence_score = data.get("confidence", 0.5)
        extraction_obj = existing
    else:
        # Create new extraction
        event_date = None
        if data.get("date"):
            try:
                event_date = datetime.strptime(data["date"], "%Y-%m-%d")
            except:
                pass
                
        extraction_obj = ExtractedEvent(
            source=source,
            confidence_score=data.get("confidence", 0.5),
            summary=data.get("summary"),
            extracted_victim_name=data.get("victim_name"),
            extracted_location=data.get("location"),
            extracted_date=event_date
        )
        db.session.add(extraction_obj)
    
    source.status = 'processed'
    db.session.commit()
    
    return {
        "success": True,
        "source_id": source_id,
        "extraction": {
            "id": extraction_obj.id,
            "summary": data.get("summary"),
            "victim_name": data.get("victim_name"),
            "location": data.get("location"),
            "date": data.get("date"),
            "confidence": data.get("confidence", 0.5),
            "keywords_matched": matches
        },
        "message": "Extraction successful"
    }


def run_extraction(force=False, limit=None, max_workers=10):
    """Stage 2: Extraction - Process pending/downloaded sources in parallel.
    
    Only processes sources that are not already marked as 'processed' (unless force=True).
    """
    # We need to access the real app object to pass to threads
    app_obj = current_app._get_current_object()
    
    query = Source.query
    if not force:
        # Only process sources that are not already marked as 'processed'
        query = query.filter(Source.status != 'processed')
    
    # Fetch IDs only to avoid DetachedInstanceError and save memory
    if limit:
        sources = query.with_entities(Source.id).limit(limit).all()
    else:
        sources = query.with_entities(Source.id).all()
        
    source_ids = [s.id for s in sources]
    total = len(source_ids)
    print(f"Processing {total} sources (Limit={limit}, Force={force}, Threads={max_workers})...")
    
    count = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        futures = {executor.submit(process_single_source, app_obj, sid, force): sid for sid in source_ids}
        
        # Process as they complete
        for i, future in enumerate(concurrent.futures.as_completed(futures)):
            sid = futures[future]
            try:
                if future.result():
                    count += 1
            except Exception as e:
                print(f"Thread error for source {sid}: {e}")
            
            # Simple progress log
            if (i + 1) % 10 == 0:
                print(f"Progress: {i + 1}/{total}")
            
    print(f"Extraction complete. Updated {count} sources.")
    return count
