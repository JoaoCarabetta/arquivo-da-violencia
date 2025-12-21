#!/usr/bin/env python3
"""
Test script to verify death_count is saved to database during extraction.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger
from app import create_app
from app.models import Source, ExtractedEvent
from app.services.extraction import extract_event
from app.extensions import db

app = create_app()

def test_death_count_save():
    """Test if death_count is saved to database during extraction."""
    with app.app_context():
        logger.info("=" * 60)
        logger.info("Testing death_count save to database")
        logger.info("=" * 60)
        
        # Find a source with content that mentions deaths
        logger.info("\n[Step 1] Looking for sources with content...")
        
        sources = Source.query.filter(
            Source.content.isnot(None),
            Source.content != ''
        ).limit(5).all()
        
        if not sources:
            logger.info("❌ No sources with content found. Please run ingestion first.")
            return
        
        logger.info(f"Found {len(sources)} sources with content")
        
        # Try to extract from the first source
        test_source = sources[0]
        logger.info(f"\n[Step 2] Testing extraction from Source ID {test_source.id}")
        logger.info(f"  Title: {test_source.title or 'N/A'}")
        logger.info(f"  URL: {test_source.url}")
        logger.info(f"  Content preview: {test_source.content[:200] if test_source.content else 'N/A'}...")
        
        # Check if there's already an extraction
        existing_extraction = ExtractedEvent.query.filter_by(source_id=test_source.id).first()
        if existing_extraction:
            logger.info(f"\n  Existing extraction ID {existing_extraction.id}:")
            logger.info(f"    death_count: {existing_extraction.death_count}")
        
        # Force re-extraction
        logger.info(f"\n[Step 3] Running extraction (force=True)...")
        try:
            result = extract_event(test_source.id, force=True)
            
            if result["success"]:
                logger.info("✅ Extraction successful!")
                if result.get("extraction"):
                    logger.info(f"  Summary: {result['extraction'].get('summary', 'N/A')}")
                    logger.info(f"  Victim: {result['extraction'].get('victim_name', 'N/A')}")
                    logger.info(f"  Location: {result['extraction'].get('location', 'N/A')}")
                    logger.info(f"  death_count: {result['extraction'].get('death_count', 'N/A')}")
                else:
                    logger.info(f"  Message: {result.get('message', 'N/A')}")
                    logger.info("  (No extraction created - likely no relevant keywords found)")
                
                # Check database
                db.session.refresh(test_source)
                extraction = ExtractedEvent.query.filter_by(source_id=test_source.id).first()
                
                if extraction:
                    logger.info(f"\n[Step 4] Verifying database record...")
                    logger.info(f"  Extraction ID: {extraction.id}")
                    logger.info(f"  death_count in DB: {extraction.death_count}")
                    
                    if extraction.death_count is not None:
                        logger.info(f"\n✅ SUCCESS: death_count was saved to database: {extraction.death_count}")
                    else:
                        logger.info(f"\n❌ FAILED: death_count is None in database")
                else:
                    logger.info("\n❌ No extraction found in database after extraction")
            else:
                logger.info(f"❌ Extraction failed: {result.get('message', 'Unknown error')}")
                
        except Exception as e:
            logger.info(f"\n❌ ERROR during extraction: {e}")
            import traceback
            traceback.print_exc()
        
        logger.info("\n" + "=" * 60)
        logger.info("Test complete!")
        logger.info("=" * 60)

if __name__ == '__main__':
    test_death_count_save()

