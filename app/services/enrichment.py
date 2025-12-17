"""
Enrichment Service - Stage 3 of the Pipeline

Links ExtractedEvents to Incidents, handling deduplication and enrichment.

Deduplication Strategy:
1. Block by date (±1 day) and city to find candidates (heuristics)
2. Use LLM to determine if extraction matches an existing incident
3. Comprehensively enrich incidents using all related sources via LLM
"""
import json
import os
import time
from difflib import SequenceMatcher
from datetime import datetime, timedelta
import vertexai
from vertexai.generative_models import GenerativeModel
from google.oauth2 import service_account
from app.extensions import db
from app.models import ExtractedEvent, Incident

# Configure Vertex AI (Gemini) - same as extraction.py
SA_PATH = "/Users/joaoc/Documents/service_accounts/rj-ia-desenvolvimento-bb81db62d872.json"
MODEL_NAME = "gemini-2.5-flash"

try:
    if os.path.exists(SA_PATH):
        credentials = service_account.Credentials.from_service_account_file(
            SA_PATH,
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        vertexai.init(project=credentials.project_id, location="us-central1", credentials=credentials)
        print(f"✅ Vertex AI initialized for enrichment: {credentials.service_account_email} (Project: {credentials.project_id})")
    else:
        print(f"⚠️ Service Account file not found at {SA_PATH}. LLM enrichment will be skipped.")
        credentials = None
except Exception as e:
    print(f"⚠️ Error initializing Vertex AI for enrichment: {e}")
    credentials = None


def get_llm_model():
    """Get initialized LLM model for enrichment."""
    if not credentials:
        return None
    return GenerativeModel(MODEL_NAME)


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
    # Build location string from structured fields for comparison
    incident_location_parts = []
    if incident.street:
        incident_location_parts.append(incident.street)
    if incident.neighborhood:
        incident_location_parts.append(incident.neighborhood)
    if incident.city:
        incident_location_parts.append(incident.city)
    if incident.state:
        incident_location_parts.append(incident.state)
    incident_location_str = ", ".join(incident_location_parts) if incident_location_parts else None
    
    if extraction.extracted_location and incident_location_str:
        loc_score = fuzzy_match_score(
            extraction.extracted_location,
            incident_location_str
        )
        # Try neighborhood comparison
        ext_neighborhood = extract_neighborhood(extraction.extracted_location)
        inc_neighborhood = incident.neighborhood
        
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


def llm_match_extraction_to_incident(extraction, candidate_incidents):
    """
    Use LLM to determine if an extraction matches any of the candidate incidents.
    
    Args:
        extraction: ExtractedEvent object
        candidate_incidents: List of Incident objects to check against
    
    Returns:
        Tuple: (matched_incident, confidence_score, reasoning) or (None, 0.0, None)
    """
    if not candidate_incidents:
        print(f"    [LLM Match] No candidates to check")
        return None, 0.0, None
    
    print(f"    [LLM Match] Checking {len(candidate_incidents)} candidate incident(s)...")
    start_time = time.time()
    
    model = get_llm_model()
    if not model:
        # Fallback to fuzzy matching if LLM not available
        print(f"    [LLM Match] ⚠️ LLM not available, skipping")
        return None, 0.0, "LLM not available"
    
    # Build extraction summary
    extraction_info = {
        "extraction_id": extraction.id,
        "victim_name": extraction.extracted_victim_name or "Não mencionado",
        "location": extraction.extracted_location or "Não mencionado",
        "date": extraction.extracted_date.strftime('%Y-%m-%d') if extraction.extracted_date else "Desconhecida",
        "summary": extraction.summary or "Sem resumo"
    }
    
    # Build candidate incidents summaries
    candidates_info = []
    for incident in candidate_incidents:
        # Build location string
        location_parts = []
        if incident.street:
            location_parts.append(incident.street)
        if incident.neighborhood:
            location_parts.append(incident.neighborhood)
        if incident.city:
            location_parts.append(incident.city)
        location_str = ", ".join(location_parts) if location_parts else "Não mencionado"
        
        candidates_info.append({
            "incident_id": incident.id,
            "title": incident.title or "Sem título",
            "victims": incident.victims or "Não mencionado",
            "location": location_str,
            "date": incident.date.strftime('%Y-%m-%d') if incident.date else "Desconhecida",
            "description": incident.description or "Sem descrição"
        })
    
    prompt = f"""Analise se a extração abaixo se refere ao mesmo evento real que algum dos incidentes candidatos.

EXTRAÇÃO:
- ID: {extraction_info['extraction_id']}
- Vítima: {extraction_info['victim_name']}
- Local: {extraction_info['location']}
- Data: {extraction_info['date']}
- Resumo: {extraction_info['summary']}

INCIDENTES CANDIDATOS:
"""
    
    for i, candidate in enumerate(candidates_info, 1):
        prompt += f"""
{i}. Incidente ID {candidate['incident_id']}:
   - Título: {candidate['title']}
   - Vítimas: {candidate['victims']}
   - Local: {candidate['location']}
   - Data: {candidate['date']}
   - Descrição: {candidate['description']}
"""
    
    prompt += """
Responda APENAS com um objeto JSON válido no seguinte formato:
{
  "match": true/false,
  "incident_id": número_do_incidente_que_combina_ou_null,
  "confidence": 0.0-1.0,
  "reasoning": "explicação breve do motivo"
}

Considere:
- Nomes de vítimas similares (mesma pessoa)
- Localizações próximas ou iguais
- Datas próximas (mesmo dia ou dia seguinte/anterior)
- Descrições que mencionam o mesmo evento

Se nenhum incidente corresponder claramente, retorne match: false.
"""
    
    try:
        response = model.generate_content(prompt)
        raw_text = response.text.strip()
        
        # Clean up markdown code blocks if present
        if "```json" in raw_text:
            raw_text = raw_text.split("```json")[1].split("```")[0].strip()
        elif "```" in raw_text:
            raw_text = raw_text.split("```")[1].split("```")[0].strip()
        
        data = json.loads(raw_text)
        elapsed = time.time() - start_time
        
        if data.get("match") and data.get("incident_id"):
            # Find the matched incident
            matched_incident = next(
                (inc for inc in candidate_incidents if inc.id == data["incident_id"]),
                None
            )
            if matched_incident:
                print(f"    [LLM Match] ✅ Match found: Incident {matched_incident.id} (confidence: {data.get('confidence', 0.0):.2f}, {elapsed:.1f}s)")
                return (
                    matched_incident,
                    float(data.get("confidence", 0.0)),
                    data.get("reasoning", "")
                )
        
        print(f"    [LLM Match] ❌ No match found (confidence: {data.get('confidence', 0.0):.2f}, {elapsed:.1f}s)")
        return None, float(data.get("confidence", 0.0)), data.get("reasoning", "")
        
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"    [LLM Match] ⚠️ Error: {e} ({elapsed:.1f}s)")
        return None, 0.0, f"LLM error: {e}"


