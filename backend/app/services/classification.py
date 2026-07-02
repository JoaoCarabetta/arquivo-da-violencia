"""Classification service - classifies headlines to filter violent death news."""

from datetime import datetime
from typing import Literal, Optional

import instructor
from loguru import logger
from pydantic import BaseModel, Field
from sqlmodel import select
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.config import get_settings
from app.database import async_session_maker
from app.models import SourceGoogleNews, SourceStatus


class ViolentDeathClassification(BaseModel):
    """Classification result for whether news is about a violent death."""
    
    is_violent_death: bool = Field(
        ...,
        description="""
        TRUE only if the headline is about one or more NEW violent deaths in Brazil
        (homicides, murders, killings, police operations with deaths).

        Examples of TRUE:
        - "Homem é morto a tiros em operação policial"
        - "Corpo é encontrado com marcas de violência"
        - "Tiroteio deixa dois mortos na Zona Norte"
        - "Mulher é assassinada pelo ex-marido"

        Examples of FALSE:
        - "Polícia prende suspeito de roubo"
        - "Homem sobrevive após ser baleado"
        - "Vítima de facadas chora no julgamento do agressor" (victim alive)
        - "Atirador em massa no Texas recebe pena de morte" (foreign event)
        - "Operação apreende drogas e armas"
        """
    )
    confidence: Literal["alta", "média", "baixa"] = Field(
        ...,
        description="""
        Confidence level in the classification:
        - "alta": Clear case, headline explicitly mentions death/killing
        - "média": Death likely but not explicit in headline
        - "baixa": Ambiguous, might be about violence without death
        """
    )
    
    reasoning: str = Field(
        ...,
        description="Brief explanation (1-2 sentences) of why this classification was made."
    )

    is_single_incident: bool = Field(
        ...,
        description="""
        TRUE if the headline describes ONE specific violent-death incident (or a single
        clearly bounded event such as one shootout with N victims).

        FALSE for aggregate statistics, year-end crime reports, multi-city roundups,
        foreign disasters, suicides, animal cruelty, policy/analysis pieces, or any
        headline that is not about a discrete incident.
        """
    )

    content_class_hint: Optional[
        Literal[
            "incident",
            "aggregate_statistics",
            "foreign",
            "non_incident",
            "suicide",
            "accident_disaster",
        ]
    ] = Field(
        None,
        description="Optional hint about why the headline is or is not a single incident.",
    )


