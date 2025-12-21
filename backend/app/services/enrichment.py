"""
Enrichment Service - Stage 4 of the Pipeline

Links RawEvents to UniqueEvents through intelligent deduplication,
and synthesizes information from multiple sources.

Deduplication Strategy:
1. Block by date/city/victim name to find candidates (heuristics)
2. Use LLM to determine if RawEvent matches an existing UniqueEvent
3. Batch process pending RawEvents to cluster and create new UniqueEvents
4. Enrich UniqueEvents using all related sources via LLM
"""

import json
from datetime import datetime, timedelta
from difflib import SequenceMatcher

import instructor
from loguru import logger
from sqlalchemy import text
from unidecode import unidecode

from app.config import get_settings
from app.database import async_session_maker
from app.models import RawEvent, UniqueEvent
from app.services.telegram import notify_new_death


def parse_datetime(value) -> datetime | None:
    """Parse datetime from various formats (handles SQLite string dates)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        # Try common formats
        for fmt in ["%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]:
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
        # Try ISO format
        try:
            return datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            pass
    return None


# === Configuration ===
DATE_TOLERANCE_DAYS = 1  # For date+city blocking
VICTIM_NAME_DATE_TOLERANCE_DAYS = 10  # Wider window when victim name matches
FUZZY_NAME_THRESHOLD = 0.85  # Threshold for fuzzy name matching
LLM_MATCH_CONFIDENCE_THRESHOLD = 0.7  # Minimum confidence to accept LLM match


# =============================================================================
# VICTIM NAME UTILITIES
# =============================================================================


def normalize_name(name: str) -> str:
    """Normalize name for fuzzy matching: remove accents, lowercase, strip."""
    if not name:
        return ""
    # Remove accents, lowercase, normalize whitespace
    normalized = unidecode(name.lower().strip())
    # Collapse multiple spaces
    normalized = " ".join(normalized.split())
    return normalized


def fuzzy_name_match(name1: str, name2: str, threshold: float = FUZZY_NAME_THRESHOLD) -> bool:
    """
    Check if two names refer to the same person.
    
    Handles:
    - Exact matches after normalization
    - Partial names (one contains the other)
    - Fuzzy similarity above threshold
    """
    n1, n2 = normalize_name(name1), normalize_name(name2)
    
    if not n1 or not n2:
        return False
    
    # Exact match after normalization
    if n1 == n2:
        return True
    
    # One name contains the other (handles partial names)
    # e.g., "João" matches "João da Silva"
    if n1 in n2 or n2 in n1:
        return True
    
    # High fuzzy similarity
    ratio = SequenceMatcher(None, n1, n2).ratio()
    if ratio >= threshold:
        return True
    
    return False


def extract_victim_names(raw_event: RawEvent) -> list[str]:
    """
    Extract identified victim names from extraction_data.
    
    Returns list of normalized names (at least 4 characters).
    """
    names = []
    if not raw_event.extraction_data:
        return names
    
    victims = raw_event.extraction_data.get("victims", {})
    identifiable = victims.get("identifiable_victims", [])
    
    for victim in identifiable:
        name = victim.get("name")
        if name and len(name.strip()) > 3:  # Ignore very short names/initials
            names.append(normalize_name(name))
    
    return names


def extract_victim_names_from_unique_event(unique_event: UniqueEvent) -> list[str]:
    """Extract victim names from UniqueEvent's victims_summary or merged_data."""
    names = []
    
    # Try victims_summary first
    if unique_event.victims_summary:
        # victims_summary is like "João Silva, 32 anos, masculino"
        # Extract just the name part (before comma or age)
        parts = unique_event.victims_summary.split(",")
        if parts:
            name = parts[0].strip()
            if len(name) > 3:
                names.append(normalize_name(name))
    
    # Also check merged_data for identifiable victims
    if unique_event.merged_data:
        victims = unique_event.merged_data.get("victims", {})
        identifiable = victims.get("identifiable_victims", [])
        for victim in identifiable:
            name = victim.get("name")
            if name and len(name.strip()) > 3:
                normalized = normalize_name(name)
                if normalized not in names:
                    names.append(normalized)
    
    return names


# =============================================================================
# BLOCKING FUNCTIONS (Finding Candidates)
# =============================================================================


async def block_by_date_city(
    raw_event: RawEvent, 
    days: int = DATE_TOLERANCE_DAYS
) -> list[UniqueEvent]:
    """
    Find UniqueEvents within +/- days of raw_event date in same city.
    
    This is the baseline blocking strategy.
    """
    if not raw_event.event_date or not raw_event.city:
        return []
    
    min_date = raw_event.event_date - timedelta(days=days)
    max_date = raw_event.event_date + timedelta(days=days)
    city_lower = raw_event.city.lower()
    
    async with async_session_maker() as session:
        result = await session.execute(
            text("""
                SELECT * FROM unique_event 
                WHERE event_date BETWEEN :min_date AND :max_date
                AND LOWER(city) = :city
            """),
            {"min_date": min_date, "max_date": max_date, "city": city_lower}
        )
        rows = result.fetchall()
        
        # Convert rows to UniqueEvent objects
        candidates = []
        for row in rows:
            # Create UniqueEvent from row
            unique_event = UniqueEvent(
                id=row.id,
                event_date=parse_datetime(row.event_date),
                city=row.city,
                state=row.state,
                neighborhood=row.neighborhood,
                street=row.street,
                victims_summary=row.victims_summary,
                victim_count=row.victim_count,
                homicide_type=row.homicide_type,
                title=row.title,
                chronological_description=row.chronological_description,
                source_count=row.source_count,
                merged_data=row.merged_data,
            )
            candidates.append(unique_event)
        
        return candidates