def find_candidate_incidents(extraction):
    """
    Find existing incidents that could potentially match this extraction.
    
    Uses blocking by date and city to reduce comparison space.
    
    Args:
        extraction: ExtractedEvent to find candidates for
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
    Find a matching incident for an extraction using LLM-based matching.
    
    Uses heuristics to find candidates, then LLM to make final decision.
    
    Args:
        extraction: ExtractedEvent to match
    
    Returns (incident, confidence_score) if match found, (None, 0.0) otherwise.
    """
    print(f"  [Match] Searching for matching incidents...")
    candidates = find_candidate_incidents(extraction)
    
    if not candidates:
        print(f"  [Match] No candidates found in date range")
        return None, 0.0
    
    print(f"  [Match] Found {len(candidates)} candidate(s) in date range")
    
    # Use LLM to determine if any candidate matches
    matched_incident, confidence, reasoning = llm_match_extraction_to_incident(extraction, candidates)
    
    if matched_incident:
        print(f"  [Match] ✅ Match confirmed: Incident {matched_incident.id}")
        return matched_incident, confidence
    
    # Log if LLM considered candidates but found no match
    if reasoning and "not available" not in reasoning:
        print(f"  [Match] ❌ No match found")
    
    return None, 0.0


def llm_enrich_incident(incident):
    """
    Comprehensively enrich an incident using all related sources via LLM.
    
    Collects all ExtractedEvents and Sources related to the incident,
    then uses LLM to synthesize the most complete and accurate information.
    
    Args:
        incident: Incident object to enrich
    
    Returns:
        Updated incident object (not saved to database yet)
    """
    print(f"    [Enrichment] Starting enrichment for Incident {incident.id}...")
    start_time = time.time()
    
    model = get_llm_model()
    if not model:
        print(f"    [Enrichment] ⚠️ LLM not available, skipping")
        return incident
    
    # Collect all related extractions
    extractions = incident.extractions
    if not extractions:
        print(f"    [Enrichment] ⚠️ No extractions found, skipping")
        return incident
    
    # Collect all related sources
    sources = [ext.source for ext in extractions if ext.source]
    print(f"    [Enrichment] Found {len(extractions)} extraction(s) and {len(sources)} source(s)")
    
    # Build current incident state
    current_state = {
        "id": incident.id,
        "title": incident.title or "Sem título",
        "date": incident.date.strftime('%Y-%m-%d') if incident.date else "Desconhecida",
        "victims": incident.victims or "Não mencionado",
        "death_count": incident.death_count if incident.death_count is not None else "Não mencionado",
        "country": incident.country or "Brasil",
        "state": incident.state or "Rio de Janeiro",
        "city": incident.city or "Rio de Janeiro",
        "neighborhood": incident.neighborhood or "Não mencionado",
        "street": incident.street or "Não mencionado",
        "location_extra_info": incident.location_extra_info or "Não mencionado",
        "description": incident.description or "Sem descrição"
    }
    
    # Build extraction summaries
    extraction_summaries = []
    for ext in extractions:
        extraction_summaries.append({
            "id": ext.id,
            "victim_name": ext.extracted_victim_name or "Não mencionado",
            "location": ext.extracted_location or "Não mencionado",
            "date": ext.extracted_date.strftime('%Y-%m-%d') if ext.extracted_date else "Desconhecida",
            "summary": ext.summary or "Sem resumo",
            "confidence": ext.confidence_score,
            "death_count": ext.death_count if ext.death_count is not None else "Não mencionado"
        })
    
    # Build source content (full content for comprehensive enrichment)
    source_contents = []
    for source in sources:
        source_contents.append({
            "id": source.id,
            "url": source.url,
            "title": source.title or "Sem título",
            "content": (source.content or "")[:5000],  # Limit to avoid token limits
            "published_at": source.published_at.strftime('%Y-%m-%d') if source.published_at else "Desconhecida"
        })
    
    prompt = f"""Você é um assistente especializado em sintetizar informações sobre incidentes violentos a partir de múltiplas fontes de notícias.

INCIDENTE ATUAL:
- ID: {current_state['id']}
- Título: {current_state['title']}
- Data: {current_state['date']}
- Vítimas: {current_state['victims']}
- Número de mortos: {current_state['death_count']}
- País: {current_state['country']}
- Estado: {current_state['state']}
- Cidade: {current_state['city']}
- Bairro: {current_state['neighborhood']}
- Rua: {current_state['street']}
- Informações adicionais de localização: {current_state['location_extra_info']}
- Descrição: {current_state['description']}

EXTRAÇÕES RELACIONADAS:
"""
    
    for i, ext in enumerate(extraction_summaries, 1):
        prompt += f"""
{i}. Extração ID {ext['id']} (Confiança: {ext['confidence']:.2f}):
   - Vítima: {ext['victim_name']}
   - Local: {ext['location']}
   - Data: {ext['date']}
   - Número de mortos: {ext['death_count']}
   - Resumo: {ext['summary']}
"""
    
    prompt += "\nFONTES DE NOTÍCIAS COMPLETAS:\n"
    
    for i, source in enumerate(source_contents, 1):
        prompt += f"""
{i}. Fonte ID {source['id']} ({source['published_at']}):
   - URL: {source['url']}
   - Título: {source['title']}
   - Conteúdo: {source['content']}
"""
    
    prompt += """
Sua tarefa é sintetizar a informação mais completa e precisa possível sobre este incidente,
combinando todas as fontes acima. Se houver conflitos entre fontes, use a informação mais
credível, recente e consistente.

Retorne APENAS um objeto JSON válido com a seguinte estrutura:
{
  "title": "título mais descritivo e preciso",
  "date": "YYYY-MM-DD ou null se não puder determinar",
  "victims": "informação completa sobre vítimas (nomes, idades, etc.)",
  "death_count": número_inteiro ou null (número de pessoas mortas neste incidente. Extraia diretamente das fontes. Se houver conflito entre fontes, use o número mais confiável e consistente. Retorne null apenas se não for possível determinar),
  "country": "país",
  "state": "estado",
  "city": "cidade",
  "neighborhood": "bairro ou null",
  "street": "rua/endereço específico ou null",
  "location_extra_info": "informações adicionais de localização ou null",
  "description": "descrição completa e detalhada do incidente, sintetizando todas as fontes"
}

Instruções importantes:
- Use informações de múltiplas fontes para criar uma descrição completa
- Se fontes conflitam, prefira fontes mais recentes e com maior confiança
- Extraia informações de localização estruturadas (país, estado, cidade, bairro, rua)
- Se uma informação não estiver disponível, use null (não invente dados)
- O título deve ser descritivo e incluir informações principais (vítima, local, data se relevante)
"""
    
    try:
        response = model.generate_content(prompt)
        raw_text = response.text.strip()
        
        # Clean up markdown code blocks if present
        if "```json" in raw_text:
            raw_text = raw_text.split("```json")[1].split("```")[0].strip()
        elif "```" in raw_text:
            raw_text = raw_text.split("```")[1].split("```")[0].strip()
        
        data = json.loads(raw_text)
        
        # Update incident fields
        if data.get("title"):
            incident.title = data["title"]
        
        if data.get("date"):
            try:
                incident.date = datetime.strptime(data["date"], "%Y-%m-%d")
            except:
                pass  # Keep existing date if parsing fails
        
        if data.get("victims"):
            incident.victims = data["victims"]
        
        if data.get("death_count") is not None:
            try:
                incident.death_count = int(data["death_count"])
            except (ValueError, TypeError):
                pass  # Keep existing death_count if parsing fails
        
        if data.get("country"):
            incident.country = data["country"]
        
        if data.get("state"):
            incident.state = data["state"]
        
        if data.get("city"):
            incident.city = data["city"]
        
        if data.get("neighborhood"):
            incident.neighborhood = data["neighborhood"]
        elif data.get("neighborhood") is None:
            incident.neighborhood = None
        
        if data.get("street"):
            incident.street = data["street"]
        elif data.get("street") is None:
            incident.street = None
        
        if data.get("location_extra_info"):
            incident.location_extra_info = data["location_extra_info"]
        elif data.get("location_extra_info") is None:
            incident.location_extra_info = None
        
        if data.get("description"):
            incident.description = data["description"]
        
        elapsed = time.time() - start_time
        print(f"    [Enrichment] ✅ Completed in {elapsed:.1f}s")
        print(f"    [Enrichment]   Title: {incident.title[:60]}...")
        if incident.victims:
            print(f"    [Enrichment]   Victims: {incident.victims[:60]}...")
        if incident.neighborhood:
            print(f"    [Enrichment]   Location: {incident.neighborhood}, {incident.city}")
        return incident
        
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"    [Enrichment] ⚠️ Error: {e} ({elapsed:.1f}s)")
        # Return incident unchanged on error
        return incident


