#!/usr/bin/env python3
"""
Re-extract sources related to duplicate incidents (121 deaths in Penha/Alemão)
to verify if dates are now extracted correctly.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger
from app import create_app
from app.models import Source, ExtractedEvent, Incident
from app.services.extraction import extract_event
from app.extensions import db
from sqlalchemy import or_
from sqlalchemy.orm import joinedload

app = create_app()

def find_duplicate_incidents():
    """Find incidents with 121 deaths in Penha/Alemão."""
    with app.app_context():
        # Find incidents with death_count = 121 and location containing Penha or Alemão
        incidents = Incident.query.filter(
            Incident.death_count == 121
        ).all()
        
        # Filter by location
        matching_incidents = []
        for incident in incidents:
            location_text = " ".join([
                incident.neighborhood or "",
                incident.location_extra_info or "",
                incident.description or "",
                incident.title or ""
            ]).lower()
            
            if "penha" in location_text or "alemão" in location_text:
                matching_incidents.append(incident)
        
        return matching_incidents

def re_extract_for_incidents(incident_ids=None):
    """Re-extract sources related to specific incidents."""
    with app.app_context():
        logger.info("=" * 70)
        logger.info("RE-EXTRACTION FOR DUPLICATE INCIDENTS")
        logger.info("=" * 70)
        
        if incident_ids:
            incidents = Incident.query.options(joinedload(Incident.extractions)).filter(Incident.id.in_(incident_ids)).all()
        else:
            # Find incidents with 121 deaths in Penha/Alemão
            incidents = find_duplicate_incidents()
            # Reload with extractions
            incident_ids_list = [inc.id for inc in incidents]
            incidents = Incident.query.options(joinedload(Incident.extractions)).filter(Incident.id.in_(incident_ids_list)).all()
        
        if not incidents:
            logger.info("No matching incidents found.")
            return
        
        logger.info(f"\nFound {len(incidents)} incident(s) to check:")
        for incident in incidents:
            logger.info(f"  - Incident {incident.id}: {incident.title}")
            logger.info(f"    Date: {incident.date.strftime('%Y-%m-%d') if incident.date else 'N/A'}")
            logger.info(f"    Death count: {incident.death_count}")
            logger.info(f"    Location: {incident.neighborhood or 'N/A'}")
            logger.info(f"    Extractions: {len(incident.extractions)}")
        
        # Get all extractions from these incidents
        extraction_ids = []
        for incident in incidents:
            for extraction in incident.extractions:
                extraction_ids.append(extraction.id)
        
        if not extraction_ids:
            logger.info("\nNo extractions found for these incidents.")
            return
        
        # Get all source IDs from these extractions
        extractions = ExtractedEvent.query.filter(
            ExtractedEvent.id.in_(extraction_ids)
        ).all()
        
        source_ids = list(set([ext.source_id for ext in extractions]))
        
        logger.info(f"\nFound {len(source_ids)} unique source(s) to re-extract")
        logger.info("=" * 70)
        
        # Show current extraction dates
        logger.info("\nBEFORE RE-EXTRACTION:")
        for extraction in extractions:
            logger.info(f"  Extraction {extraction.id} (Source {extraction.source_id}):")
            logger.info(f"    Date: {extraction.extracted_date.strftime('%Y-%m-%d') if extraction.extracted_date else 'N/A'}")
            logger.info(f"    Death count: {extraction.death_count}")
            logger.info(f"    Location: {extraction.extracted_location or 'N/A'}")
            logger.info(f"    Summary: {extraction.summary[:80] if extraction.summary else 'N/A'}...")
        
        logger.info("\n" + "=" * 70)
        logger.info("RE-EXTRACTING...")
        logger.info("=" * 70)
        
        success_count = 0
        error_count = 0
        updated_dates = []
        
        for i, source_id in enumerate(source_ids, 1):
            try:
                result = extract_event(source_id, force=True)
                if result["success"]:
                    extraction = ExtractedEvent.query.filter_by(source_id=source_id).first()
                    if extraction:
                        old_date = None
                        # Find old date from the list above
                        for old_ext in extractions:
                            if old_ext.source_id == source_id:
                                old_date = old_ext.extracted_date
                                break
                        
                        new_date = extraction.extracted_date
                        
                        if old_date != new_date:
                            updated_dates.append({
                                "source_id": source_id,
                                "extraction_id": extraction.id,
                                "old_date": old_date.strftime('%Y-%m-%d') if old_date else 'N/A',
                                "new_date": new_date.strftime('%Y-%m-%d') if new_date else 'N/A',
                                "death_count": extraction.death_count
                            })
                            logger.info(f"✓ [{i}/{len(source_ids)}] Source {source_id}: Date changed from {old_date.strftime('%Y-%m-%d') if old_date else 'N/A'} to {new_date.strftime('%Y-%m-%d') if new_date else 'N/A'}")
                        else:
                            logger.info(f"  [{i}/{len(source_ids)}] Source {source_id}: Date unchanged ({new_date.strftime('%Y-%m-%d') if new_date else 'N/A'})")
                        
                        success_count += 1
                    else:
                        logger.info(f"⚠ [{i}/{len(source_ids)}] Source {source_id}: No extraction found after re-extraction")
                else:
                    error_count += 1
                    logger.info(f"✗ [{i}/{len(source_ids)}] Source {source_id}: {result.get('message', 'Unknown error')}")
            except Exception as e:
                error_count += 1
                logger.info(f"✗ [{i}/{len(source_ids)}] Source {source_id}: Exception - {e}")
        
        logger.info("\n" + "=" * 70)
        logger.info("RE-EXTRACTION COMPLETE")
        logger.info("=" * 70)
        logger.info(f"  Total sources:      {len(source_ids)}")
        logger.info(f"  Successful:         {success_count}")
        logger.info(f"  Errors:             {error_count}")
        logger.info(f"  Dates changed:      {len(updated_dates)}")
        
        if updated_dates:
            logger.info("\n  DATE CHANGES:")
            for change in updated_dates:
                logger.info(f"    Source {change['source_id']}: {change['old_date']} → {change['new_date']} (death_count: {change['death_count']})")
        
        # Show updated extraction dates
        logger.info("\nAFTER RE-EXTRACTION:")
        updated_extractions = ExtractedEvent.query.filter(
            ExtractedEvent.id.in_(extraction_ids)
        ).all()
        
        for extraction in updated_extractions:
            logger.info(f"  Extraction {extraction.id} (Source {extraction.source_id}):")
            logger.info(f"    Date: {extraction.extracted_date.strftime('%Y-%m-%d') if extraction.extracted_date else 'N/A'}")
            logger.info(f"    Death count: {extraction.death_count}")
            logger.info(f"    Location: {extraction.extracted_location or 'N/A'}")
        
        logger.info("=" * 70)

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Re-extract sources for duplicate incidents')
    parser.add_argument('--incident-ids', type=int, nargs='+', help='Specific incident IDs to re-extract (optional)')
    args = parser.parse_args()
    
    re_extract_for_incidents(incident_ids=args.incident_ids)

