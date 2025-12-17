#!/usr/bin/env python3
"""
Test script to verify death_count extraction is working.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger
from app import create_app
from app.models import Source, ExtractedEvent
from app.services.extraction import extract_with_llm, extract_event
from app.extensions import db

app = create_app()

def test_death_count_extraction():
    """Test if death_count is being extracted correctly."""
    with app.app_context():
        logger.info("=" * 60)
        logger.info("Testing death_count extraction")
        logger.info("=" * 60)
        
        # Test 1: Test extract_with_llm directly with a news text that mentions multiple deaths
        logger.info("\n[Test 1] Testing extract_with_llm with explicit death count...")
        
        test_text = """
        Três pessoas foram mortas em um tiroteio na favela da Maré, na Zona Norte do Rio de Janeiro, 
        na tarde desta segunda-feira (15). Segundo a Polícia Civil, as vítimas foram identificadas 
        como João Silva, de 25 anos, Maria Santos, de 30 anos, e Pedro Costa, de 28 anos. 
        O crime ocorreu por volta das 14h na Rua Principal. A polícia investiga o caso.
        """
        
        matches = ["morto", "vítimas", "tiroteio"]
        
        try:
            result, status = extract_with_llm(test_text, matches)
            
            logger.info(f"Status: {status}")
            logger.info(f"is_valid: {result.get('is_valid')}")
            logger.info(f"summary: {result.get('summary')}")
            logger.info(f"victim_name: {result.get('victim_name')}")
            logger.info(f"death_count: {result.get('death_count')}")
            logger.info(f"location: {result.get('location')}")
            logger.info(f"date: {result.get('date')}")
            
            if result.get('death_count') is not None:
                logger.info(f"\n✅ SUCCESS: death_count was extracted: {result.get('death_count')}")
                if result.get('death_count') == 3:
                    logger.info("✅ CORRECT: death_count matches expected value (3)")
                else:
                    logger.info(f"⚠️  WARNING: death_count is {result.get('death_count')}, expected 3")
            else:
                logger.info("\n❌ FAILED: death_count was not extracted (returned None)")
                
        except Exception as e:
            logger.info(f"\n❌ ERROR: {e}")
            import traceback
            traceback.print_exc()
        
        # Test 2: Test with a single death
        logger.info("\n" + "=" * 60)
        logger.info("[Test 2] Testing with single death mention...")
        
        test_text2 = """
        Um homem foi morto a tiros na Rua das Flores, em Copacabana, na manhã desta terça-feira (16).
        A vítima foi identificada como Carlos Oliveira, de 35 anos. A polícia investiga o caso.
        """
        
        try:
            result2, status2 = extract_with_llm(test_text2, matches)
            
            logger.info(f"Status: {status2}")
            logger.info(f"death_count: {result2.get('death_count')}")
            
            if result2.get('death_count') is not None:
                logger.info(f"\n✅ SUCCESS: death_count was extracted: {result2.get('death_count')}")
                if result2.get('death_count') == 1:
                    logger.info("✅ CORRECT: death_count matches expected value (1)")
                else:
                    logger.info(f"⚠️  WARNING: death_count is {result2.get('death_count')}, expected 1")
            else:
                logger.info("\n❌ FAILED: death_count was not extracted (returned None)")
                
        except Exception as e:
            logger.info(f"\n❌ ERROR: {e}")
            import traceback
            traceback.print_exc()
        
        # Test 3: Check existing extractions in database
        logger.info("\n" + "=" * 60)
        logger.info("[Test 3] Checking existing ExtractedEvents in database...")
        
        extractions = ExtractedEvent.query.limit(10).all()
        logger.info(f"Found {len(extractions)} extractions in database")
        
        if extractions:
            logger.info("\nRecent extractions with death_count:")
            for ext in extractions[:5]:
                logger.info(f"  - Extraction ID {ext.id}: death_count = {ext.death_count}")
                if ext.death_count is not None:
                    logger.info(f"    ✅ Has death_count: {ext.death_count}")
                else:
                    logger.info(f"    ⚠️  No death_count (None)")
        else:
            logger.info("No extractions found in database. Run extraction first.")
        
        logger.info("\n" + "=" * 60)
        logger.info("Test complete!")
        logger.info("=" * 60)

if __name__ == '__main__':
    test_death_count_extraction()

