"""
Enrichment Service - Stage 3 of the Pipeline

Links ExtractedEvents to Incidents, handling deduplication.

Deduplication Strategy:
1. Block by date (±1 day) and city to find candidates
2. Score based on victim name (fuzzy), neighborhood, and summary similarity
3. Link to existing Incident if score > threshold, else create new Incident
"""
from difflib import SequenceMatcher
from datetime import datetime, timedelta
from app.extensions import db
from app.models import ExtractedEvent, Incident


# --- Configuration ---
DATE_TOLERANCE_DAYS = 1
MATCH_THRESHOLD = 0.6  # Score above this = same incident
VICTIM_NAME_WEIGHT = 0.5
LOCATION_WEIGHT = 0.3
SUMMARY_WEIGHT = 0.2


def normalize_text(text):
    """Normalize text for comparison."""
    if not text:
        return ""
    return text.lower().strip()


def fuzzy_match_score(str1, str2):
    """Calculate fuzzy match score between two strings (0.0 - 1.0)."""
    s1 = normalize_text(str1)
    s2 = normalize_text(str2)
    
    if not s1 or not s2:
        return 0.0
    
    return SequenceMatcher(None, s1, s2).ratio()


def extract_neighborhood(location):
    """Extract neighborhood from a location string.
    
    Common patterns in Rio:
    - "Rua X, Bairro Y, Rio de Janeiro"
    - "Bairro Y"
    - "Comunidade Z"
    """
    if not location:
        return None
        
    # Common neighborhood indicators
    indicators = ["bairro", "comunidade", "morro", "favela", "complexo"]
    loc_lower = location.lower()
    
    for indicator in indicators:
        if indicator in loc_lower:
            # Try to extract the part after the indicator
            parts = loc_lower.split(indicator)
            if len(parts) > 1:
                # Clean up and return
                neighborhood = parts[1].split(",")[0].strip()
                return neighborhood if neighborhood else None
    
    # If no indicator, return the whole location (might be just a neighborhood name)
    return location.strip()


def calculate_match_score(extraction, incident):
    """
    Calculate how likely an extraction matches an existing incident.
    
    Returns a score from 0.0 to 1.0.
    """
    score = 0.0
    components = []
    
    # 1. Victim Name Match (highest weight)
    if extraction.extracted_victim_name and incident.title:
        # Often the incident title contains the victim name
        name_score = fuzzy_match_score(
            extraction.extracted_victim_name, 
            incident.title
        )
        # Also try matching against description if available
        if incident.description:
            desc_score = fuzzy_match_score(
                extraction.extracted_victim_name,
                incident.description
            )
            name_score = max(name_score, desc_score)
        
        score += name_score * VICTIM_NAME_WEIGHT
        components.append(f"victim={name_score:.2f}")
    
    # 2. Location Match
    if extraction.extracted_location and incident.location:
        loc_score = fuzzy_match_score(
            extraction.extracted_location,
            incident.location
        )
        # Try neighborhood comparison
        ext_neighborhood = extract_neighborhood(extraction.extracted_location)
        inc_neighborhood = incident.neighborhood or extract_neighborhood(incident.location)
        
        if ext_neighborhood and inc_neighborhood:
            neighborhood_score = fuzzy_match_score(ext_neighborhood, inc_neighborhood)
            loc_score = max(loc_score, neighborhood_score)
        
        score += loc_score * LOCATION_WEIGHT
        components.append(f"location={loc_score:.2f}")
    
    # 3. Summary/Description Similarity
    if extraction.summary and incident.description:
        summary_score = fuzzy_match_score(extraction.summary, incident.description)
        score += summary_score * SUMMARY_WEIGHT
        components.append(f"summary={summary_score:.2f}")
    
    return score, components


def find_candidate_incidents(extraction):
    """
    Find existing incidents that could potentially match this extraction.
    
    Uses blocking by date and city to reduce comparison space.
    """
    candidates = []
    
    # If we don't have a date, we can't reliably deduplicate
    if not extraction.extracted_date:
        return candidates
    
    # Date range for blocking
    min_date = extraction.extracted_date - timedelta(days=DATE_TOLERANCE_DAYS)
    max_date = extraction.extracted_date + timedelta(days=DATE_TOLERANCE_DAYS)
    
    # Query incidents in date range
    # Note: We assume city is always Rio de Janeiro for now
    query = Incident.query.filter(
        Incident.date.isnot(None),
        Incident.date >= min_date,
        Incident.date <= max_date
    )
    
    candidates = query.all()
    return candidates


