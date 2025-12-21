"""Event extraction service using LLM with structured output."""

import json
import os
from datetime import datetime

import instructor
from loguru import logger
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import get_settings
from app.database import async_session_maker
from app.models import RawEvent, SourceGoogleNews, SourceStatus
from app.services.extraction_schemas import ViolentDeathEvent


# System prompt for extraction
EXTRACTION_SYSTEM_PROMPT = """
Você é um assistente especializado em extrair informações de notícias sobre mortes violentas 
e convertê-las em descrições técnicas seguindo padrões profissionais de escrivães 
de polícia no Brasil.

PRINCÍPIOS FUNDAMENTAIS:
1. Use APENAS informações explicitamente presentes no texto
2. NUNCA invente, calcule ou infira informações
3. Para campos opcionais, deixe null se a informação não estiver disponível
4. Mantenha objetividade e neutralidade absoluta
5. Use terminologia jurídica formal e precisa

REGRA CRÍTICA SOBRE DATAS - LEIA COM ATENÇÃO:

Você receberá metadados da notícia incluindo a DATA DE PUBLICAÇÃO. Use esta informação 
para resolver datas relativas mencionadas no texto.

RESOLUÇÃO DE DATAS RELATIVAS:
Se a notícia foi publicada em 21/12/2025 e o texto menciona:
- "ontem" → 20/12/2025
- "anteontem" → 19/12/2025
- "na sexta-feira" → calcule qual sexta-feira mais recente antes da publicação
- "nesta semana" → semana da publicação
- "há três dias" → 18/12/2025

QUANDO PODE INFERIR A DATA (has_explicit_date = TRUE):
1. Data completa explícita: "15 de dezembro de 2025", "20/11/2025"
2. Data relativa COM referência de publicação: "ontem" quando você sabe a data de publicação
3. Dia da semana COM número: "sexta-feira (12)" quando você pode verificar pelo contexto

QUANDO NÃO PODE INFERIR (has_explicit_date = FALSE):
1. Termos vagos sem referência: "recentemente", "há alguns dias"
2. Não há data de publicação fornecida E texto usa termos relativos
3. Ambiguidade que não pode ser resolvida

O campo date_verification funciona como um VERIFICADOR:
1. has_explicit_date = TRUE se você consegue determinar a data completa (dia/mês/ano)
2. date_source = "explicit" se está no texto, "inferred_from_publication" se calculada
3. verification_reasoning deve explicar como você chegou à data

Se has_explicit_date = FALSE, o campo date DEVE ser null.

IMPORTANTE: 
- Use a data de publicação para resolver datas relativas
- Documente no verification_reasoning como você resolveu a data
- É MELHOR deixar date como null do que inventar uma data incorreta

SOBRE TÍTULOS:
- Se não há data completa verificada, use "DATA NÃO INFORMADA" no título
- Exemplo: "FEMINICÍDIO - RESIDÊNCIA SANTA CRUZ - DATA NÃO INFORMADA"
"""


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


