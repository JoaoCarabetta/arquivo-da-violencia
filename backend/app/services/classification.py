"""Classification service - classifies headlines to filter violent death news."""

from datetime import datetime
from typing import Literal, Optional

import instructor
from loguru import logger
from pydantic import BaseModel, Field
from sqlmodel import select
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.services.classification_heuristics import apply_classification_heuristics
from app.config import get_pipeline_active_countries, get_settings
from app.database import async_session_maker
from app.models import SourceGoogleNews, SourceStatus


class ClassificationModelCallError(Exception):
    """Raised when the upstream LLM/model call fails (HTTP 402, 401, timeout, etc.)."""


class ViolentDeathClassification(BaseModel):
    """Classification result for whether news is about a violent death."""
    
    is_violent_death: bool = Field(
        ...,
        description="""
        TRUE only if the headline is about one or more NEW violent deaths in South America
        (AR, BO, BR, CL, CO, EC, GY, PY, PE, SR, UY, VE) — homicides, murders, killings,
        police operations with deaths.

        Examples of TRUE:
        - "Homem é morto a tiros em operação policial" (Brazil, PT)
        - "Corpo é encontrado com marcas de violência" (Brazil, PT)
        - "Tiroteio deixa dois mortos na Zona Norte" (Brazil, PT)
        - "Mulher é assassinada pelo ex-marido" (Brazil, PT)
        - "Hombre asesinado en operativo policial en Santiago" (Chile, ES)
        - "Homicidio en Buenos Aires deja dos muertos" (Argentina, ES)
        - "Murder in Georgetown leaves one dead" (Guyana, EN)
        - "Moord in Paramaribo: man doodgeschoten" (Suriname, NL)

        Examples of FALSE:
        - "Polícia prende suspeito de roubo"
        - "Homem sobrevive após ser baleado"
        - "Vítima de facadas chora no julgamento do agressor" (victim alive)
        - "Atirador em massa no Texas recebe pena de morte" (foreign: outside SA)
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
Você é um classificador de manchetes de notícias do Google News. Sua tarefa é:
1. Determinar se a manchete indica NOTÍCIA sobre MORTE(S) VIOLENTA(S) na América do Sul.
2. Determinar se descreve UM ÚNICO INCIDENTE específico (is_single_incident).

Este filtro alimenta um arquivo de violência que cobre toda a América do Sul (Argentina, Bolívia,
Brasil, Chile, Colômbia, Equador, Guiana, Paraguai, Peru, Suriname, Uruguai, Venezuela).
Manchetes sobre mortes violentas FORA da América do Sul NÃO entram (EUA, México, Europa, etc.).

CLASSIFIQUE COMO MORTE VIOLENTA (is_violent_death = true):
- Morte violenta em qualquer país sul-americano: morto(s), assassinado(s), executado(s), baleado(s) MORTO
  (PT: morto, assassinado, baleado; ES: asesinado, muerto, baleado; EN: murdered, killed, shot dead; NL: doodgeschoten, vermoord)
- Corpo, restos mortais ou ossada encontrados com indícios de violência
- Tiroteio/confronto/operação policial que deixa mortos (inclui jargão: "neutralizado",
  "CPF cancelado" no sentido de pessoa morta)
  (ES: operativos policiales, balacera; EN: police shooting, gunfire; NL: schietpartij)
- Feminicídio, latrocínio, homicídio, chacina, execução
  (ES: femicidio, homicidio, asesinato, sicariato; EN: murder, homicide, killing; NL: moord, doodslag)
- Vítima que MORRE: "não resistiu aos ferimentos", "morre após ser baleado"
  (ES: "no resistió", "murió tras", "falleció"; EN: "died after", "succumbed"; NL: "overleed")
- Letalidade implícita: "crivado de balas", "CPF cancelado", "tombou/tombaram",
  "não deixa sobreviventes", "linchado até parar de respirar" — trate como morte violenta
  salvo se a manchete indicar sobrevivência (ferido, hospital, quadro estável)

NÃO CLASSIFIQUE COMO MORTE VIOLENTA (is_violent_death = false):
- Eventos FORA da América do Sul (EUA, México, Europa, Rússia, Ucrânia, África, Ásia, etc.), mesmo com mortes
- Vítima VIVA: sobrevive, ferido(s), hospitalizado, chora, presta depoimento, "vítima de
  X facadas" no julgamento (sobrevivente), tentativa de homicídio sem morte
  (ES: sobrevivió, herido, hospitalizado; EN: survived, injured, hospitalized; NL: gewond, ziekenhuis)
- Tiroteio, operação ou confronto SEM menção a morte ou feridos mortos
- Prisões, mandados, julgamentos, pena de morte como sentença judicial (notícia jurídica)
- Apreensões de armas/drogas, políticas de segurança
- Metáforas ("assassinato da língua", "executa o orçamento")
- Acidentes (trânsito, queda) sem homicídio doloso
- Arsenal apreendido para crimes futuros (crime frustrado, sem morte na notícia)

INCIDENTE ÚNICO (is_single_incident = true):
- Um homicídio ou tiroteio específico em qualquer país sul-americano, em local identificável
- "Tiroteio deixa dois mortos na Zona Norte" (Brasil, PT)
- "Homem é morto a tiros em operação policial" (Brasil, PT)
- "Hombre asesinado en Santiago" (Chile, ES)
- "Homicidio en Bogotá deja tres muertos" (Colômbia, ES)
- "Murder in Georgetown: man shot dead" (Guiana, EN)
- "Moord in Paramaribo: man doodgeschoten" (Suriname, NL)

NÃO É INCIDENTE ÚNICO (is_single_incident = false) — descarte mesmo se mencionar mortes:
- Estatísticas agregadas: balanço anual, CVLI, "X mortes em 2025", "no estado", painéis
- Notícias estrangeiras: terremotos, guerras, desastres fora da América do Sul
- Suicídios (mesmo violentos)
- Crueldade contra animais
- Resumos com múltiplos incidentes não relacionados
- Análises/políticas públicas sobre violência sem um caso específico

Use content_class_hint quando aplicável: incident, aggregate_statistics, foreign,
non_incident, suicide, accident_disaster.

Baseie-se APENAS no texto da manchete. Em dúvida sobre local, procure topônimos estrangeiros
(Texas, EUA, Rússia, Ucrânia, México, Europa) ou contexto claramente fora da América do Sul.
América do Sul é IN; resto do mundo é OUT.
"""

CONTENT_CLASSIFICATION_SYSTEM_PROMPT = """
Você é um classificador de ARTIGOS JORNALÍSTICOS do Google News. A manchete já passou
por um filtro inicial, mas o CORPO do artigo pode revelar que a matéria NÃO descreve um
incidente único de morte violenta na América do Sul.

Sua tarefa:
1. Determinar se o artigo trata de MORTE(S) VIOLENTA(S) na América do Sul (AR, BO, BR, CL, CO, EC, GY, PY, PE, SR, UY, VE).
2. Determinar se descreve UM ÚNICO INCIDENTE específico (is_single_incident).

Use a manchete apenas como contexto. Baseie a decisão principalmente no corpo do artigo.

CLASSIFIQUE COMO MORTE VIOLENTA (is_violent_death = true):
- Morte violenta em qualquer país sul-americano descrita no corpo: homicídio, tiroteio, operação policial com morte
  (ES: homicidio, asesinato, balacera, operativo policial, sicariato)
  (EN: murder, homicide, killing, shooting)
  (NL: moord, doodslag, schietpartij)
- Corpo/restos encontrados com indícios de violência
- Feminicídio, latrocínio, chacina, execução
  (ES: femicidio, homicidio, asesinato; EN: murder, killing; NL: moord)
- CASO ENTERRADO em matéria estatística: se uma matéria de balanço/estatísticas descreve
  em detalhe UM caso concreto cujo ÓBITO É RECENTE (ocorreu há horas/dias, ex.: "na noite
  de ontem"), classifique is_violent_death = true e is_single_incident = true — o caso
  concreto e recente prevalece sobre o enquadramento estatístico da matéria.

REGRA DE PRECEDÊNCIA: o que importa é haver um ÓBITO NOVO/RECENTE noticiado. Matéria cuja
pauta é julgamento/condenação de crime antigo = false (o óbito não é novo), mesmo com
detalhes do caso. Matéria estatística que cita uma morte ocorrida ontem = true.

NÃO CLASSIFIQUE COMO MORTE VIOLENTA (is_violent_death = false):
- Eventos FORA da América do Sul (desastres, guerras, crimes em EUA, México, Europa, África, Ásia, etc.)
  — atenção a cidades homônimas: o corpo pode revelar que "Belém" é no Texas, etc.
- VÍTIMA SOBREVIVEU: se o corpo informa que a vítima foi socorrida, está internada,
  estável ou sobreviveu, NÃO há morte violenta — mesmo em "tentativa de feminicídio"
  ou ataque brutal. Sem óbito, is_violent_death = false.
  (ES: sobrevivió, hospitalizado, estable; EN: survived, injured, hospitalized; NL: gewond, overleefd)
- Matéria sobre PROCESSO JUDICIAL: julgamento, júri, condenação, absolvição, prisão ou
  investigação de crime que já ocorreu no passado. A pauta é o processo, não um novo
  óbito — mesmo que o corpo descreva os homicídios julgados, is_violent_death = false.
- Obras culturais: séries, filmes, documentários, livros ou peças que retratam crimes
  (mesmo crimes reais/históricos) — é pauta cultural, não um novo incidente
- Acidentes (trânsito, afogamento, queda) sem homicídio doloso
- Apreensões, políticas, análises sem caso específico

INCIDENTE ÚNICO (is_single_incident = true):
- Um homicídio ou tiroteio específico em qualquer país sul-americano, em local identificável
- Um evento claramente delimitado ("tiroteio deixa dois mortos na Zona Norte", Brasil, PT)
  (ES: "balacera deja dos muertos en Santiago", Chile)
  (ES: "homicidio en Bogotá deja tres muertos", Colômbia)
  (EN: "murder in Georgetown leaves one dead", Guiana)
  (NL: "moord in Paramaribo: man doodgeschoten", Suriname)
- ATENÇÃO: mesmo em matéria com tom estatístico, se o corpo DESCREVE um incidente
  específico (vítima, local e circunstâncias identificáveis), classifique
  is_single_incident = true — o caso concreto prevalece sobre o enquadramento da matéria.

NÃO É INCIDENTE ÚNICO (is_single_incident = false) — descarte:
- Estatísticas agregadas SEM caso concreto descrito: balanço anual, CVLI, totais
  estaduais/nacionais, "X mortes em 2025"
- Notícias estrangeiras fora da América do Sul mesmo que a manchete pareça local
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

    if not settings.openrouter_api_key:
        raise ValueError("OPENROUTER_API_KEY not configured")

    model_name = model or settings.selection_model
    # JSON mode: OpenRouter tool-calling with Gemini intermittently hangs the
    # response stream and breaks on parallel function calls.
    return instructor.from_provider(
        f"openrouter/{model_name}",
        api_key=settings.openrouter_api_key,
        mode=instructor.Mode.JSON,
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
        timeout=60,
    )

    return apply_classification_heuristics(headline, result)


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
    client = get_classification_client(model=model or get_settings().content_gate_model)
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
        timeout=90,
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
                        is_violent_death = :is_violent_death,
                        classification_reasoning = 'No headline available',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                """),
                {"id": source_id, "is_violent_death": False},
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
        raise ClassificationModelCallError(
            f"Model call failed for source {source_id}: {e}"
        ) from e

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
                "is_violent_death": classification.is_violent_death,
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


