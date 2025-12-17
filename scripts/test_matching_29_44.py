#!/usr/bin/env python3
"""
Test matching between incidents 29 and 44 to diagnose and fix the prompt.
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

def test_matching_29_44():
    """Test if incidents 29 and 44 match using the current LLM matching logic."""
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
        print("TESTING MATCH BETWEEN INCIDENTS 29 AND 44")
        print("=" * 70)
        
        print(f"\nINCIDENT 29:")
        print(f"  ID: {incident29.id}")
        print(f"  Title: {incident29.title}")
        print(f"  Date: {incident29.date.strftime('%Y-%m-%d') if incident29.date else 'N/A'}")
        print(f"  Victims: {incident29.victims or 'N/A'}")
        print(f"  Location: {incident29.neighborhood or 'N/A'}, {incident29.city or 'N/A'}")
        print(f"  Description: {incident29.description[:200] if incident29.description else 'N/A'}...")
        print(f"  Extractions: {len(incident29.extractions)}")
        
        print(f"\nINCIDENT 44:")
        print(f"  ID: {incident44.id}")
        print(f"  Title: {incident44.title}")
        print(f"  Date: {incident44.date.strftime('%Y-%m-%d') if incident44.date else 'N/A'}")
        print(f"  Victims: {incident44.victims or 'N/A'}")
        print(f"  Location: {incident44.neighborhood or 'N/A'}, {incident44.city or 'N/A'}")
        print(f"  Description: {incident44.description[:200] if incident44.description else 'N/A'}...")
        print(f"  Extractions: {len(incident44.extractions)}")
        
        # Create a dummy extraction from incident44 to test matching against incident29
        dummy_extraction = ExtractedEvent(
            id=999999,
            extracted_date=incident44.date,
            extracted_victim_name=incident44.victims,
            extracted_location=f"{incident44.street or ''}, {incident44.neighborhood or ''}, {incident44.city or ''}".strip(', '),
            summary=incident44.description or incident44.title
        )
        
        print("\n" + "=" * 70)
        print("TESTING LLM MATCHING")
        print("=" * 70)
        print(f"\nTesting if Incident 44 (as extraction) matches Incident 29...")
        
        # Test matching
        matched_incident, confidence, reasoning = llm_match_extraction_to_incident(
            dummy_extraction,
            [incident29]
        )
        
        print(f"\n{'='*70}")
        print("RESULTS:")
        print(f"{'='*70}")
        if matched_incident and matched_incident.id == incident29.id:
            print(f"✅ MATCH FOUND!")
            print(f"   Confidence: {confidence:.2f}")
            print(f"   Reasoning: {reasoning}")
        else:
            print(f"❌ NO MATCH")
            print(f"   Confidence: {confidence:.2f}")
            print(f"   Reasoning: {reasoning}")
            print(f"\n⚠️  This indicates the prompt needs improvement!")

if __name__ == '__main__':
    test_matching_29_44()