async def block_by_victim_name(
    raw_event: RawEvent,
    victim_names: list[str],
    days: int = VICTIM_NAME_DATE_TOLERANCE_DAYS
) -> list[UniqueEvent]:
    """
    Find UniqueEvents that mention any of the victim names (wider date window).
    
    This uses a wider date window because victim names are strong identity signals.
    """
    if not victim_names or not raw_event.city:
        return []
    
    # Get date range (use wider window, or no date constraint if no date)
    if raw_event.event_date:
        min_date = raw_event.event_date - timedelta(days=days)
        max_date = raw_event.event_date + timedelta(days=days)
    else:
        # No date - search last 30 days
        max_date = datetime.utcnow()
        min_date = max_date - timedelta(days=30)
    
    city_lower = raw_event.city.lower()
    
    async with async_session_maker() as session:
        # Get all unique events in the date range and city
        result = await session.execute(
            text("""
                SELECT * FROM unique_event 
                WHERE (event_date BETWEEN :min_date AND :max_date OR event_date IS NULL)
                AND LOWER(city) = :city
            """),
            {"min_date": min_date, "max_date": max_date, "city": city_lower}
        )
        rows = result.fetchall()
        
        candidates = []
        for row in rows:
            unique_event = UniqueEvent(
                id=row.id,
                event_date=parse_datetime(row.event_date),
                city=row.city,
                state=row.state,
                neighborhood=row.neighborhood,
                street=row.street,
                victims_summary=row.victims_summary,
                victim_count=row.victim_count,
                homicide_type=row.homicide_type,
                title=row.title,
                chronological_description=row.chronological_description,
                source_count=row.source_count,
                merged_data=row.merged_data,
            )
            
            # Check if any victim name matches
            unique_event_names = extract_victim_names_from_unique_event(unique_event)
            for raw_name in victim_names:
                for unique_name in unique_event_names:
                    if fuzzy_name_match(raw_name, unique_name):
                        candidates.append(unique_event)
                        break
                else:
                    continue
                break
        
        return candidates


async def block_by_neighborhood(raw_event: RawEvent) -> list[UniqueEvent]:
    """
    Find UniqueEvents in same city+neighborhood+date (for events without victims).
    
    This provides tighter location matching when we don't have victim names.
    """
    if not raw_event.event_date or not raw_event.city or not raw_event.neighborhood:
        return []
    
    min_date = raw_event.event_date - timedelta(days=DATE_TOLERANCE_DAYS)
    max_date = raw_event.event_date + timedelta(days=DATE_TOLERANCE_DAYS)
    city_lower = raw_event.city.lower()
    neighborhood_lower = raw_event.neighborhood.lower()
    
    async with async_session_maker() as session:
        result = await session.execute(
            text("""
                SELECT * FROM unique_event 
                WHERE event_date BETWEEN :min_date AND :max_date
                AND LOWER(city) = :city
                AND LOWER(neighborhood) = :neighborhood
            """),
            {
                "min_date": min_date, 
                "max_date": max_date, 
                "city": city_lower,
                "neighborhood": neighborhood_lower
            }
        )
        rows = result.fetchall()
        
        candidates = []
        for row in rows:
            unique_event = UniqueEvent(
                id=row.id,
                event_date=parse_datetime(row.event_date),
                city=row.city,
                state=row.state,
                neighborhood=row.neighborhood,
                street=row.street,
                victims_summary=row.victims_summary,
                victim_count=row.victim_count,
                homicide_type=row.homicide_type,
                title=row.title,
                chronological_description=row.chronological_description,
                source_count=row.source_count,
                merged_data=row.merged_data,
            )
            candidates.append(unique_event)
        
        return candidates


async def find_candidate_unique_events(raw_event: RawEvent) -> list[UniqueEvent]:
    """
    Combine all blocking strategies and return unique candidates.
    
    Priority:
    1. Victim name match (highest priority, widest date window)
    2. Date + City (baseline)
    3. Neighborhood + Date (for events without victim names)
    """
    candidates_dict = {}  # id -> UniqueEvent to deduplicate
    
    # Strategy 1: Date + City (always run if we have date and city)
    if raw_event.event_date and raw_event.city:
        date_city_candidates = await block_by_date_city(raw_event)
        for c in date_city_candidates:
            candidates_dict[c.id] = c
    
    # Strategy 2: Victim Name + City (if victim identified - highest priority)
    victim_names = extract_victim_names(raw_event)
    if victim_names:
        victim_candidates = await block_by_victim_name(raw_event, victim_names)
        for c in victim_candidates:
            candidates_dict[c.id] = c
    
    # Strategy 3: Neighborhood + Date (if no victim but has neighborhood)
    if not victim_names and raw_event.neighborhood:
        neighborhood_candidates = await block_by_neighborhood(raw_event)
        for c in neighborhood_candidates:
            candidates_dict[c.id] = c
    
    return list(candidates_dict.values())


# =============================================================================
# LLM MATCHING
# =============================================================================


def get_instructor_client():
    """Get instructor client with Gemini provider."""
    settings = get_settings()
    api_key = settings.gemini_api_key
    
    if not api_key:
        raise ValueError("GEMINI_API_KEY not configured")
    
    return instructor.from_provider(
        f"google/{settings.extraction_model}",
        api_key=api_key,
    )


