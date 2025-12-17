#!/usr/bin/env python3
"""Test extraction from CBN article to see what content is being captured."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger
from app import create_app
from app.extensions import db
from app.models import Source, ExtractedEvent
from app.services.extraction import extract_content_and_metadata, extract_event
import trafilatura

app = create_app()

url = 'https://cbn.globoradio.globo.com/media/audio/426161/pm-que-investigava-milicia-e-morta-na-zona-oeste-d.htm'

logger.info("=" * 80)
logger.info("Testing CBN Article Extraction")
logger.info("=" * 80)
logger.info(f"\nURL: {url}\n")

with app.app_context():
    # Check if source already exists
    source = Source.query.filter_by(url=url).first()
    
    if source:
        logger.info(f"Found existing source (ID: {source.id})")
        logger.info(f"Current content length: {len(source.content) if source.content else 0} characters")
        
        # Re-extract with force=True
        logger.info("\nRe-extracting with improved method...")
        result = extract_event(source.id, force=True)
        
        if result['success']:
            # Refresh source to get updated content
            db.session.refresh(source)
            logger.info(f"\n✓ Extraction successful!")
            logger.info(f"New content length: {len(source.content) if source.content else 0} characters")
            
            if source.content:
                logger.info("\n" + "=" * 80)
                logger.info("EXTRACTED CONTENT:")
                logger.info("=" * 80)
                logger.info(source.content)
                logger.info("=" * 80)
                
                # Check for key phrases that should be in both sections
                logger.info("\n" + "=" * 80)
                logger.info("CONTENT VERIFICATION:")
                logger.info("=" * 80)
                key_phrases = [
                    ("Vaneza Lobão", "Victim name"),
                    ("31 anos", "Age"),
                    ("Santa Cruz", "Location"),
                    ("Zona Oeste", "Zone"),
                    ("academia", "Gym context"),
                    ("criminosos encapuzados", "Attackers description"),
                    ("oitava Delegacia de Polícia Judiciária Militar", "Second section - her role"),
                    ("milicianos e contraventores", "Second section - what she investigated"),
                    ("Corregedoria-Geral", "Second section - department"),
                    ("Disque Denúncia", "Second section - tip line"),
                    ("R$ 5 mil", "Second section - reward"),
                    ("52 o número de agentes", "Second section - statistics")
                ]
                
                found_count = 0
                for phrase, description in key_phrases:
                    if phrase.lower() in source.content.lower():
                        logger.info(f"  ✓ Found: '{phrase}' ({description})")
                        found_count += 1
                    else:
                        logger.info(f"  ✗ Missing: '{phrase}' ({description})")
                
                logger.info(f"\nSummary: Found {found_count}/{len(key_phrases)} key phrases")
                
                if found_count >= 8:
                    logger.info("\n✅ SUCCESS: Both sections appear to be captured!")
                elif found_count >= 5:
                    logger.info("\n⚠️  PARTIAL: Some content captured, but may be missing sections")
                else:
                    logger.info("\n❌ ISSUE: Significant content may be missing")
        else:
            logger.info(f"\n✗ Extraction failed: {result['message']}")
    else:
        # Test extraction directly without database
        logger.info("Source not found in database. Testing direct extraction...")
        logger.info("\n1. Fetching HTML...")
        html = trafilatura.fetch_url(url)
        if not html:
            logger.info("ERROR: Failed to fetch URL")
            sys.exit(1)
        logger.info(f"   ✓ HTML fetched ({len(html)} characters)")
        
        # Extract using improved method
        logger.info("\n2. Extracting content using improved method...")
        content, metadata, pub_date = extract_content_and_metadata(html)
        if content:
            logger.info(f"   ✓ Content extracted ({len(content)} characters)")
            logger.info("\n" + "=" * 80)
            logger.info("EXTRACTED CONTENT:")
            logger.info("=" * 80)
            logger.info(content)
            logger.info("=" * 80)
            
            # Check for key phrases
            logger.info("\n" + "=" * 80)
            logger.info("CONTENT VERIFICATION:")
            logger.info("=" * 80)
            key_phrases = [
                ("Vaneza Lobão", "Victim name"),
                ("31 anos", "Age"),
                ("Santa Cruz", "Location"),
                ("academia", "Gym context"),
                ("oitava Delegacia de Polícia Judiciária Militar", "Second section - her role"),
                ("milicianos e contraventores", "Second section - what she investigated"),
                ("Disque Denúncia", "Second section - tip line"),
                ("R$ 5 mil", "Second section - reward")
            ]
            
            found_count = 0
            for phrase, description in key_phrases:
                if phrase.lower() in content.lower():
                    logger.info(f"  ✓ Found: '{phrase}' ({description})")
                    found_count += 1
                else:
                    logger.info(f"  ✗ Missing: '{phrase}' ({description})")
            
            logger.info(f"\nSummary: Found {found_count}/{len(key_phrases)} key phrases")
        else:
            logger.info("   ✗ No content extracted")
