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

Você DEVE preencher o campo date_verification PRIMEIRO, antes de qualquer extração de data.

O campo date_verification funciona como um VERIFICADOR que impede datas inventadas:

1. has_explicit_date = TRUE SOMENTE se o texto contém data COMPLETA (dia/mês/ano)
   Exemplos de TRUE:
   - "15 de dezembro de 2025"
   - "em 12 de março de 2024"
   - "no dia 20/11/2025"
   
2. has_explicit_date = FALSE se o texto tem apenas:
   - Dias da semana: "sexta-feira (12)", "na segunda-feira (15)"
   - Termos relativos: "ontem", "hoje", "na semana passada"
   - Períodos: "recentemente", "há três dias"
   
3. Se has_explicit_date = FALSE, o campo date DEVE ser null
   Não há exceções. O validador vai rejeitar se você tentar preencher date quando has_explicit_date é FALSE.
   
4. year_explicitly_mentioned deve ser TRUE apenas se o ANO aparece no texto da data

5. verification_reasoning deve explicar claramente por que você decidiu TRUE ou FALSE

IMPORTANTE: É MELHOR deixar date como null do que inventar uma data.
Dados incompletos são preferíveis a dados falsos.

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


def extract_event_from_content(content: str, model_id: str | None = None) -> ViolentDeathEvent:
    """
    Extract structured event data from news content using LLM.
    
    Args:
        content: News article text
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
    
    event = client.create(
        response_model=ViolentDeathEvent,
        messages=[
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        max_retries=3,
    )
    
    return event


async def extract_source(source_id: int) -> RawEvent | None:
    """
    Extract event data from a downloaded source and create RawEvent.
    
    Args:
        source_id: ID of the SourceGoogleNews to process
    
    Returns:
        RawEvent if successful, None otherwise
    """
    async with async_session_maker() as session:
        # Get the source
        source = await session.get(SourceGoogleNews, source_id)
        if not source:
            logger.warning(f"Source {source_id} not found")
            return None
        
        if not source.content:
            logger.warning(f"Source {source_id} has no content")
            return None
        
        logger.info(f"Extracting event from source {source_id}: {source.headline[:50]}...")
        
        try:
            # Extract structured event data
            event = extract_event_from_content(source.content)
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
                source_google_news_id=source.id,
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
            
            # Update source status
            source.status = SourceStatus.processed
            source.updated_at = datetime.utcnow()
            
            await session.commit()
            await session.refresh(raw_event)
            
            logger.info(f"Created RawEvent {raw_event.id} for source {source_id}")
            return raw_event
            
        except Exception as e:
            logger.error(f"Extraction failed for source {source_id}: {e}")
            source.status = SourceStatus.failed
            source.updated_at = datetime.utcnow()
            await session.commit()
            return None


async def extract_downloaded_sources(limit: int = 10) -> dict:
    """
    Extract events from all downloaded sources.
    
    Args:
        limit: Maximum number of sources to process
    
    Returns:
        Dict with extraction statistics
    """
    async with async_session_maker() as session:
        # Get downloaded sources that haven't been processed
        result = await session.exec(
            select(SourceGoogleNews)
            .where(SourceGoogleNews.status == SourceStatus.downloaded)
            .where(SourceGoogleNews.content.isnot(None))
            .limit(limit)
        )
        sources = result.all()
    
    logger.info(f"Found {len(sources)} downloaded sources to extract")
    
    if not sources:
        return {
            "processed": 0,
            "successful": 0,
            "failed": 0,
        }
    
    successful = 0
    failed = 0
    raw_events = []
    
    for source in sources:
        raw_event = await extract_source(source.id)
        if raw_event:
            successful += 1
            raw_events.append(raw_event)
        else:
            failed += 1
    
    logger.info(f"Extraction complete: {successful} successful, {failed} failed")
    
    return {
        "processed": len(sources),
        "successful": successful,
        "failed": failed,
        "raw_event_ids": [e.id for e in raw_events],
    }