def format_raw_event_for_prompt(raw_event: RawEvent) -> str:
    """Format a RawEvent for LLM prompt."""
    victim_names = extract_victim_names(raw_event)
    victim_str = ", ".join(victim_names) if victim_names else "Não identificado"
    
    location_parts = []
    if raw_event.neighborhood:
        location_parts.append(raw_event.neighborhood)
    if raw_event.city:
        location_parts.append(raw_event.city)
    if raw_event.state:
        location_parts.append(raw_event.state)
    location_str = ", ".join(location_parts) if location_parts else "Não especificado"
    
    date_str = raw_event.event_date.strftime('%Y-%m-%d') if raw_event.event_date else "Não especificada"
    
    return f"""- ID: {raw_event.id}
- Vítima(s): {victim_str}
- Local: {location_str}
- Data: {date_str}
- Tipo: {raw_event.homicide_type or 'Não especificado'}
- Descrição: {raw_event.chronological_description or raw_event.title or 'Sem descrição'}"""


def format_unique_event_for_prompt(unique_event: UniqueEvent) -> str:
    """Format a UniqueEvent for LLM prompt."""
    location_parts = []
    if unique_event.neighborhood:
        location_parts.append(unique_event.neighborhood)
    if unique_event.city:
        location_parts.append(unique_event.city)
    if unique_event.state:
        location_parts.append(unique_event.state)
    location_str = ", ".join(location_parts) if location_parts else "Não especificado"
    
    date_str = unique_event.event_date.strftime('%Y-%m-%d') if unique_event.event_date else "Não especificada"
    
    return f"""- ID: {unique_event.id}
- Vítima(s): {unique_event.victims_summary or 'Não identificado'}
- Local: {location_str}
- Data: {date_str}
- Tipo: {unique_event.homicide_type or 'Não especificado'}
- Descrição: {unique_event.chronological_description or unique_event.title or 'Sem descrição'}
- Fontes: {unique_event.source_count}"""


def llm_match_to_unique_event(
    raw_event: RawEvent,
    candidates: list[UniqueEvent]
) -> tuple[UniqueEvent | None, float, str]:
    """
    Use LLM to determine if RawEvent matches any candidate UniqueEvent.
    
    Returns: (matched_event, confidence, reasoning) or (None, 0.0, "no match")
    """
    if not candidates:
        return None, 0.0, "No candidates"
    
    logger.debug(f"[LLM Match] Checking {len(candidates)} candidate(s) for RawEvent {raw_event.id}")
    
    # Build prompt
    raw_event_str = format_raw_event_for_prompt(raw_event)
    candidates_str = "\n\n".join([
        f"{i+1}. UniqueEvent:\n{format_unique_event_for_prompt(c)}"
        for i, c in enumerate(candidates)
    ])
    
    prompt = f"""Analise se a extração abaixo se refere ao mesmo evento real que algum dos eventos candidatos.

EXTRAÇÃO (RawEvent):
{raw_event_str}

EVENTOS CANDIDATOS (UniqueEvents):
{candidates_str}

REGRAS DE MATCHING (em ordem de importância):

1. **VÍTIMA** (peso MÁXIMO): Se a extração e um candidato mencionam a MESMA VÍTIMA (mesmo nome ou nome muito similar), são o MESMO evento, MESMO QUE outros detalhes difiram.
   - Exemplo: "João Silva" e "Joao da Silva" = MESMA pessoa
   - Exemplo: fontes diferentes podem focar em aspectos diferentes do mesmo crime

2. **DATA + LOCAL** (peso alto): Mesmo dia + mesmo bairro/local sugere mesmo evento, especialmente se não há vítimas identificadas.

3. **DESCRIÇÃO** (peso médio): Descrições similares do crime ajudam a confirmar, mas fontes diferentes podem descrever o mesmo evento de formas diferentes.
   - "Homem baleado no Complexo da Maré" e "Tiroteio deixa um morto na Maré" podem ser o MESMO evento

IMPORTANTE: Se há dúvida significativa, responda que NÃO há match. É melhor criar eventos separados que podem ser mesclados depois.

Responda APENAS com JSON válido:
{{
  "match": true/false,
  "unique_event_id": número_do_id_que_combina_ou_null,
  "confidence": 0.0-1.0,
  "reasoning": "explicação breve"
}}"""

    try:
        settings = get_settings()
        client = instructor.from_provider(
            f"google/{settings.extraction_model}",
            api_key=settings.gemini_api_key,
        )
        
        from pydantic import BaseModel
        
        class MatchResult(BaseModel):
            match: bool
            unique_event_id: int | None
            confidence: float
            reasoning: str
        
        result = client.create(
            response_model=MatchResult,
            messages=[
                {"role": "user", "content": prompt}
            ],
            max_retries=2,
        )
        
        if result.match and result.unique_event_id and result.confidence >= LLM_MATCH_CONFIDENCE_THRESHOLD:
            # Find the matched candidate
            matched = next((c for c in candidates if c.id == result.unique_event_id), None)
            if matched:
                logger.info(f"[LLM Match] ✅ Match found: RawEvent {raw_event.id} -> UniqueEvent {matched.id} (confidence: {result.confidence:.2f})")
                return matched, result.confidence, result.reasoning
        
        logger.debug(f"[LLM Match] ❌ No match for RawEvent {raw_event.id} (confidence: {result.confidence:.2f})")
        return None, result.confidence, result.reasoning
        
    except Exception as e:
        logger.error(f"[LLM Match] Error: {e}")
        return None, 0.0, f"LLM error: {e}"


# =============================================================================
# LINKING
# =============================================================================


