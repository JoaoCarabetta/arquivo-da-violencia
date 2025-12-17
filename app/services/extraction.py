import trafilatura
import googlenewsdecoder
import vertexai
from vertexai.generative_models import GenerativeModel
from google.oauth2 import service_account
import os
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
from datetime import datetime

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
- "victim_name": string or null (name of the victim if mentioned)
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
    
    # 1. Resolve URL
    if not source.resolved_url or force:
        if not source.resolved_url: 
             print(f"Resolving {source.url}")
        resolved = resolve_url(source.url)
        if resolved != source.url:
            source.resolved_url = resolved
            changed = True
    
    target_url = source.resolved_url or source.url

    # 2. Download valid content
    if (not source.content or force) and source.status != 'failed':
        try:
            downloaded = trafilatura.fetch_url(target_url)
            if downloaded:
                content = trafilatura.extract(downloaded)
                if content:
                    source.content = content
                    source.status = 'downloaded'
                    changed = True
        except Exception as e:
             print(f"Download error: {e}")

    # 3. Identify Extractions (The Core Logic)
    if source.content:
        # A. Fast Keyword Filter
        matches = check_keywords_fast(source.content)
        
        if matches:
            # B. LLM Extraction (use published_at if available, else fetched_at)
            pub_date = source.published_at or source.fetched_at
            data, status = extract_with_llm(source.content, matches, pub_date)
            
            if data.get("is_valid"):
                # Check for existing extraction
                existing = ExtractedEvent.query.filter_by(source_id=source.id).first()
                if not existing:
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
    
    # Check if already has extraction
    existing = ExtractedEvent.query.filter_by(source_id=source_id).first()
    if existing and not force:
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
            "message": "Extraction already exists"
        }
    
    # Ensure we have content
    if not source.content:
        # Try to download content first
        target_url = source.resolved_url or source.url
        try:
            downloaded = trafilatura.fetch_url(target_url)
            if downloaded:
                content = trafilatura.extract(downloaded)
                if content:
                    source.content = content
                    source.status = 'downloaded'
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
    
    # Run LLM extraction (use published_at if available, else fetched_at)
    pub_date = source.published_at or source.fetched_at
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
    
    # If we have existing (and force=True), update it
    if existing:
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
    """Stage 2: Extraction - Process pending/downloaded sources in parallel."""
    # We need to access the real app object to pass to threads
    app_obj = current_app._get_current_object()
    
    query = Source.query
    if not force:
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
