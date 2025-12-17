#!/usr/bin/env python3
"""
Merge duplicate incidents - move extractions from one incident to another and delete the duplicate.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger
from app import create_app
from app.models import Incident, ExtractedEvent
from app.services.enrichment import llm_enrich_incident
from app.extensions import db
from sqlalchemy.orm import joinedload

app = create_app()

def merge_incidents(keep_incident_id, merge_incident_id, dry_run=False):
    """Merge merge_incident into keep_incident."""
    with app.app_context():
        keep_incident = Incident.query.options(joinedload(Incident.extractions)).get(keep_incident_id)
        merge_incident = Incident.query.options(joinedload(Incident.extractions)).get(merge_incident_id)
        
        if not keep_incident:
            logger.info(f"Error: Incident {keep_incident_id} not found")
            return False
        
        if not merge_incident:
            logger.info(f"Error: Incident {merge_incident_id} not found")
            return False
        
        logger.info("=" * 70)
        logger.info("MERGING INCIDENTS")
        logger.info("=" * 70)
        logger.info(f"\nKEEPING Incident {keep_incident.id}:")
        logger.info(f"  Title: {keep_incident.title}")
        logger.info(f"  Date: {keep_incident.date.strftime('%Y-%m-%d') if keep_incident.date else 'N/A'}")
        logger.info(f"  Death count: {keep_incident.death_count}")
        logger.info(f"  Location: {keep_incident.neighborhood or 'N/A'}")
        logger.info(f"  Extractions: {len(keep_incident.extractions)}")
        
        logger.info(f"\nMERGING Incident {merge_incident.id}:")
        logger.info(f"  Title: {merge_incident.title}")
        logger.info(f"  Date: {merge_incident.date.strftime('%Y-%m-%d') if merge_incident.date else 'N/A'}")
        logger.info(f"  Death count: {merge_incident.death_count}")
        logger.info(f"  Location: {merge_incident.neighborhood or 'N/A'}")
        logger.info(f"  Extractions: {len(merge_incident.extractions)}")
        
        if dry_run:
            logger.info("\n[DRY RUN] Would merge incidents...")
            return True
        
        # Move all extractions from merge_incident to keep_incident
        moved_count = 0
        for extraction in merge_incident.extractions:
            extraction.incident_id = keep_incident.id
            moved_count += 1
        
        logger.info(f"\n✓ Moved {moved_count} extraction(s) to Incident {keep_incident.id}")
        
        # Delete merge_incident
        db.session.delete(merge_incident)
        logger.info(f"✓ Deleted Incident {merge_incident.id}")
        
        # Commit changes
        db.session.commit()
        
        # Re-enrich the kept incident with all sources
        logger.info(f"\nRe-enriching Incident {keep_incident.id}...")
        db.session.refresh(keep_incident)
        enriched = llm_enrich_incident(keep_incident)
        db.session.commit()
        
        logger.info("\n" + "=" * 70)
        logger.info("MERGE COMPLETE")
        logger.info("=" * 70)
        logger.info(f"  Kept Incident: {keep_incident.id}")
        logger.info(f"  Merged Incident: {merge_incident_id} (deleted)")
        logger.info(f"  Total extractions in kept incident: {len(keep_incident.extractions)}")
        
        return True

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Merge duplicate incidents')
    parser.add_argument('--keep', type=int, required=True, help='Incident ID to keep')
    parser.add_argument('--merge', type=int, required=True, help='Incident ID to merge and delete')
    parser.add_argument('--dry-run', action='store_true', help='Dry run (do not commit changes)')
    args = parser.parse_args()
    
    merge_incidents(args.keep, args.merge, dry_run=args.dry_run)