async def link_raw_event_to_unique_event(raw_event_id: int, unique_event_id: int) -> None:
    """
    Link RawEvent to UniqueEvent:
    - Set raw_event.unique_event_id
    - Set raw_event.deduplication_status = 'matched'
    - Increment unique_event.source_count
    - Set unique_event.needs_enrichment = True
    """
    async with async_session_maker() as session:
        # Update RawEvent
        await session.execute(
            text("""
                UPDATE raw_event 
                SET unique_event_id = :unique_event_id,
                    deduplication_status = 'matched',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :raw_event_id
            """),
            {"raw_event_id": raw_event_id, "unique_event_id": unique_event_id}
        )
        
        # Update UniqueEvent
        await session.execute(
            text("""
                UPDATE unique_event 
                SET source_count = source_count + 1,
                    needs_enrichment = 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :unique_event_id
            """),
            {"unique_event_id": unique_event_id}
        )
        
        await session.commit()
        
    logger.info(f"[Link] Linked RawEvent {raw_event_id} to UniqueEvent {unique_event_id}")


# =============================================================================
# CLUSTERING (Batch Deduplication)
# =============================================================================


def group_pending_by_date_city(raw_events: list[RawEvent]) -> dict[tuple, list[RawEvent]]:
    """Group pending RawEvents by (date, city) for efficient clustering."""
    groups = {}
    
    for raw_event in raw_events:
        if raw_event.event_date and raw_event.city:
            key = (raw_event.event_date.date(), raw_event.city.lower())
        elif raw_event.city:
            key = ("no_date", raw_event.city.lower())
        else:
            key = ("no_date", "unknown")
        
        groups.setdefault(key, []).append(raw_event)
    
    return groups


def pre_cluster_by_victim_name(raw_events: list[RawEvent]) -> list[list[RawEvent]]:
    """
    Pre-cluster RawEvents by victim name match (no LLM needed).
    
    Events with matching victim names are clustered together.
    Events without identifiable victims remain as singletons.
    """
    if len(raw_events) <= 1:
        return [[e] for e in raw_events]
    
    # Build victim name -> raw_events index
    name_to_events: dict[str, list[RawEvent]] = {}
    events_with_names: set[int] = set()
    
    for raw_event in raw_events:
        names = extract_victim_names(raw_event)
        if names:
            events_with_names.add(raw_event.id)
            for name in names:
                name_to_events.setdefault(name, []).append(raw_event)
    
    # Build clusters using union-find approach
    event_to_cluster: dict[int, int] = {}
    clusters: dict[int, list[RawEvent]] = {}
    next_cluster_id = 0
    
    # First, cluster events that share any victim name
    for name, events in name_to_events.items():
        if len(events) > 1:
            # Find if any of these events are already in a cluster
            existing_cluster_ids = set()
            for e in events:
                if e.id in event_to_cluster:
                    existing_cluster_ids.add(event_to_cluster[e.id])
            
            if existing_cluster_ids:
                # Merge into the first existing cluster
                target_cluster_id = min(existing_cluster_ids)
                for e in events:
                    if e.id not in event_to_cluster:
                        event_to_cluster[e.id] = target_cluster_id
                        clusters.setdefault(target_cluster_id, []).append(e)
                    elif event_to_cluster[e.id] != target_cluster_id:
                        # Merge clusters
                        old_cluster_id = event_to_cluster[e.id]
                        for old_e in clusters.get(old_cluster_id, []):
                            event_to_cluster[old_e.id] = target_cluster_id
                            clusters.setdefault(target_cluster_id, []).append(old_e)
                        clusters.pop(old_cluster_id, None)
            else:
                # Create new cluster
                for e in events:
                    event_to_cluster[e.id] = next_cluster_id
                    clusters.setdefault(next_cluster_id, []).append(e)
                next_cluster_id += 1
    
    # Add events with names that weren't clustered (unique names)
    for raw_event in raw_events:
        if raw_event.id in events_with_names and raw_event.id not in event_to_cluster:
            clusters[next_cluster_id] = [raw_event]
            event_to_cluster[raw_event.id] = next_cluster_id
            next_cluster_id += 1
    
    # Add events without names as singletons
    for raw_event in raw_events:
        if raw_event.id not in events_with_names:
            clusters[next_cluster_id] = [raw_event]
            next_cluster_id += 1
    
    # Deduplicate events within clusters
    result = []
    for cluster_id, events in clusters.items():
        seen_ids = set()
        unique_events = []
        for e in events:
            if e.id not in seen_ids:
                seen_ids.add(e.id)
                unique_events.append(e)
        if unique_events:
            result.append(unique_events)
    
    return result


