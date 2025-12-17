#!/usr/bin/env python3
"""
Test script to verify death_count is saved to database during extraction.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models import Source, ExtractedEvent
from app.services.extraction import extract_event
from app.extensions import db

app = create_app()

def test_death_count_save():
    """Test if death_count is saved to database during extraction."""
    with app.app_context():
        print("=" * 60)
        print("Testing death_count save to database")
        print("=" * 60)
        
        # Find a source with content that mentions deaths
        print("\n[Step 1] Looking for sources with content...")
        
        sources = Source.query.filter(
            Source.content.isnot(None),
            Source.content != ''
        ).limit(5).all()
        
        if not sources:
            print("❌ No sources with content found. Please run ingestion first.")
            return
        
        print(f"Found {len(sources)} sources with content")
        
        # Try to extract from the first source
        test_source = sources[0]
        print(f"\n[Step 2] Testing extraction from Source ID {test_source.id}")
        print(f"  Title: {test_source.title or 'N/A'}")
        print(f"  URL: {test_source.url}")
        print(f"  Content preview: {test_source.content[:200] if test_source.content else 'N/A'}...")
        
        # Check if there's already an extraction
        existing_extraction = ExtractedEvent.query.filter_by(source_id=test_source.id).first()
        if existing_extraction:
            print(f"\n  Existing extraction ID {existing_extraction.id}:")
            print(f"    death_count: {existing_extraction.death_count}")
        
        # Force re-extraction
        print(f"\n[Step 3] Running extraction (force=True)...")
        try:
            result = extract_event(test_source.id, force=True)
            
            if result["success"]:
                print("✅ Extraction successful!")
                if result.get("extraction"):
                    print(f"  Summary: {result['extraction'].get('summary', 'N/A')}")
                    print(f"  Victim: {result['extraction'].get('victim_name', 'N/A')}")
                    print(f"  Location: {result['extraction'].get('location', 'N/A')}")
                    print(f"  death_count: {result['extraction'].get('death_count', 'N/A')}")
                else:
                    print(f"  Message: {result.get('message', 'N/A')}")
                    print("  (No extraction created - likely no relevant keywords found)")
                
                # Check database
                db.session.refresh(test_source)
                extraction = ExtractedEvent.query.filter_by(source_id=test_source.id).first()
                
                if extraction:
                    print(f"\n[Step 4] Verifying database record...")
                    print(f"  Extraction ID: {extraction.id}")
                    print(f"  death_count in DB: {extraction.death_count}")
                    
                    if extraction.death_count is not None:
                        print(f"\n✅ SUCCESS: death_count was saved to database: {extraction.death_count}")
                    else:
                        print(f"\n❌ FAILED: death_count is None in database")
                else:
                    print("\n❌ No extraction found in database after extraction")
            else:
                print(f"❌ Extraction failed: {result.get('message', 'Unknown error')}")
                
        except Exception as e:
            print(f"\n❌ ERROR during extraction: {e}")
            import traceback
            traceback.print_exc()
        
        print("\n" + "=" * 60)
        print("Test complete!")
        print("=" * 60)

if __name__ == '__main__':
    test_death_count_save()