# System prompt for classification
CLASSIFICATION_SYSTEM_PROMPT = """
Você é um classificador de manchetes de notícias do GOOGLE NEWS BRASIL. Sua tarefa é:
1. Determinar se a manchete indica NOTÍCIA sobre MORTE(S) VIOLENTA(S) no Brasil.
2. Determinar se descreve UM ÚNICO INCIDENTE específico (is_single_incident).

Este filtro alimenta um arquivo de violência no Rio de Janeiro. Manchetes sobre mortes
violentas no exterior NÃO entram, mesmo que mencionem tiroteio, guerra ou assassinato.

CLASSIFIQUE COMO MORTE VIOLENTA (is_violent_death = true):
- Morte violenta no Brasil: morto(s), assassinado(s), executado(s), baleado(s) MORTO
- Corpo, restos mortais ou ossada encontrados com indícios de violência
- Tiroteio/confronto/operação policial que deixa mortos (inclui jargão: "neutralizado",
  "CPF cancelado" no sentido de pessoa morta)
- Feminicídio, latrocínio, homicídio, chacina, execução
- Vítima que MORRE: "não resistiu aos ferimentos", "morre após ser baleado"

NÃO CLASSIFIQUE COMO MORTE VIOLENTA (is_violent_death = false):
- Eventos FORA DO BRASIL (EUA, Europa, Rússia, Ucrânia, México, etc.), mesmo com mortes
- Vítima VIVA: sobrevive, ferido(s), hospitalizado, chora, presta depoimento, "vítima de
  X facadas" no julgamento (sobrevivente), tentativa de homicídio sem morte
- Tiroteio, operação ou confronto SEM menção a morte ou feridos mortos
- Prisões, mandados, julgamentos, pena de morte como sentença judicial (notícia jurídica)
- Apreensões de armas/drogas, políticas de segurança
- Metáforas ("assassinato da língua", "executa o orçamento")
- Acidentes (trânsito, queda) sem homicídio doloso
- Arsenal apreendido para crimes futuros (crime frustrado, sem morte na notícia)

INCIDENTE ÚNICO (is_single_incident = true):
- Um homicídio ou tiroteio específico no Brasil, em local identificável
- "Tiroteio deixa dois mortos na Zona Norte" (um evento)
- "Homem é morto a tiros em operação policial"

NÃO É INCIDENTE ÚNICO (is_single_incident = false) — descarte mesmo se mencionar mortes:
- Estatísticas agregadas: balanço anual, CVLI, "X mortes em 2025", "no estado", painéis
- Notícias estrangeiras: terremotos, guerras, desastres fora do Brasil
- Suicídios (mesmo violentos)
- Crueldade contra animais
- Resumos com múltiplos incidentes não relacionados
- Análises/políticas públicas sobre violência sem um caso específico

Use content_class_hint quando aplicável: incident, aggregate_statistics, foreign,
non_incident, suicide, accident_disaster.

Baseie-se APENAS no texto da manchete. Em dúvida sobre local (Brasil vs exterior), procure
topônimos estrangeiros (Texas, EUA, Rússia, Ucrânia) ou contexto claramente internacional.
"""

CONTENT_CLASSIFICATION_SYSTEM_PROMPT = """
Você é um classificador de ARTIGOS JORNALÍSTICOS do Google News Brasil. A manchete já passou
por um filtro inicial, mas o CORPO do artigo pode revelar que a matéria NÃO descreve um
incidente único de morte violenta no Brasil.

Sua tarefa:
1. Determinar se o artigo trata de MORTE(S) VIOLENTA(S) no Brasil.
2. Determinar se descreve UM ÚNICO INCIDENTE específico (is_single_incident).

Use a manchete apenas como contexto. Baseie a decisão principalmente no corpo do artigo.

CLASSIFIQUE COMO MORTE VIOLENTA (is_violent_death = true):
- Morte violenta no Brasil descrita no corpo: homicídio, tiroteio, operação policial com morte
- Corpo/restos encontrados com indícios de violência
- Feminicídio, latrocínio, chacina, execução

NÃO CLASSIFIQUE COMO MORTE VIOLENTA (is_violent_death = false):
- Eventos FORA DO BRASIL (desastres, guerras, crimes internacionais)
- Vítima sobrevive ou matéria é sobre julgamento/pena sem novo óbito
- Apreensões, políticas, análises sem caso específico

INCIDENTE ÚNICO (is_single_incident = true):
- Um homicídio ou tiroteio específico no Brasil, em local identificável
- Um evento claramente delimitado ("tiroteio deixa dois mortos na Zona Norte")

NÃO É INCIDENTE ÚNICO (is_single_incident = false) — descarte:
- Estatísticas agregadas: balanço anual, CVLI, totais estaduais/nacionais, "X mortes em 2025"
- Notícias estrangeiras mesmo que a manchete pareça local
- Suicídios, crueldade contra animais, acidentes sem homicídio doloso
- Resumos com múltiplos incidentes não relacionados

Use content_class_hint quando aplicável: incident, aggregate_statistics, foreign,
non_incident, suicide, accident_disaster.
"""

# Truncate article bodies before LLM content classification (~8k chars).
CONTENT_CLASSIFICATION_MAX_CHARS = 8000