def extract_event_from_content(
    content: str, 
    metadata: dict | None = None,
    model_id: str | None = None
) -> ViolentDeathEvent:
    """
    Extract structured event data from news content using LLM.
    
    Args:
        content: News article text
        metadata: Optional source metadata (headline, published_at, publisher, url)
        model_id: Optional model ID override
    
    Returns:
        ViolentDeathEvent with extracted data
    """
    settings = get_settings()
    api_key = settings.gemini_api_key
    
    if not api_key:
        raise ValueError("GEMINI_API_KEY not configured")
    
    model = model_id or settings.extraction_model
    
    client = instructor.from_provider(
        f"google/{model}",
        api_key=api_key,
    )
    
    # Build user message with metadata context
    user_message = _build_extraction_prompt(content, metadata)
    
    event = client.create(
        response_model=ViolentDeathEvent,
        messages=[
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        max_retries=3,
    )
    
    return event


def _build_extraction_prompt(content: str, metadata: dict | None = None) -> str:
    """
    Build the extraction prompt with metadata context.
    
    The metadata provides important context for date resolution:
    - published_at: When the article was published
    - headline: The article title
    - publisher: Source of the news
    - url: Original article URL
    """
    if not metadata:
        return content
    
    parts = ["## METADADOS DA NOTÍCIA\n"]
    
    if metadata.get("published_at"):
        parts.append(f"**Data de Publicação:** {metadata['published_at']}")
        parts.append("(Use esta data como referência para resolver datas relativas como 'ontem', 'na sexta-feira', etc.)\n")
    
    if metadata.get("headline"):
        parts.append(f"**Manchete:** {metadata['headline']}\n")
    
    if metadata.get("publisher"):
        parts.append(f"**Fonte:** {metadata['publisher']}\n")
    
    if metadata.get("url"):
        parts.append(f"**URL:** {metadata['url']}\n")
    
    parts.append("\n## CONTEÚDO DA NOTÍCIA\n")
    parts.append(content)
    
    return "\n".join(parts)


async def extract_source(source_id: int) -> RawEvent | None:
    """
    Extract event data from a downloaded source and create RawEvent.
    
    Args:
        source_id: ID of the SourceGoogleNews to process
    
    Returns:
        RawEvent if successful, None otherwise
    """
    from sqlalchemy import text
    
    async with async_session_maker() as session:
        # Get the source content and metadata using raw SQL
        result = await session.execute(
            text("""
                SELECT id, headline, content, published_at, publisher_name, resolved_url 
                FROM source_google_news 
                WHERE id = :id
            """),
            {"id": source_id}
        )
        row = result.fetchone()
        
        if not row:
            logger.warning(f"Source {source_id} not found")
            return None
        
        source_id_db, headline, content, published_at, publisher_name, resolved_url = row
        
        if not content:
            logger.warning(f"Source {source_id} has no content")
            return None
        
        headline_preview = (headline or "")[:50]
        logger.info(f"Extracting event from source {source_id}: {headline_preview}...")
        
        # Build metadata context for the LLM
        metadata = {
            "headline": headline,
            "publisher": publisher_name,
            "url": resolved_url,
        }
        
        # Format published_at for the LLM
        if published_at:
            try:
                from datetime import datetime as dt
                if isinstance(published_at, str):
                    pub_date = dt.fromisoformat(published_at.replace('Z', '+00:00'))
                else:
                    pub_date = published_at
                metadata["published_at"] = pub_date.strftime("%d/%m/%Y às %H:%M")
            except Exception as e:
                logger.debug(f"Could not format published_at: {e}")
                metadata["published_at"] = str(published_at)
        
        try:
            # Extract structured event data with metadata context
            event = extract_event_from_content(content, metadata=metadata)
            event_data = event.model_dump()
            
            # Parse date string to datetime if present
            event_date = None
            if event.date_time.date:
                try:
                    from datetime import datetime as dt
                    event_date = dt.strptime(event.date_time.date, "%Y-%m-%d")
                except ValueError:
                    logger.warning(f"Could not parse date: {event.date_time.date}")
            
            # Create RawEvent with denormalized fields
            raw_event = RawEvent(
                source_google_news_id=source_id,
                # Denormalized queryable fields
                event_date=event_date,
                date_precision=event.date_time.date_precision,
                time_of_day=event.date_time.time_of_day,
                city=event.location_info.city,
                state=event.location_info.state,
                neighborhood=event.location_info.neighborhood,
                victim_count=event.victims.number_of_victims,
                identified_victim_count=event.victims.number_of_identifiable_victims,
                perpetrator_count=event.perpetrators.number_of_perpetrators if event.perpetrators else None,
                homicide_type=event.homicide_dynamic.homicide_type,
                method_of_death=event.homicide_dynamic.method,
                title=event.homicide_dynamic.title,
                chronological_description=event.homicide_dynamic.chronological_description,
                # Full structured data as JSON
                extraction_data=event_data,
                extraction_model=get_settings().extraction_model,
                extraction_success=True,
            )
            
            session.add(raw_event)
            
            # Update source status using raw SQL
            await session.execute(
                text("""
                    UPDATE source_google_news 
                    SET status = 'extracted', updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                """),
                {"id": source_id}
            )
            
            await session.commit()
            await session.refresh(raw_event)
            
            logger.info(f"Created RawEvent {raw_event.id} for source {source_id}")
            return raw_event
            
        except Exception as e:
            logger.error(f"Extraction failed for source {source_id}: {e}")
            await session.execute(
                text("""
                    UPDATE source_google_news 
                    SET status = 'failed_in_extraction', updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                """),
                {"id": source_id}
            )
            await session.commit()
            return None


async def extract_ready_sources(limit: int = 10, concurrency: int = 15) -> dict:
    """
    Extract events from all sources ready for extraction (in parallel).
    
    Args:
        limit: Maximum number of sources to process
        concurrency: Maximum number of parallel extractions
    
    Returns:
        Dict with extraction statistics
    """
    import asyncio
    from sqlalchemy import text
    
    async with async_session_maker() as session:
        # Atomically select AND mark sources as 'extracting' to prevent race conditions
        # This prevents multiple parallel workers from extracting the same source
        
        # First, get the IDs we want to claim
        result = await session.execute(
            text("""
                SELECT id FROM source_google_news 
                WHERE status = 'ready_for_extraction' 
                AND content IS NOT NULL 
                LIMIT :limit
            """),
            {"limit": limit}
        )
        candidate_ids = [row[0] for row in result.fetchall()]
        
        if not candidate_ids:
            logger.info(f"Found 0 sources ready for extraction")
            return {
                "processed": 0,
                "successful": 0,
                "failed": 0,
            }
        
        # Atomically claim these sources by updating status
        # Only sources still in 'ready_for_extraction' will be updated
        await session.execute(
            text("""
                UPDATE source_google_news 
                SET status = 'extracting', updated_at = CURRENT_TIMESTAMP
                WHERE id IN ({}) AND status = 'ready_for_extraction'
            """.format(",".join(str(id) for id in candidate_ids)))
        )
        await session.commit()
        
        # Now get the IDs we actually claimed (those now in 'extracting' status)
        result = await session.execute(
            text("""
                SELECT id FROM source_google_news 
                WHERE id IN ({}) AND status = 'extracting'
            """.format(",".join(str(id) for id in candidate_ids)))
        )
        source_ids = [row[0] for row in result.fetchall()]
    
    logger.info(f"Claimed {len(source_ids)} sources for extraction (marked as extracting)")
    
    if not source_ids:
        return {
            "processed": 0,
            "successful": 0,
            "failed": 0,
        }
    
    # Semaphore to limit concurrency
    semaphore = asyncio.Semaphore(concurrency)
    
    async def extract_with_limit(source_id: int):
        async with semaphore:
            return await extract_source(source_id)
    
    # Run extractions in parallel with concurrency limit
    logger.info(f"Starting parallel extraction with concurrency={concurrency}")
    results = await asyncio.gather(
        *[extract_with_limit(sid) for sid in source_ids],
        return_exceptions=True
    )
    
    successful = 0
    failed = 0
    raw_events = []
    
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Extraction failed with exception: {result}")
            failed += 1
        elif result is not None:
            successful += 1
            raw_events.append(result)
        else:
            failed += 1
    
    logger.info(f"Extraction complete: {successful} successful, {failed} failed")
    
    return {
        "processed": len(source_ids),
        "successful": successful,
        "failed": failed,
        "raw_event_ids": [e.id for e in raw_events],
    }

