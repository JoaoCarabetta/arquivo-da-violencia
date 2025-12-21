#!/usr/bin/env python3
"""
Re-extract all sources that have ExtractedEvents without death_count.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger
from app import create_app
from app.models import Source, ExtractedEvent
from app.services.extraction import extract_event
from app.extensions import db
from concurrent.futures import ThreadPoolExecutor, as_completed

app = create_app()

def re_extract_for_death_count(workers=10, limit=None):
    """Re-extract sources that have extractions without death_count."""
    with app.app_context():
        logger.info("=" * 70)
        logger.info("RE-EXTRACTION FOR DEATH_COUNT")
        logger.info("=" * 70)
        
        # Get source IDs that have extractions without death_count
        query = db.session.query(ExtractedEvent.source_id).filter(
            ExtractedEvent.death_count.is_(None)
        ).distinct()
        
        if limit:
            query = query.limit(limit)
        
        source_ids = [row[0] for row in query.all()]
        total = len(source_ids)
        
        if total == 0:
            logger.info("✅ No sources need re-extraction. All extractions already have death_count.")
            return
        
        logger.info(f"\nFound {total} sources with extractions missing death_count")
        logger.info(f"Using {workers} parallel workers...")
        logger.info("=" * 70)
        
        success_count = 0
        error_count = 0
        updated_count = 0
        
        def process_source(source_id):
            """Process a single source in its own app context."""
            with app.app_context():
                try:
                    result = extract_event(source_id, force=True)
                    if result["success"]:
                        # Check if death_count was added
                        extraction = ExtractedEvent.query.filter_by(source_id=source_id).first()
                        if extraction and extraction.death_count is not None:
                            return {"status": "success", "death_count": extraction.death_count}
                        else:
                            return {"status": "success_no_death_count"}
                    else:
                        return {"status": "failed", "error": result.get("message", "Unknown error")}
                except Exception as e:
                    return {"status": "error", "error": str(e)}
        
        # Process in parallel
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(process_source, source_id): source_id 
                      for source_id in source_ids}
            
            # Process as they complete
            for i, future in enumerate(as_completed(futures), 1):
                source_id = futures[future]
                try:
                    result = future.result()
                    
                    if result["status"] == "success":
                        success_count += 1
                        updated_count += 1
                        logger.info(f"✓ [{i}/{total}] Source {source_id}: death_count = {result.get('death_count')}")
                    elif result["status"] == "success_no_death_count":
                        success_count += 1
                        logger.info(f"⚠ [{i}/{total}] Source {source_id}: Re-extracted but no death_count found")
                    else:
                        error_count += 1
                        logger.info(f"✗ [{i}/{total}] Source {source_id}: {result.get('error', 'Unknown error')}")
                    
                    # Progress update every 10 items
                    if i % 10 == 0:
                        logger.info(f"\n📊 Progress: {i}/{total} | Success: {success_count} | Updated: {updated_count} | Errors: {error_count}\n")
                        
                except Exception as e:
                    error_count += 1
                    logger.info(f"✗ [{i}/{total}] Source {source_id}: Exception - {e}")
        
        logger.info("\n" + "=" * 70)
        logger.info("RE-EXTRACTION COMPLETE")
        logger.info("=" * 70)
        logger.info(f"  Total processed:    {total}")
        logger.info(f"  Successful:         {success_count}")
        logger.info(f"  With death_count:   {updated_count}")
        logger.info(f"  Errors:             {error_count}")
        logger.info("=" * 70)
        
        # Final statistics
        final_count = ExtractedEvent.query.filter(ExtractedEvent.death_count.isnot(None)).count()
        total_extractions = ExtractedEvent.query.count()
        logger.info(f"\nFinal statistics:")
        logger.info(f"  Total extractions:           {total_extractions}")
        logger.info(f"  With death_count:            {final_count} ({final_count/total_extractions*100:.1f}%)")
        logger.info(f"  Without death_count:          {total_extractions - final_count}")

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Re-extract sources for death_count')
    parser.add_argument('--workers', type=int, default=10, help='Number of parallel workers (default: 10)')
    parser.add_argument('--limit', type=int, help='Limit number of sources to process')
    args = parser.parse_args()
    
    re_extract_for_death_count(workers=args.workers, limit=args.limit)