def get_classification_client(*, model: str | None = None):
    """Get instructor client for classification using the selection model."""
    settings = get_settings()

    if not settings.gemini_api_key:
        raise ValueError("GEMINI_API_KEY not configured")

    model_name = model or settings.selection_model
    return instructor.from_provider(
        f"google/{model_name}",
        api_key=settings.gemini_api_key,
    )


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
def classify_headline(
    headline: str,
    *,
    system_prompt: str | None = None,
    model: str | None = None,
) -> ViolentDeathClassification:
    """
    Classify a headline to determine if it's about violent death.

    Uses tenacity for retries with exponential backoff.

    Args:
        headline: News headline text
        system_prompt: Optional override for the classification system prompt
        model: Optional override for the Gemini model name

    Returns:
        ViolentDeathClassification with is_violent_death, confidence, and reasoning
    """
    client = get_classification_client(model=model)
    prompt = system_prompt or CLASSIFICATION_SYSTEM_PROMPT

    result = client.create(
        response_model=ViolentDeathClassification,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Classifique esta manchete:\n\n{headline}"},
        ],
        max_retries=2,  # Instructor's internal retry
    )

    return result


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
def classify_article_content(
    headline: str,
    content: str,
    *,
    system_prompt: str | None = None,
    model: str | None = None,
) -> ViolentDeathClassification:
    """Classify downloaded article body before extraction."""
    client = get_classification_client(model=model)
    prompt = system_prompt or CONTENT_CLASSIFICATION_SYSTEM_PROMPT
    truncated = content[:CONTENT_CLASSIFICATION_MAX_CHARS]

    result = client.create(
        response_model=ViolentDeathClassification,
        messages=[
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": (
                    f"Manchete:\n{headline}\n\n"
                    f"Corpo do artigo:\n{truncated}"
                ),
            },
        ],
        max_retries=2,
    )

    return result


def passes_content_gate(classification: ViolentDeathClassification) -> bool:
    """Whether article content should proceed to extraction."""
    return classification.is_violent_death and classification.is_single_incident


def format_content_gate_reasoning(
    classification: ViolentDeathClassification,
    *,
    method: str,
) -> str:
    """Build classification_reasoning suffix for content-gate discards."""
    hint = classification.content_class_hint or "non-incident"
    return (
        f"{classification.reasoning} "
        f"[content_gate={method}, single_incident={classification.is_single_incident}, hint={hint}]"
    )


async def classify_source(source_id: int) -> bool:
    """
    Classify a single source by its headline.
    
    Updates the source with classification results and changes status to
    ready-for-download or discarded.
    
    Args:
        source_id: ID of the SourceGoogleNews to classify
    
    Returns:
        True if classified as violent death, False otherwise
    """
    import asyncio
    from sqlalchemy import text

    # Step 1: read the headline in a short-lived session, then release the
    # connection. We must NOT hold a DB connection while the (slow, blocking)
    # LLM call runs, otherwise concurrent workers exhaust the connection pool.
    async with async_session_maker() as session:
        result = await session.execute(
            text("SELECT id, headline FROM source_google_news WHERE id = :id"),
            {"id": source_id}
        )
        row = result.fetchone()

        if not row:
            logger.warning(f"Source {source_id} not found")
            return False

        source_id, headline = row

        if not headline:
            logger.warning(f"Source {source_id} has no headline")
            await session.execute(
                text("""
                    UPDATE source_google_news 
                    SET status = 'discarded', 
                        is_violent_death = 0,
                        classification_reasoning = 'No headline available',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                """),
                {"id": source_id}
            )
            await session.commit()
            return False

    # Step 2: run the blocking LLM classification off the event loop and
    # WITHOUT holding a DB connection.
    try:
        logger.info(f"Classifying source {source_id}: {headline[:60]}...")
        classification = await asyncio.to_thread(classify_headline, headline)
    except Exception as e:
        logger.error(f"Error classifying source {source_id}: {e}")
        async with async_session_maker() as session:
            await session.execute(
                text("""
                    UPDATE source_google_news
                    SET status = 'ready_for_classification', updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id AND status = 'classifying'
                """),
                {"id": source_id},
            )
            await session.commit()
        return False

    # Step 3: persist the result in a fresh short-lived session.
    passes_gate = classification.is_violent_death and classification.is_single_incident
    new_status = "ready_for_download" if passes_gate else "discarded"

    reasoning = classification.reasoning
    if classification.is_violent_death and not classification.is_single_incident:
        hint = classification.content_class_hint or "non-incident"
        reasoning = f"{reasoning} [single_incident=false, hint={hint}]"

    async with async_session_maker() as session:
        await session.execute(
            text("""
                UPDATE source_google_news 
                SET status = :status,
                    is_violent_death = :is_violent_death,
                    classification_confidence = :confidence,
                    classification_reasoning = :reasoning,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
            """),
            {
                "id": source_id,
                "status": new_status,
                "is_violent_death": 1 if classification.is_violent_death else 0,
                "confidence": classification.confidence,
                "reasoning": reasoning,
            }
        )
        await session.commit()

    if passes_gate:
        logger.info(f"Source {source_id}: VIOLENT DEATH ({classification.confidence})")
    else:
        logger.info(f"Source {source_id}: DISCARDED ({classification.confidence})")

    return passes_gate