def process_single_extraction(extraction_id, auto_create, dry_run):
    """
    Process a single extraction: match → link/create → enrich → commit
    
    Args:
        extraction_id: ID of extraction to process
        auto_create: If True, create new incidents for unmatched extractions
        dry_run: If True, don't commit changes
    
    Returns:
        dict with result: {"status": "linked"|"created"|"skipped"|"error", 
                          "extraction_id": int, "incident_id": int|None, 
                          "error": str|None}
    """
    try:
        # Get extraction
        extraction = ExtractedEvent.query.get(extraction_id)
        if not extraction:
            return {
                "status": "error",
                "extraction_id": extraction_id,
                "incident_id": None,
                "error": "Extraction not found"
            }
        
        # Skip if already linked
        if extraction.incident_id is not None:
            return {
                "status": "skipped",
                "extraction_id": extraction_id,
                "incident_id": extraction.incident_id,
                "error": None
            }
        
        print(f"\n[Extraction {extraction.id}] Processing")
        print(f"  Victim: {extraction.extracted_victim_name or 'Unknown'}")
        print(f"  Date: {extraction.extracted_date.strftime('%Y-%m-%d') if extraction.extracted_date else 'N/A'}")
        print(f"  Location: {extraction.extracted_location or 'N/A'}")
        
        # 1. Try to find existing match
        match, score = find_matching_incident(extraction)
        
        if match:
            print(f"  ✅ MATCHED to Incident {match.id}: '{match.title}' (Confidence: {score:.2f})")
            if not dry_run:
                extraction.incident = match
                db.session.commit()
                
                # Refresh incident to get latest state with all extractions
                db.session.refresh(match)
                
                # Enrich the incident with all related sources
                enriched_incident = llm_enrich_incident(match)
                db.session.commit()
            
            return {
                "status": "linked",
                "extraction_id": extraction.id,
                "incident_id": match.id,
                "error": None
            }
        
        elif auto_create:
            # 2. Create new incident - no match found
            if not dry_run:
                new_incident = create_incident_from_extraction(extraction)
                print(f"  🆕 CREATED new Incident: '{new_incident.title}'")
                db.session.add(new_incident)
                db.session.flush()  # Get the ID
                extraction.incident = new_incident
                db.session.commit()
                
                # Refresh to get all related extractions
                db.session.refresh(new_incident)
                
                # Enrich the new incident with all related sources
                enriched_incident = llm_enrich_incident(new_incident)
                db.session.commit()
                
                return {
                    "status": "created",
                    "extraction_id": extraction.id,
                    "incident_id": new_incident.id,
                    "error": None
                }
            else:
                # Dry run - just create without committing
                new_incident = create_incident_from_extraction(extraction)
                print(f"  🆕 CREATED new Incident: '{new_incident.title}' (DRY RUN)")
                return {
                    "status": "created",
                    "extraction_id": extraction.id,
                    "incident_id": None,  # No ID in dry run
                    "error": None
                }
        
        else:
            print(f"  ⏭️ SKIPPED (no match, auto_create=False)")
            return {
                "status": "skipped",
                "extraction_id": extraction.id,
                "incident_id": None,
                "error": None
            }
            
    except Exception as e:
        print(f"  ❌ ERROR processing extraction {extraction_id}: {e}")
        db.session.rollback()
        return {
            "status": "error",
            "extraction_id": extraction_id,
            "incident_id": None,
            "error": str(e)
        }


