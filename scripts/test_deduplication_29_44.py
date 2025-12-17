#!/usr/bin/env python3
"""
Test deduplication logic between incidents 29 and 44.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models import Incident, ExtractedEvent
from app.services.enrichment import llm_match_extraction_to_incident
from app.extensions import db
from sqlalchemy.orm import joinedload

app = create_app()

def test_deduplication_logic():
    """Test the deduplication logic used in deduplicate_incidents."""
    with app.app_context():
        # Load incidents
        incident29 = Incident.query.options(joinedload(Incident.extractions)).get(29)
        incident44 = Incident.query.options(joinedload(Incident.extractions)).get(44)
        
        if not incident29:
            print("❌ Incident 29 not found")
            return
        if not incident44:
            print("❌ Incident 44 not found")
            return
        
        print("=" * 70)
        print("TESTING DEDUPLICATION LOGIC (as used in deduplicate_incidents)")
        print("=" * 70)
        
        # Simulate what deduplicate_incidents does
        # Create a dummy extraction from incident44 to check against incident29
        dummy_extraction = ExtractedEvent(
            id=999999,  # Dummy ID
            extracted_date=incident44.date,
            extracted_victim_name=incident44.victims,
            extracted_location=f"{incident44.street or ''}, {incident44.neighborhood or ''}, {incident44.city or ''}".strip(', '),
            summary=incident44.description or incident44.title
        )
        
        print(f"\nCreating dummy extraction from Incident 44:")
        print(f"  Date: {dummy_extraction.extracted_date}")
        print(f"  Victim: {dummy_extraction.extracted_victim_name}")
        print(f"  Location: {dummy_extraction.extracted_location}")
        print(f"  Summary: {dummy_extraction.summary[:100]}...")
        
        print(f"\nTesting if Incident 44 matches Incident 29...")
        
        # Check if incident44 matches incident29 using LLM (same logic as deduplicate_incidents)
        matched_incident, confidence, reasoning = llm_match_extraction_to_incident(
            dummy_extraction, 
            [incident29]
        )
        
        print(f"\n{'='*70}")
        print("RESULTS:")
        print(f"{'='*70}")
        print(f"   Matched Incident ID: {matched_incident.id if matched_incident else None}")
        print(f"   Target Incident ID: {incident29.id}")
        print(f"   Confidence: {confidence:.2f}")
        print(f"   Threshold: 0.8")
        print(f"   Reasoning: {reasoning}")
        
        if matched_incident and matched_incident.id == incident29.id and confidence > 0.8:
            print(f"\n✅ WOULD BE MERGED by deduplicate_incidents")
        else:
            print(f"\n❌ WOULD NOT BE MERGED by deduplicate_incidents")
            if not matched_incident:
                print(f"   Reason: No match returned")
            elif matched_incident.id != incident29.id:
                print(f"   Reason: Matched wrong incident")
            elif confidence <= 0.8:
                print(f"   Reason: Confidence {confidence:.2f} <= 0.8 threshold")

if __name__ == '__main__':
    test_deduplication_logic()