def llm_cluster_events(raw_events: list[RawEvent]) -> list[list[RawEvent]]:
    """
    Use LLM to cluster events that couldn't be matched by victim name.
    
    Only called for singletons without victim names in the same date+city group.
    """
    if len(raw_events) <= 1:
        return [[e] for e in raw_events]
    
    logger.debug(f"[LLM Cluster] Clustering {len(raw_events)} events...")
    
    # Build prompt
    events_str = "\n\n".join([
        f"{i+1}. Extração:\n{format_raw_event_for_prompt(e)}"
        for i, e in enumerate(raw_events)
    ])
    
    prompt = f"""Analise as extrações abaixo e determine quais se referem ao MESMO evento real.

REGRAS DE MATCHING (em ordem de importância):

1. **VÍTIMA** (peso MÁXIMO): Se duas extrações mencionam a mesma vítima, são o MESMO evento.

2. **DATA + LOCAL** (peso alto): Mesmo dia + mesmo bairro/local sugere mesmo evento.

3. **DESCRIÇÃO** (peso médio): Descrições similares do crime ajudam a confirmar.

IMPORTANTE:
- Diferentes fontes podem descrever o mesmo evento de formas diferentes
- "Homem baleado na Maré" e "Tiroteio deixa um morto na Maré" podem ser o MESMO evento
- Se há dúvida, considere como eventos DIFERENTES

EXTRAÇÕES:
{events_str}

Responda com JSON válido:
{{
  "clusters": [
    [1, 3],  // extrações 1 e 3 são o mesmo evento
    [2],     // extração 2 é evento diferente
  ],
  "reasoning": "explicação breve"
}}"""

    try:
        settings = get_settings()
        client = instructor.from_provider(
            f"google/{settings.extraction_model}",
            api_key=settings.gemini_api_key,
        )
        
        from pydantic import BaseModel
        
        class ClusterResult(BaseModel):
            clusters: list[list[int]]
            reasoning: str
        
        result = client.create(
            response_model=ClusterResult,
            messages=[
                {"role": "user", "content": prompt}
            ],
            max_retries=2,
        )
        
        # Convert 1-indexed cluster numbers to RawEvent objects
        clusters = []
        for cluster_indices in result.clusters:
            cluster = []
            for idx in cluster_indices:
                if 1 <= idx <= len(raw_events):
                    cluster.append(raw_events[idx - 1])
            if cluster:
                clusters.append(cluster)
        
        if not clusters:
            logger.warning("[LLM Cluster] Empty result, treating each as separate")
            return [[e] for e in raw_events]
        
        logger.info(f"[LLM Cluster] ✅ Found {len(clusters)} cluster(s)")
        return clusters
        
    except Exception as e:
        logger.error(f"[LLM Cluster] Error: {e}, treating each as separate")
        return [[e] for e in raw_events]


def cluster_within_group(raw_events: list[RawEvent]) -> list[list[RawEvent]]:
    """
    Full clustering pipeline for a date+city group:
    1. Pre-cluster by victim name
    2. LLM cluster remaining singletons (if multiple)
    3. Return final clusters
    """
    if len(raw_events) <= 1:
        return [[e] for e in raw_events]
    
    # Step 1: Pre-cluster by victim name
    pre_clusters = pre_cluster_by_victim_name(raw_events)
    
    # Step 2: Check if we need LLM
    singletons = [c for c in pre_clusters if len(c) == 1]
    multi_clusters = [c for c in pre_clusters if len(c) > 1]
    
    # If all events are in multi-clusters (matched by victim), we're done
    if not singletons:
        return multi_clusters
    
    # If we have multiple singletons without victim names, use LLM to cluster them
    singletons_flat = [e for c in singletons for e in c]
    
    # Check if these singletons have no victim names
    singletons_without_names = [e for e in singletons_flat if not extract_victim_names(e)]
    
    if len(singletons_without_names) > 1:
        llm_clusters = llm_cluster_events(singletons_without_names)
        # Add singletons with names (they stay separate)
        singletons_with_names = [[e] for e in singletons_flat if extract_victim_names(e)]
        return multi_clusters + llm_clusters + singletons_with_names
    
    return pre_clusters


# =============================================================================
# UNIQUE EVENT CREATION
# =============================================================================


def select_best_raw_event(cluster: list[RawEvent]) -> RawEvent:
    """
    Select the best RawEvent to use as base for UniqueEvent.
    
    Priority:
    1. Has identified victim name
    2. Has most complete location (neighborhood, street)
    3. Has explicit date
    4. Most recent extraction
    """
    def score(raw_event: RawEvent) -> tuple:
        victim_names = extract_victim_names(raw_event)
        has_victim = 1 if victim_names else 0
        
        location_completeness = sum([
            1 if raw_event.neighborhood else 0,
            1 if raw_event.city else 0,
            1 if raw_event.state else 0,
        ])
        
        has_date = 1 if raw_event.event_date else 0
        
        # Use created_at as tiebreaker (most recent)
        created_ts = raw_event.created_at.timestamp() if raw_event.created_at else 0
        
        return (has_victim, location_completeness, has_date, created_ts)
    
    return max(cluster, key=score)


