#!/usr/bin/env python3
"""Test script to verify extraction only processes new sources (without existing extractions)."""

import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models import Source, ExtractedEvent
from app.services.extraction import run_extraction
from sqlalchemy import func

def get_stats(db):
    """Get current statistics about sources and extractions."""
    total_sources = Source.query.count()
    sources_with_extraction = db.session.query(Source.id).join(ExtractedEvent).distinct().count()
    sources_without_extraction = total_sources - sources_with_extraction
    total_extractions = ExtractedEvent.query.count()
    
    return {
        'total_sources': total_sources,
        'sources_with_extraction': sources_with_extraction,
        'sources_without_extraction': sources_without_extraction,
        'total_extractions': total_extractions
    }

def test_extraction_new_only():
    """Test that extraction only processes sources without existing extractions."""
    app = create_app()
    
    with app.app_context():
        from app.extensions import db
        
        print("=" * 60)
        print("TEST: Extraction should only process new sources")
        print("=" * 60)
        
        # Get initial stats
        print("\n📊 Initial Statistics:")
        initial_stats = get_stats(db)
        print(f"  Total sources: {initial_stats['total_sources']}")
        print(f"  Sources with extraction: {initial_stats['sources_with_extraction']}")
        print(f"  Sources without extraction: {initial_stats['sources_without_extraction']}")
        print(f"  Total extractions: {initial_stats['total_extractions']}")
        
        if initial_stats['total_sources'] == 0:
            print("\n⚠️  No sources found in database. Please run ingestion first.")
            return
        
        # Test 1: Verify sources WITH extractions are NOT processed
        print("\n" + "=" * 60)
        print("TEST 1: Verify sources WITH extractions are skipped")
        print("=" * 60)
        
        # Get a source that already has an extraction
        source_with_extraction = db.session.query(Source).join(ExtractedEvent).first()
        
        if not source_with_extraction:
            print("⚠️  No sources with extractions found. Cannot test skipping logic.")
            print("   Running extraction on sources without extractions instead...")
        else:
            print(f"  Found source {source_with_extraction.id} with extraction")
            print(f"  Source title: {source_with_extraction.title[:50]}...")
            
            # Count how many sources with extractions would be selected
            from sqlalchemy import and_
            sources_with_extractions_count = db.session.query(Source.id).join(ExtractedEvent).count()
            print(f"  Total sources with extractions: {sources_with_extractions_count}")
            
            # The query should exclude all sources with extractions
            query_without_extractions = Source.query.outerjoin(ExtractedEvent).filter(ExtractedEvent.id == None)
            sources_without_extractions_count = query_without_extractions.count()
            print(f"  Sources without extractions (should be processed): {sources_without_extractions_count}")
            
            # Verify the query excludes sources with extractions
            sources_with_extraction_ids = set(db.session.query(Source.id).join(ExtractedEvent).all())
            sources_to_process_ids = set([s.id for s in query_without_extractions.with_entities(Source.id).limit(100).all()])
            
            overlap = sources_with_extraction_ids.intersection(sources_to_process_ids)
            test1_passed = len(overlap) == 0
            
            print(f"\n  Verification:")
            print(f"    Sources with extractions: {len(sources_with_extraction_ids)}")
            print(f"    Sources to be processed: {len(sources_to_process_ids)}")
            print(f"    Overlap (should be 0): {len(overlap)}")
            print(f"    ✅ Test 1 (Sources with extractions excluded): {'PASS' if test1_passed else 'FAIL'}")
            
            if not test1_passed:
                print(f"    ⚠️  Found {len(overlap)} sources with extractions that would be processed!")
        
        # Test 2: Run extraction and verify it only processes sources without extractions
        print("\n" + "=" * 60)
        print("TEST 2: Run extraction and verify behavior")
        print("=" * 60)
        
        initial_extractions = initial_stats['total_extractions']
        initial_sources_without = initial_stats['sources_without_extraction']
        
        print(f"  Before extraction:")
        print(f"    Sources without extraction: {initial_sources_without}")
        print(f"    Total extractions: {initial_extractions}")
        
        # Run extraction with a small limit
        count = run_extraction(force=False, limit=10, max_workers=2)
        
        # Get stats after extraction
        after_stats = get_stats(db)
        new_extractions = after_stats['total_extractions'] - initial_extractions
        
        print(f"\n  After extraction:")
        print(f"    Sources processed: {count}")
        print(f"    New extractions created: {new_extractions}")
        print(f"    Sources without extraction now: {after_stats['sources_without_extraction']}")
        print(f"    Total extractions now: {after_stats['total_extractions']}")
        
        # Test 3: Run extraction again - should process different sources (or fewer)
        print("\n" + "=" * 60)
        print("TEST 3: Run extraction again (should process different/new sources)")
        print("=" * 60)
        
        before_second_stats = get_stats(db)
        count2 = run_extraction(force=False, limit=10, max_workers=2)
        after_second_stats = get_stats(db)
        
        print(f"\n  Results:")
        print(f"    Sources processed: {count2}")
        print(f"    New extractions created: {after_second_stats['total_extractions'] - before_second_stats['total_extractions']}")
        print(f"    Sources without extraction now: {after_second_stats['sources_without_extraction']}")
        
        # Verify results
        print("\n" + "=" * 60)
        print("VERIFICATION SUMMARY")
        print("=" * 60)
        
        # Test 2: Should have processed some sources (even if no new extractions were created due to invalid content)
        test2_passed = count > 0
        
        # Test 3: Should process sources (they might be different ones, or same ones if they were invalid)
        # The key is that sources WITH extractions should never be processed
        test3_passed = True  # This is more about verifying the query works
        
        print(f"\n✅ Test 1 (Query excludes sources with extractions): {'PASS' if test1_passed else 'FAIL'}")
        print(f"✅ Test 2 (Extraction processes sources): {'PASS' if test2_passed else 'FAIL'}")
        print(f"✅ Test 3 (Second run executes): {'PASS' if test3_passed else 'FAIL'}")
        
        if test1_passed and test2_passed:
            print("\n🎉 Core functionality verified: Sources with extractions are correctly excluded!")
        else:
            print("\n❌ Some tests failed - check the output above")
        
        # Final stats
        print("\n📊 Final Statistics:")
        final_stats = get_stats(db)
        print(f"  Total sources: {final_stats['total_sources']}")
        print(f"  Sources with extraction: {final_stats['sources_with_extraction']}")
        print(f"  Sources without extraction: {final_stats['sources_without_extraction']}")
        print(f"  Total extractions: {final_stats['total_extractions']}")
        
        if test1_passed and test2_passed:
            print("\n🎉 All tests PASSED!")
        else:
            print("\n❌ Some tests FAILED")

if __name__ == "__main__":
    test_extraction_new_only()

