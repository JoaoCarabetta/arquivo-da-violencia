#!/usr/bin/env python3
"""
Test the improved prompt with various edge cases to ensure robustness.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models import Incident, ExtractedEvent
from app.services.enrichment import llm_match_extraction_to_incident
from app.extensions import db
from datetime import datetime
from sqlalchemy.orm import joinedload

app = create_app()

def test_edge_cases():
    """Test the prompt with various edge cases."""
    with app.app_context():
        print("=" * 70)
        print("TESTING PROMPT ROBUSTNESS WITH EDGE CASES")
        print("=" * 70)
        
        # Test case 1: Same victim, date, location, but different descriptions
        print("\n" + "=" * 70)
        print("TEST CASE 1: Same victim/date/location, different crime methods")
        print("=" * 70)
        
        incident1 = Incident(
            id=9991,
            title="Assassinato de João Silva",
            date=datetime(2025, 1, 15),
            victims="João Silva, 40 anos",
            neighborhood="Copacabana",
            city="Rio de Janeiro",
            description="João Silva foi assassinado com tiro na cabeça em Copacabana."
        )
        
        extraction1 = ExtractedEvent(
            id=9991,
            extracted_date=datetime(2025, 1, 15),
            extracted_victim_name="João Silva, 40 anos",
            extracted_location="Copacabana, Rio de Janeiro",
            summary="João Silva foi morto por envenenamento em Copacabana."
        )
        
        matched, conf, reason = llm_match_extraction_to_incident(extraction1, [incident1])
        print(f"Result: {'✅ MATCH' if matched and matched.id == incident1.id else '❌ NO MATCH'}")
        print(f"Confidence: {conf:.2f}")
        print(f"Reasoning: {reason}")
        
        # Test case 2: Same victim, date, location, but one mentions more details
        print("\n" + "=" * 70)
        print("TEST CASE 2: Same victim/date/location, one has more details")
        print("=" * 70)
        
        incident2 = Incident(
            id=9992,
            title="Morte de Maria Santos",
            date=datetime(2025, 2, 20),
            victims="Maria Santos",
            neighborhood="Ipanema",
            city="Rio de Janeiro",
            description="Maria Santos foi assassinada. A polícia investiga."
        )
        
        extraction2 = ExtractedEvent(
            id=9992,
            extracted_date=datetime(2025, 2, 20),
            extracted_victim_name="Maria Santos",
            extracted_location="Ipanema, Rio de Janeiro",
            summary="Maria Santos foi assassinada por seu ex-marido com faca. A polícia prendeu o suspeito."
        )
        
        matched, conf, reason = llm_match_extraction_to_incident(extraction2, [incident2])
        print(f"Result: {'✅ MATCH' if matched and matched.id == incident2.id else '❌ NO MATCH'}")
        print(f"Confidence: {conf:.2f}")
        print(f"Reasoning: {reason}")
        
        # Test case 3: Different victims (should NOT match)
        print("\n" + "=" * 70)
        print("TEST CASE 3: Different victims, same date/location (should NOT match)")
        print("=" * 70)
        
        incident3 = Incident(
            id=9993,
            title="Morte de Pedro Costa",
            date=datetime(2025, 3, 10),
            victims="Pedro Costa",
            neighborhood="Leblon",
            city="Rio de Janeiro",
            description="Pedro Costa foi assassinado."
        )
        
        extraction3 = ExtractedEvent(
            id=9993,
            extracted_date=datetime(2025, 3, 10),
            extracted_victim_name="Ana Lima",
            extracted_location="Leblon, Rio de Janeiro",
            summary="Ana Lima foi assassinada."
        )
        
        matched, conf, reason = llm_match_extraction_to_incident(extraction3, [incident3])
        print(f"Result: {'❌ WRONG MATCH' if matched else '✅ CORRECTLY NO MATCH'}")
        print(f"Confidence: {conf:.2f}")
        print(f"Reasoning: {reason}")

if __name__ == '__main__':
    test_edge_cases()