async def create_unique_event_from_cluster(cluster: list[RawEvent]) -> UniqueEvent:
    """
    Create UniqueEvent from a cluster of RawEvents.
    - Uses the RawEvent with most complete data as base
    - Links all RawEvents in cluster
    - Sets needs_enrichment=True
    """
    best = select_best_raw_event(cluster)
    victim_names = extract_victim_names(best)
    
    # Build victims_summary
    victims_summary = None
    if victim_names:
        victims_summary = ", ".join(victim_names)
    
    async with async_session_maker() as session:
        # Create UniqueEvent
        result = await session.execute(
            text("""
                INSERT INTO unique_event (
                    homicide_type, method_of_death, event_date, date_precision, time_of_day,
                    country, state, city, neighborhood, street, establishment, full_location_description,
                    victim_count, identified_victim_count, victims_summary,
                    perpetrator_count, security_force_involved,
                    title, chronological_description, additional_context,
                    merged_data, source_count, confirmed, needs_enrichment,
                    created_at, updated_at
                ) VALUES (
                    :homicide_type, :method_of_death, :event_date, :date_precision, :time_of_day,
                    :country, :state, :city, :neighborhood, :street, :establishment, :full_location_description,
                    :victim_count, :identified_victim_count, :victims_summary,
                    :perpetrator_count, :security_force_involved,
                    :title, :chronological_description, :additional_context,
                    :merged_data, :source_count, 0, 1,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
            """),
            {
                "homicide_type": best.homicide_type,
                "method_of_death": best.method_of_death,
                "event_date": best.event_date,
                "date_precision": best.date_precision,
                "time_of_day": best.time_of_day,
                "country": "Brasil",
                "state": best.state,
                "city": best.city,
                "neighborhood": best.neighborhood,
                "street": best.extraction_data.get("location_info", {}).get("street") if best.extraction_data else None,
                "establishment": best.extraction_data.get("location_info", {}).get("establishment") if best.extraction_data else None,
                "full_location_description": best.extraction_data.get("location_info", {}).get("full_location_description") if best.extraction_data else None,
                "victim_count": best.victim_count,
                "identified_victim_count": best.identified_victim_count,
                "victims_summary": victims_summary,
                "perpetrator_count": best.perpetrator_count,
                "security_force_involved": best.security_force_involved,
                "title": best.title,
                "chronological_description": best.chronological_description,
                "additional_context": best.extraction_data.get("additional_context") if best.extraction_data else None,
                "merged_data": json.dumps(best.extraction_data) if best.extraction_data else None,
                "source_count": len(cluster),
            }
        )
        
        # Get the new unique_event_id
        result = await session.execute(text("SELECT last_insert_rowid()"))
        unique_event_id = result.scalar()
        
        # Link all RawEvents in cluster
        raw_event_ids = [e.id for e in cluster]
        for raw_event_id in raw_event_ids:
            await session.execute(
                text("""
                    UPDATE raw_event 
                    SET unique_event_id = :unique_event_id,
                        deduplication_status = 'clustered',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :raw_event_id
                """),
                {"raw_event_id": raw_event_id, "unique_event_id": unique_event_id}
            )
        
        await session.commit()
        
        logger.info(f"[Create] Created UniqueEvent {unique_event_id} from {len(cluster)} RawEvent(s): {raw_event_ids}")
        
        # Return the created UniqueEvent
        result = await session.execute(
            text("SELECT * FROM unique_event WHERE id = :id"),
            {"id": unique_event_id}
        )
        row = result.fetchone()
        
        unique_event = UniqueEvent(
            id=row.id,
            event_date=parse_datetime(row.event_date),
            city=row.city,
            state=row.state,
            neighborhood=row.neighborhood,
            victims_summary=row.victims_summary,
            source_count=row.source_count,
            needs_enrichment=row.needs_enrichment,
        )
        
        # Send Telegram notification for new death
        await notify_new_death(
            unique_event_id=unique_event_id,
            title=best.title,
            city=best.city,
            state=best.state,
            event_date=best.event_date,
            victim_count=best.victim_count,
            victims_summary=victims_summary,
            homicide_type=best.homicide_type,
            source_count=len(cluster),
        )
        
        return unique_event


# =============================================================================
# BATCH PROCESSING FUNCTIONS
# =============================================================================


async def process_single_raw_event(raw_event_id: int) -> dict:
    """
    Phase 1: Immediate matching (called after extraction).
    
    1. Find candidates using blocking strategies
    2. If candidates: LLM match
    3. If match: link and mark for enrichment
    4. If no match: set deduplication_status='pending'
    """
    async with async_session_maker() as session:
        # Get the RawEvent
        result = await session.execute(
            text("SELECT * FROM raw_event WHERE id = :id"),
            {"id": raw_event_id}
        )
        row = result.fetchone()
        
        if not row:
            logger.warning(f"[Process] RawEvent {raw_event_id} not found")
            return {"status": "error", "raw_event_id": raw_event_id, "error": "Not found"}
        
        raw_event = RawEvent(
            id=row.id,
            event_date=parse_datetime(row.event_date),
            city=row.city,
            state=row.state,
            neighborhood=row.neighborhood,
            homicide_type=row.homicide_type,
            title=row.title,
            chronological_description=row.chronological_description,
            extraction_data=json.loads(row.extraction_data) if row.extraction_data else None,
            victim_count=row.victim_count,
            identified_victim_count=row.identified_victim_count,
            perpetrator_count=row.perpetrator_count,
            security_force_involved=row.security_force_involved,
            created_at=row.created_at,
        )
    
    logger.info(f"[Process] Processing RawEvent {raw_event_id}")
    
    # Step 1: Find candidates
    candidates = await find_candidate_unique_events(raw_event)
    
    if not candidates:
        # No candidates - mark as pending for batch processing
        async with async_session_maker() as session:
            await session.execute(
                text("""
                    UPDATE raw_event 
                    SET deduplication_status = 'pending',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                """),
                {"id": raw_event_id}
            )
            await session.commit()
        
        logger.info(f"[Process] RawEvent {raw_event_id}: No candidates, marked as pending")
        return {
            "status": "pending",
            "raw_event_id": raw_event_id,
            "candidates_found": 0,
        }
    
    # Step 2: LLM match
    logger.info(f"[Process] RawEvent {raw_event_id}: Found {len(candidates)} candidate(s)")
    matched, confidence, reasoning = llm_match_to_unique_event(raw_event, candidates)
    
    if matched:
        # Step 3: Link to UniqueEvent
        await link_raw_event_to_unique_event(raw_event_id, matched.id)
        
        return {
            "status": "matched",
            "raw_event_id": raw_event_id,
            "unique_event_id": matched.id,
            "confidence": confidence,
            "reasoning": reasoning,
        }
    else:
        # No match - mark as pending
        async with async_session_maker() as session:
            await session.execute(
                text("""
                    UPDATE raw_event 
                    SET deduplication_status = 'pending',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                """),
                {"id": raw_event_id}
            )
            await session.commit()
        
        logger.info(f"[Process] RawEvent {raw_event_id}: No match, marked as pending")
        return {
            "status": "pending",
            "raw_event_id": raw_event_id,
            "candidates_found": len(candidates),
            "confidence": confidence,
            "reasoning": reasoning,
        }


