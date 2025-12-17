#!/usr/bin/env python3
"""Test extraction from CBN article to see what content is being captured."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db
from app.models import Source, ExtractedEvent
from app.services.extraction import extract_content_and_metadata, extract_event
import trafilatura

app = create_app()

url = 'https://cbn.globoradio.globo.com/media/audio/426161/pm-que-investigava-milicia-e-morta-na-zona-oeste-d.htm'

print("=" * 80)
print("Testing CBN Article Extraction")
print("=" * 80)
print(f"\nURL: {url}\n")

with app.app_context():
    # Check if source already exists
    source = Source.query.filter_by(url=url).first()
    
    if source:
        print(f"Found existing source (ID: {source.id})")
        print(f"Current content length: {len(source.content) if source.content else 0} characters")
        
        # Re-extract with force=True
        print("\nRe-extracting with improved method...")
        result = extract_event(source.id, force=True)
        
        if result['success']:
            # Refresh source to get updated content
            db.session.refresh(source)
            print(f"\n✓ Extraction successful!")
            print(f"New content length: {len(source.content) if source.content else 0} characters")
            
            if source.content:
                print("\n" + "=" * 80)
                print("EXTRACTED CONTENT:")
                print("=" * 80)
                print(source.content)
                print("=" * 80)
                
                # Check for key phrases that should be in both sections
                print("\n" + "=" * 80)
                print("CONTENT VERIFICATION:")
                print("=" * 80)
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
                        print(f"  ✓ Found: '{phrase}' ({description})")
                        found_count += 1
                    else:
                        print(f"  ✗ Missing: '{phrase}' ({description})")
                
                print(f"\nSummary: Found {found_count}/{len(key_phrases)} key phrases")
                
                if found_count >= 8:
                    print("\n✅ SUCCESS: Both sections appear to be captured!")
                elif found_count >= 5:
                    print("\n⚠️  PARTIAL: Some content captured, but may be missing sections")
                else:
                    print("\n❌ ISSUE: Significant content may be missing")
        else:
            print(f"\n✗ Extraction failed: {result['message']}")
    else:
        # Test extraction directly without database
        print("Source not found in database. Testing direct extraction...")
        print("\n1. Fetching HTML...")
        html = trafilatura.fetch_url(url)
        if not html:
            print("ERROR: Failed to fetch URL")
            sys.exit(1)
        print(f"   ✓ HTML fetched ({len(html)} characters)")
        
        # Extract using improved method
        print("\n2. Extracting content using improved method...")
        content, metadata, pub_date = extract_content_and_metadata(html)
        if content:
            print(f"   ✓ Content extracted ({len(content)} characters)")
            print("\n" + "=" * 80)
            print("EXTRACTED CONTENT:")
            print("=" * 80)
            print(content)
            print("=" * 80)
            
            # Check for key phrases
            print("\n" + "=" * 80)
            print("CONTENT VERIFICATION:")
            print("=" * 80)
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
                    print(f"  ✓ Found: '{phrase}' ({description})")
                    found_count += 1
                else:
                    print(f"  ✗ Missing: '{phrase}' ({description})")
            
            print(f"\nSummary: Found {found_count}/{len(key_phrases)} key phrases")
        else:
            print("   ✗ No content extracted")