async def classify_pending_sources(limit: int = 50, concurrency: int = 10) -> dict:
    """
    Batch classify all sources that are ready for classification (in parallel).
    
    Args:
        limit: Maximum number of sources to process
        concurrency: Maximum number of parallel classifications
    
    Returns:
        Dict with classification statistics
    """
    import asyncio
    
    # Use raw SQL to avoid SQLAlchemy enum caching issues
    async with async_session_maker() as session:
        from sqlalchemy import text
        result = await session.execute(
            text("""
                SELECT id FROM source_google_news 
                WHERE status = 'ready_for_classification' 
                AND headline IS NOT NULL 
                LIMIT :limit
            """),
            {"limit": limit}
        )
        candidate_ids = [row[0] for row in result.fetchall()]
        
        if not candidate_ids:
            logger.info(f"Found 0 sources to classify")
            return {
                "processed": 0,
                "violent_death": 0,
                "discarded": 0,
                "errors": 0,
            }
        
        # Atomically claim these sources by updating status to prevent race conditions
        await session.execute(
            text("""
                UPDATE source_google_news 
                SET status = 'classifying', updated_at = CURRENT_TIMESTAMP
                WHERE id IN ({}) AND status = 'ready_for_classification'
            """.format(",".join(str(id) for id in candidate_ids)))
        )
        await session.commit()
        
        # Get the IDs we actually claimed
        result = await session.execute(
            text("""
                SELECT id FROM source_google_news 
                WHERE id IN ({}) AND status = 'classifying'
            """.format(",".join(str(id) for id in candidate_ids)))
        )
        source_ids = [row[0] for row in result.fetchall()]
    
    logger.info(f"Claimed {len(source_ids)} sources for classification")
    
    if not source_ids:
        return {
            "processed": 0,
            "violent_death": 0,
            "discarded": 0,
            "errors": 0,
        }
    
    # Semaphore to limit concurrency
    semaphore = asyncio.Semaphore(concurrency)
    
    async def classify_with_limit(source_id: int):
        async with semaphore:
            return await classify_source(source_id)
    
    # Run classifications in parallel with concurrency limit
    logger.info(f"Starting parallel classification with concurrency={concurrency}")
    results = await asyncio.gather(
        *[classify_with_limit(sid) for sid in source_ids],
        return_exceptions=True
    )
    
    violent_death_count = 0
    discarded_count = 0
    error_count = 0
    
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Classification failed with exception: {result}")
            error_count += 1
        elif result is True:
            violent_death_count += 1
        else:
            discarded_count += 1
    
    logger.info(
        f"Classification complete: {violent_death_count} violent death, "
        f"{discarded_count} discarded, {error_count} errors"
    )
    
    return {
        "processed": len(source_ids),
        "violent_death": violent_death_count,
        "discarded": discarded_count,
        "errors": error_count,
    }