def create_incident_from_extraction(extraction):
    """Create a new Incident from an ExtractedEvent."""
    # Use victim name for title if available, otherwise use a generic title
    if extraction.extracted_victim_name:
        title = f"Morte de {extraction.extracted_victim_name}"
    else:
        title = f"Homicídio - {extraction.extracted_date.strftime('%d/%m/%Y') if extraction.extracted_date else 'Data desconhecida'}"
    
    # Extract neighborhood
    neighborhood = extract_neighborhood(extraction.extracted_location)
    
    # Store the full extracted location in location_extra_info for reference
    # The structured fields will be populated by enrichment/location parsing later
    incident = Incident(
        title=title,
        date=extraction.extracted_date,
        victims=extraction.extracted_victim_name,  # Store victim name in victims field
        death_count=extraction.death_count,  # Copy death_count from extraction
        country="Brasil",
        state="Rio de Janeiro",
        city="Rio de Janeiro",
        neighborhood=neighborhood,
        location_extra_info=extraction.extracted_location,  # Store full location string for reference
        description=extraction.summary,
        confirmed=False  # Requires manual review
    )
    
    return incident


def run_enrichment(auto_create=True, dry_run=False):
    """
    Stage 3: Enrichment - Link Extractions to Incidents.
    
    Processes extractions sequentially:
    - Each extraction is fully processed: match → link/create → enrich → commit
    - Processes one extraction at a time in order
    
    Args:
        auto_create: If True, automatically create new Incidents for unmatched extractions
        dry_run: If True, don't commit changes to database, just log what would happen
    """
    print(f"\n{'='*70}")
    print(f"ENRICHMENT PROCESS STARTING")
    print(f"{'='*70}")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print(f"Auto-create: {auto_create}")
    print(f"{'='*70}\n")
    
    start_time = time.time()
    
    # Get unlinked extractions that have enough data for deduplication
    # Fetch only IDs to avoid loading all data into memory
    unlinked_query = ExtractedEvent.query.filter(
        ExtractedEvent.incident_id.is_(None),
        ExtractedEvent.extracted_date.isnot(None)  # Need date for matching
    )
    unlinked_ids = [row[0] for row in unlinked_query.with_entities(ExtractedEvent.id).all()]
    total = len(unlinked_ids)
    
    print(f"📊 Found {total} unlinked extraction(s) with dates")
    
    if total == 0:
        print("✅ No extractions to process. Exiting.")
        return {
            "linked": 0,
            "created": 0,
            "skipped": 0,
            "errors": 0
        }
    
    # Process sequentially
    linked_count = 0
    created_count = 0
    skipped_count = 0
    error_count = 0
    
    for i, ext_id in enumerate(unlinked_ids, 1):
        try:
            result = process_single_extraction(ext_id, auto_create, dry_run)
            
            if result["status"] == "linked":
                linked_count += 1
            elif result["status"] == "created":
                created_count += 1
            elif result["status"] == "skipped":
                skipped_count += 1
            elif result["status"] == "error":
                error_count += 1
                print(f"  ❌ Error processing extraction {ext_id}: {result.get('error', 'Unknown error')}")
            
            # Progress update every 10 items or at the end
            if i % 10 == 0 or i == total:
                print(f"\n📊 Progress: {i}/{total} | Linked: {linked_count} | Created: {created_count} | Skipped: {skipped_count} | Errors: {error_count}")
                
        except Exception as e:
            error_count += 1
            print(f"  ❌ Error processing extraction {ext_id}: {e}")
    
    elapsed = time.time() - start_time
    
    print(f"\n{'='*70}")
    print(f"ENRICHMENT COMPLETE {'(DRY RUN)' if dry_run else ''}")
    print(f"{'='*70}")
    print(f"  ⏱️  Total time: {elapsed:.1f}s")
    print(f"  📈 Linked to existing: {linked_count}")
    print(f"  🆕 Created new:        {created_count}")
    print(f"  ⏭️  Skipped:            {skipped_count}")
    print(f"  ❌ Errors:              {error_count}")
    print(f"  📊 Total processed:    {total}")
    print(f"{'='*70}\n")
    
    # Post-processing: Deduplicate any incidents that were created
    merged_count = 0
    if not dry_run and created_count > 0:
        dedup_result = deduplicate_incidents(dry_run=dry_run)
        merged_count = dedup_result.get("merged", 0)
        if merged_count > 0:
            print(f"✅ Merged {merged_count} duplicate incident(s)")
    
    return {
        "linked": linked_count,
        "created": created_count,
        "skipped": skipped_count,
        "errors": error_count,
        "merged": merged_count
    }