async def process_pending_deduplication(limit: int = 100) -> dict:
    """
    Phase 2: Batch clustering (called periodically).
    
    1. Get all RawEvents with deduplication_status='pending'
    2. Group by date+city
    3. Cluster within each group
    4. Create UniqueEvents for each cluster
    5. Link RawEvents and set deduplication_status='clustered'
    """
    async with async_session_maker() as session:
        # Get pending RawEvents
        result = await session.execute(
            text("""
                SELECT * FROM raw_event 
                WHERE deduplication_status = 'pending'
                ORDER BY event_date DESC
                LIMIT :limit
            """),
            {"limit": limit}
        )
        rows = result.fetchall()
    
    if not rows:
        logger.info("[Batch Dedup] No pending RawEvents to process")
        return {"status": "completed", "processed": 0, "unique_events_created": 0}
    
    # Convert to RawEvent objects
    raw_events = []
    for row in rows:
        raw_event = RawEvent(
            id=row.id,
            event_date=parse_datetime(row.event_date),
            city=row.city,
            state=row.state,
            neighborhood=row.neighborhood,
            homicide_type=row.homicide_type,
            title=row.title,
            chronological_description=row.chronological_description,
            extraction_data=json.loads(row.extraction_data) if row.extraction_data else None,
            victim_count=row.victim_count,
            identified_victim_count=row.identified_victim_count,
            perpetrator_count=row.perpetrator_count,
            security_force_involved=row.security_force_involved,
            method_of_death=row.method_of_death,
            date_precision=row.date_precision,
            time_of_day=row.time_of_day,
            created_at=parse_datetime(row.created_at),
        )
        raw_events.append(raw_event)
    
    logger.info(f"[Batch Dedup] Processing {len(raw_events)} pending RawEvent(s)")
    
    # Group by date+city
    groups = group_pending_by_date_city(raw_events)
    logger.info(f"[Batch Dedup] Grouped into {len(groups)} group(s)")
    
    # Process each group
    unique_events_created = 0
    raw_events_processed = 0
    
    for group_key, group_events in groups.items():
        logger.debug(f"[Batch Dedup] Processing group {group_key} with {len(group_events)} event(s)")
        
        # Cluster within group
        clusters = cluster_within_group(group_events)
        
        # Create UniqueEvent for each cluster
        for cluster in clusters:
            await create_unique_event_from_cluster(cluster)
            unique_events_created += 1
            raw_events_processed += len(cluster)
    
    logger.info(f"[Batch Dedup] ✅ Created {unique_events_created} UniqueEvent(s) from {raw_events_processed} RawEvent(s)")
    
    return {
        "status": "completed",
        "processed": raw_events_processed,
        "unique_events_created": unique_events_created,
        "groups_processed": len(groups),
    }


async def run_pending_enrichments(limit: int = 50, concurrency: int = 5) -> dict:
    """
    Process all UniqueEvents with needs_enrichment=True.
    
    Uses semaphore to limit concurrent LLM calls.
    """
    import asyncio
    
    async with async_session_maker() as session:
        result = await session.execute(
            text("""
                SELECT id FROM unique_event 
                WHERE needs_enrichment = 1
                LIMIT :limit
            """),
            {"limit": limit}
        )
        unique_event_ids = [row[0] for row in result.fetchall()]
    
    if not unique_event_ids:
        logger.info("[Enrichment] No UniqueEvents needing enrichment")
        return {"status": "completed", "enriched": 0}
    
    logger.info(f"[Enrichment] Processing {len(unique_event_ids)} UniqueEvent(s)")
    
    semaphore = asyncio.Semaphore(concurrency)
    
    async def enrich_with_limit(unique_event_id: int):
        async with semaphore:
            return await enrich_unique_event(unique_event_id)
    
    results = await asyncio.gather(
        *[enrich_with_limit(uid) for uid in unique_event_ids],
        return_exceptions=True
    )
    
    successful = sum(1 for r in results if not isinstance(r, Exception) and r)
    failed = len(results) - successful
    
    logger.info(f"[Enrichment] ✅ Enriched {successful}, failed {failed}")
    
    return {
        "status": "completed",
        "enriched": successful,
        "failed": failed,
    }


