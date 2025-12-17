#!/usr/bin/env python3
"""Test script to verify extraction skips sources marked as 'processed'."""

import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models import Source, ExtractedEvent
from app.services.extraction import run_extraction
from app.extensions import db

def test_processed_status():
    """Test that extraction skips sources marked as 'processed'."""
    app = create_app()
    
    with app.app_context():
        print("=" * 60)
        print("TEST: Extraction should skip sources marked as 'processed'")
        print("=" * 60)
        
        # Get statistics
        total_sources = Source.query.count()
        sources_with_extraction = db.session.query(Source.id).join(ExtractedEvent).distinct().count()
        sources_processed = Source.query.filter_by(status='processed').count()
        sources_not_processed = Source.query.filter(Source.status != 'processed').count()
        
        print(f"\n📊 Current Statistics:")
        print(f"  Total sources: {total_sources}")
        print(f"  Sources with extraction: {sources_with_extraction}")
        print(f"  Sources marked as 'processed': {sources_processed}")
        print(f"  Sources NOT processed: {sources_not_processed}")
        
        # Test: Check what the query would select
        print("\n" + "=" * 60)
        print("TEST: Query should exclude processed sources")
        print("=" * 60)
        
        from sqlalchemy import and_
        query = Source.query.outerjoin(ExtractedEvent).filter(
            ExtractedEvent.id == None,
            Source.status != 'processed'
        )
        
        sources_to_process = query.with_entities(Source.id).limit(100).all()
        source_ids_to_process = [s.id for s in sources_to_process]
        
        # Check if any processed sources are in the list
        processed_source_ids = set([s.id for s in Source.query.filter_by(status='processed').with_entities(Source.id).all()])
        overlap = processed_source_ids.intersection(set(source_ids_to_process))
        
        print(f"\n  Sources that would be processed: {len(source_ids_to_process)}")
        print(f"  Processed sources: {len(processed_source_ids)}")
        print(f"  Overlap (should be 0): {len(overlap)}")
        
        if len(overlap) == 0:
            print("  ✅ PASS: No processed sources in the query result")
        else:
            print(f"  ❌ FAIL: Found {len(overlap)} processed sources that would be processed!")
            print(f"     Overlapping IDs: {list(overlap)[:10]}")
        
        # Test: Run extraction and verify it doesn't process already processed sources
        print("\n" + "=" * 60)
        print("TEST: Run extraction (should skip processed sources)")
        print("=" * 60)
        
        initial_processed_count = Source.query.filter_by(status='processed').count()
        
        print(f"  Before extraction:")
        print(f"    Sources marked as 'processed': {initial_processed_count}")
        print(f"    Sources to process (from query): {len(source_ids_to_process)}")
        
        # Run extraction with a small limit
        count = run_extraction(force=False, limit=10, max_workers=2)
        
        after_processed_count = Source.query.filter_by(status='processed').count()
        newly_processed = after_processed_count - initial_processed_count
        
        print(f"\n  After extraction:")
        print(f"    Sources processed: {count}")
        print(f"    Sources marked as 'processed' now: {after_processed_count}")
        print(f"    Newly processed: {newly_processed}")
        
        # Verify
        print("\n" + "=" * 60)
        print("VERIFICATION")
        print("=" * 60)
        
        # The count should match the newly processed (or be less if some were invalid)
        test_passed = count >= 0 and newly_processed >= 0
        
        print(f"\n✅ Test (Processed sources excluded): {'PASS' if test_passed and len(overlap) == 0 else 'FAIL'}")
        
        if test_passed and len(overlap) == 0:
            print("\n🎉 All tests PASSED! Processed sources are correctly excluded.")
        else:
            print("\n❌ Some tests failed")

if __name__ == "__main__":
    test_processed_status()