def deduplicate_incidents(dry_run=False):
    """
    Post-processing deduplication: Find and merge duplicate incidents.
    
    This runs after enrichment to catch any duplicates that were created.
    
    Args:
        dry_run: If True, don't commit changes
    
    Returns:
        dict with deduplication results
    """
    print(f"\n{'='*70}")
    print(f"DEDUPLICATION PASS")
    print(f"{'='*70}\n")
    
    # Get all incidents
    all_incidents = Incident.query.all()
    print(f"Checking {len(all_incidents)} incidents for duplicates...")
    
    merged_count = 0
    duplicates_found = []
    
    # Group incidents by date for efficiency
    incidents_by_date = {}
    for incident in all_incidents:
        if incident.date:
            date_key = incident.date.date()
            if date_key not in incidents_by_date:
                incidents_by_date[date_key] = []
            incidents_by_date[date_key].append(incident)
    
    # Check for duplicates within each date group
    for date_key, incidents in incidents_by_date.items():
        if len(incidents) < 2:
            continue
        
        # Compare each pair of incidents using LLM
        for i, incident1 in enumerate(incidents):
            if incident1.id in duplicates_found:
                continue
                
            for incident2 in incidents[i+1:]:
                if incident2.id in duplicates_found:
                    continue
                
                # Use LLM to check if they're duplicates
                # Create a dummy extraction from incident2 to check against incident1
                dummy_extraction = ExtractedEvent(
                    id=999999,  # Dummy ID
                    extracted_date=incident2.date,
                    extracted_victim_name=incident2.victims,
                    extracted_location=f"{incident2.street or ''}, {incident2.neighborhood or ''}, {incident2.city or ''}".strip(', '),
                    summary=incident2.description or incident2.title
                )
                
                # Check if incident2 matches incident1 using LLM
                matched_incident, confidence, reasoning = llm_match_extraction_to_incident(
                    dummy_extraction, 
                    [incident1]
                )
                
                if matched_incident and matched_incident.id == incident1.id and confidence > 0.8:
                    print(f"\n🔗 Found duplicate: Incident {incident2.id} matches Incident {incident1.id} (confidence: {confidence:.2f})")
                    print(f"   Keeping: Incident {incident1.id} - {incident1.title}")
                    print(f"   Merging: Incident {incident2.id} - {incident2.title}")
                    
                    if not dry_run:
                        # Move all extractions from incident2 to incident1
                        for extraction in incident2.extractions:
                            extraction.incident_id = incident1.id
                        
                        # Re-enrich incident1 with all sources
                        db.session.refresh(incident1)
                        enriched = llm_enrich_incident(incident1)
                        
                        # Delete incident2
                        db.session.delete(incident2)
                        db.session.commit()
                    
                    duplicates_found.append(incident2.id)
                    merged_count += 1
                    break
    
    print(f"\n{'='*70}")
    print(f"DEDUPLICATION COMPLETE {'(DRY RUN)' if dry_run else ''}")
    print(f"  Merged duplicates: {merged_count}")
    print(f"{'='*70}\n")
    
    return {
        "merged": merged_count
    }