async def enrich_unique_event(unique_event_id: int) -> bool:
    """
    Synthesize best information from all linked sources.
    
    1. Fetch all linked RawEvents and their SourceGoogleNews content
    2. Call LLM to synthesize best information
    3. Update UniqueEvent fields
    4. Set needs_enrichment=False, update last_enriched_at
    """
    logger.info(f"[Enrich] Enriching UniqueEvent {unique_event_id}")
    
    async with async_session_maker() as session:
        # Get UniqueEvent
        result = await session.execute(
            text("SELECT * FROM unique_event WHERE id = :id"),
            {"id": unique_event_id}
        )
        unique_row = result.fetchone()
        
        if not unique_row:
            logger.warning(f"[Enrich] UniqueEvent {unique_event_id} not found")
            return False
        
        # Get linked RawEvents
        result = await session.execute(
            text("""
                SELECT re.*, sgn.content, sgn.headline, sgn.publisher_name, sgn.resolved_url
                FROM raw_event re
                LEFT JOIN source_google_news sgn ON re.source_google_news_id = sgn.id
                WHERE re.unique_event_id = :unique_event_id
            """),
            {"unique_event_id": unique_event_id}
        )
        source_rows = result.fetchall()
    
    if not source_rows:
        logger.warning(f"[Enrich] No linked RawEvents for UniqueEvent {unique_event_id}")
        # Mark as enriched anyway (nothing to enrich)
        async with async_session_maker() as session:
            await session.execute(
                text("""
                    UPDATE unique_event 
                    SET needs_enrichment = 0, 
                        last_enriched_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                """),
                {"id": unique_event_id}
            )
            await session.commit()
        return True
    
    # Build enrichment data
    sources_info = []
    all_extraction_data = []
    
    for row in source_rows:
        extraction_data = json.loads(row.extraction_data) if row.extraction_data else {}
        all_extraction_data.append(extraction_data)
        
        sources_info.append({
            "raw_event_id": row.id,
            "headline": row.headline,
            "publisher": row.publisher_name,
            "url": row.resolved_url,
            "content": (row.content or "")[:3000],  # Limit content length
            "extraction": extraction_data,
        })
    
    # Build LLM prompt for enrichment
    event_date = parse_datetime(unique_row.event_date)
    current_state = {
        "title": unique_row.title,
        "event_date": event_date.strftime('%Y-%m-%d') if event_date else None,
        "city": unique_row.city,
        "state": unique_row.state,
        "neighborhood": unique_row.neighborhood,
        "street": unique_row.street,
        "victims_summary": unique_row.victims_summary,
        "chronological_description": unique_row.chronological_description,
    }
    
    sources_str = ""
    for i, source in enumerate(sources_info, 1):
        sources_str += f"""
{i}. Fonte: {source['publisher'] or 'Desconhecida'}
   Manchete: {source['headline'] or 'N/A'}
   URL: {source['url'] or 'N/A'}
   Conteúdo: {source['content'][:1000]}...
"""
    
    prompt = f"""Você é um especialista em sintetizar informações sobre eventos de morte violenta a partir de múltiplas fontes.

ESTADO ATUAL DO EVENTO:
- Título: {current_state['title']}
- Data: {current_state['event_date']}
- Cidade: {current_state['city']}
- Estado: {current_state['state']}
- Bairro: {current_state['neighborhood']}
- Rua: {current_state['street']}
- Vítimas: {current_state['victims_summary']}
- Descrição: {current_state['chronological_description']}

FONTES DE NOTÍCIAS ({len(sources_info)} fontes):
{sources_str}

Sua tarefa é sintetizar a informação mais COMPLETA e PRECISA possível, combinando todas as fontes.

REGRAS:
1. Use informações de TODAS as fontes para criar a descrição mais completa
2. Se fontes conflitam, prefira a informação mais detalhada e consistente
3. Extraia informações de localização estruturadas quando possível
4. NÃO invente informações - use apenas o que está nas fontes
5. Mantenha linguagem técnica e objetiva

Retorne APENAS JSON válido:
{{
  "title": "título técnico descritivo",
  "event_date": "YYYY-MM-DD ou null",
  "city": "cidade",
  "state": "estado (sigla)",
  "neighborhood": "bairro ou null",
  "street": "rua/endereço ou null",
  "victims_summary": "informação completa sobre vítimas",
  "victim_count": número ou null,
  "chronological_description": "descrição cronológica completa e detalhada"
}}"""

    try:
        settings = get_settings()
        client = instructor.from_provider(
            f"google/{settings.extraction_model}",
            api_key=settings.gemini_api_key,
        )
        
        from pydantic import BaseModel
        
        class EnrichmentResult(BaseModel):
            title: str | None
            event_date: str | None
            city: str | None
            state: str | None
            neighborhood: str | None
            street: str | None
            victims_summary: str | None
            victim_count: int | None
            chronological_description: str | None
        
        result = client.create(
            response_model=EnrichmentResult,
            messages=[
                {"role": "user", "content": prompt}
            ],
            max_retries=2,
        )
        
        # Update UniqueEvent with enriched data
        async with async_session_maker() as session:
            await session.execute(
                text("""
                    UPDATE unique_event 
                    SET title = COALESCE(:title, title),
                        city = COALESCE(:city, city),
                        state = COALESCE(:state, state),
                        neighborhood = COALESCE(:neighborhood, neighborhood),
                        street = COALESCE(:street, street),
                        victims_summary = COALESCE(:victims_summary, victims_summary),
                        victim_count = COALESCE(:victim_count, victim_count),
                        chronological_description = COALESCE(:chronological_description, chronological_description),
                        needs_enrichment = 0,
                        last_enriched_at = CURRENT_TIMESTAMP,
                        enrichment_model = :enrichment_model,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                """),
                {
                    "id": unique_event_id,
                    "title": result.title,
                    "city": result.city,
                    "state": result.state,
                    "neighborhood": result.neighborhood,
                    "street": result.street,
                    "victims_summary": result.victims_summary,
                    "victim_count": result.victim_count,
                    "chronological_description": result.chronological_description,
                    "enrichment_model": settings.extraction_model,
                }
            )
            await session.commit()
        
        logger.info(f"[Enrich] ✅ Enriched UniqueEvent {unique_event_id}")
        return True
        
    except Exception as e:
        import traceback
        logger.error(f"[Enrich] Error enriching UniqueEvent {unique_event_id}: {e}\n{traceback.format_exc()}")
        return False