def find_matching_incident(extraction):
    """
    Find a matching incident for an extraction using fuzzy matching.
    
    Returns (incident, score) if match found, (None, 0) otherwise.
    """
    candidates = find_candidate_incidents(extraction)
    
    if not candidates:
        return None, 0.0
    
    best_match = None
    best_score = 0.0
    
    for incident in candidates:
        score, components = calculate_match_score(extraction, incident)
        
        if score > best_score:
            best_score = score
            best_match = incident
            
        # Debug logging
        if score > 0.3:  # Only log potentially interesting matches
            print(f"  Candidate: Incident {incident.id} ({incident.title[:30]}...) "
                  f"Score: {score:.2f} [{', '.join(components)}]")
    
    if best_score >= MATCH_THRESHOLD:
        return best_match, best_score
    
    return None, best_score


def create_incident_from_extraction(extraction):
    """Create a new Incident from an ExtractedEvent."""
    # Use victim name for title if available, otherwise use a generic title
    if extraction.extracted_victim_name:
        title = f"Morte de {extraction.extracted_victim_name}"
    else:
        title = f"Homicídio - {extraction.extracted_date.strftime('%d/%m/%Y') if extraction.extracted_date else 'Data desconhecida'}"
    
    # Extract neighborhood
    neighborhood = extract_neighborhood(extraction.extracted_location)
    
    incident = Incident(
        title=title,
        date=extraction.extracted_date,
        location=extraction.extracted_location,
        city="Rio de Janeiro",
        neighborhood=neighborhood,
        description=extraction.summary,
        confirmed=False  # Requires manual review
    )
    
    return incident


def run_enrichment(auto_create=True, dry_run=False):
    """
    Stage 3: Enrichment - Link Extractions to Incidents.
    
    Args:
        auto_create: If True, automatically create new Incidents for unmatched extractions
        dry_run: If True, don't commit changes to database, just log what would happen
    """
    # Get unlinked extractions that have enough data for deduplication
    unlinked = ExtractedEvent.query.filter(
        ExtractedEvent.incident_id.is_(None),
        ExtractedEvent.extracted_date.isnot(None)  # Need date for matching
    ).all()
    
    print(f"Found {len(unlinked)} unlinked extractions with dates.")
    
    linked_count = 0
    created_count = 0
    skipped_count = 0
    
    for extraction in unlinked:
        print(f"\nProcessing Extraction {extraction.id}: "
              f"'{extraction.extracted_victim_name or 'Unknown'}' on "
              f"{extraction.extracted_date.strftime('%Y-%m-%d') if extraction.extracted_date else 'N/A'}")
        
        # 1. Try to find existing match
        match, score = find_matching_incident(extraction)
        
        if match:
            print(f"  ✅ MATCHED to Incident {match.id}: '{match.title}' (Score: {score:.2f})")
            if not dry_run:
                extraction.incident = match
            linked_count += 1
            
        elif auto_create:
            # 2. Create new incident
            new_incident = create_incident_from_extraction(extraction)
            print(f"  🆕 CREATED new Incident: '{new_incident.title}'")
            
            if not dry_run:
                db.session.add(new_incident)
                db.session.flush()  # Get the ID
                extraction.incident = new_incident
            created_count += 1
            
        else:
            print(f"  ⏭️ SKIPPED (no match, auto_create=False)")
            skipped_count += 1
    
    if not dry_run:
        db.session.commit()
    
    print(f"\n{'='*50}")
    print(f"Enrichment complete {'(DRY RUN)' if dry_run else ''}")
    print(f"  Linked to existing: {linked_count}")
    print(f"  Created new:        {created_count}")
    print(f"  Skipped:            {skipped_count}")
    print(f"{'='*50}")
    
    return {
        "linked": linked_count,
        "created": created_count,
        "skipped": skipped_count
    }


def link_extraction_to_incident(extraction_id, incident_id):
    """Manually link an extraction to an incident."""
    extraction = ExtractedEvent.query.get(extraction_id)
    incident = Incident.query.get(incident_id)
    
    if not extraction:
        return {"success": False, "message": f"Extraction {extraction_id} not found"}
    if not incident:
        return {"success": False, "message": f"Incident {incident_id} not found"}
    
    extraction.incident = incident
    db.session.commit()
    
    return {
        "success": True, 
        "message": f"Linked Extraction {extraction_id} to Incident {incident_id}",
        "incident_title": incident.title
    }