async def _reset_unfinished_classifying(source_ids: list[int]) -> int:
    """Return claimed sources still in classifying back to the queue."""
    if not source_ids:
        return 0
    from sqlalchemy import text

    id_list = ",".join(str(source_id) for source_id in source_ids)
    async with async_session_maker() as session:
        result = await session.execute(
            text(f"""
                UPDATE source_google_news
                SET status = 'ready_for_classification', updated_at = CURRENT_TIMESTAMP
                WHERE id IN ({id_list}) AND status = 'classifying'
            """)
        )
        await session.commit()
        return result.rowcount or 0


def _sql_country_in_list(countries: list[str]) -> str:
    """Quote ISO codes for a SQL IN clause; reject anything that is not AA."""
    safe = []
    for code in countries:
        normalized = str(code).strip().upper()
        if len(normalized) == 2 and normalized.isalpha():
            safe.append(f"'{normalized}'")
    if not safe:
        return "'__none__'"
    return ", ".join(safe)


async def classify_pending_sources(limit: int = 50, concurrency: int = 10) -> dict:
    """
    Batch classify sources that are ready for classification (in parallel).

    Only rows whose ``country`` is in ``pipeline_active_countries`` are
    claimed. ``country IS NULL`` is treated as ``BR`` (legacy Brazil rows).
    Inactive-country rows stay ``ready_for_classification`` — no discard,
    no model call.

    Args:
        limit: Maximum number of sources to process
        concurrency: Maximum number of parallel classifications

    Returns:
        Dict with classification statistics
    """
    import asyncio
    from sqlalchemy import text

    active_countries = get_pipeline_active_countries()
    country_in = _sql_country_in_list(active_countries)
    logger.info(
        f"Starting classification; active countries={active_countries}"
    )

    # Use raw SQL to avoid SQLAlchemy enum caching issues
    async with async_session_maker() as session:
        result = await session.execute(
            text(f"""
                SELECT id FROM source_google_news
                WHERE status = 'ready_for_classification'
                AND headline IS NOT NULL
                AND COALESCE(country, 'BR') IN ({country_in})
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
                "model_call_errors": 0,
                "other_errors": 0,
            }

        # Atomically claim these sources by updating status to prevent race conditions.
        # Country filter is repeated so a row from an inactive country cannot be
        # claimed even if it slipped into candidate_ids.
        await session.execute(
            text(f"""
                UPDATE source_google_news
                SET status = 'classifying', updated_at = CURRENT_TIMESTAMP
                WHERE id IN ({",".join(str(id) for id in candidate_ids)})
                AND status = 'ready_for_classification'
                AND COALESCE(country, 'BR') IN ({country_in})
            """)
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
            "model_call_errors": 0,
            "other_errors": 0,
        }
    
    # Semaphore to limit concurrency
    semaphore = asyncio.Semaphore(concurrency)
    
    async def classify_with_limit(source_id: int):
        async with semaphore:
            return await classify_source(source_id)
    
    # Run classifications in parallel with concurrency limit
    logger.info(f"Starting parallel classification with concurrency={concurrency}")
    try:
        results = await asyncio.gather(
            *[classify_with_limit(sid) for sid in source_ids],
            return_exceptions=True
        )
    finally:
        reset_count = await _reset_unfinished_classifying(source_ids)
        if reset_count:
            logger.warning(
                f"Reset {reset_count} source(s) still in classifying back to ready_for_classification"
            )
    
    violent_death_count = 0
    discarded_count = 0
    model_call_error_count = 0
    other_error_count = 0

    for result in results:
        if isinstance(result, ClassificationModelCallError):
            logger.error(f"Classification model call failed: {result}")
            model_call_error_count += 1
        elif isinstance(result, Exception):
            logger.error(f"Classification failed with exception: {result}")
            other_error_count += 1
        elif result is True:
            violent_death_count += 1
        else:
            discarded_count += 1

    error_count = model_call_error_count + other_error_count

    logger.info(
        f"Classification complete: {violent_death_count} violent death, "
        f"{discarded_count} discarded, {error_count} errors "
        f"(model_call={model_call_error_count}, other={other_error_count})"
    )

    return {
        "processed": len(source_ids),
        "violent_death": violent_death_count,
        "discarded": discarded_count,
        "errors": error_count,
        "model_call_errors": model_call_error_count,
        "other_errors": other_error_count,
    }