def re_enrich_incident(incident_id, dry_run=False):
    """
    Re-enrich an incident on-demand using all current related sources.
    
    Args:
        incident_id: ID of the incident to re-enrich
        dry_run: If True, don't save changes to database
    
    Returns:
        dict with success status and incident data
    """
    incident = Incident.query.get(incident_id)
    
    if not incident:
        return {
            "success": False,
            "message": f"Incident {incident_id} not found"
        }
    
    print(f"\nRe-enriching Incident {incident_id}: '{incident.title}'")
    print(f"  Current extractions: {len(incident.extractions)}")
    
    # Enrich the incident
    enriched_incident = llm_enrich_incident(incident)
    
    if not dry_run:
        db.session.commit()
        return {
            "success": True,
            "message": f"Re-enriched Incident {incident_id}",
            "incident": {
                "id": enriched_incident.id,
                "title": enriched_incident.title,
                "date": enriched_incident.date.strftime('%Y-%m-%d') if enriched_incident.date else None,
                "victims": enriched_incident.victims,
                "location": f"{enriched_incident.street or ''}, {enriched_incident.neighborhood or ''}, {enriched_incident.city or ''}".strip(', ')
            }
        }
    else:
        return {
            "success": True,
            "message": f"Re-enrichment preview for Incident {incident_id} (DRY RUN)",
            "incident": {
                "id": enriched_incident.id,
                "title": enriched_incident.title,
                "date": enriched_incident.date.strftime('%Y-%m-%d') if enriched_incident.date else None,
                "victims": enriched_incident.victims,
                "location": f"{enriched_incident.street or ''}, {enriched_incident.neighborhood or ''}, {enriched_incident.city or ''}".strip(', ')
            }
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
