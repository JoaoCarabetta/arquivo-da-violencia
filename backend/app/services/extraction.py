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
from app.services import diagnostics
from app.services.extraction_derived import derive_security_force_involved
from app.services.extraction_heuristics import apply_extraction_heuristics
from app.taxonomy import format_legacy_homicide_type


def content_class_failure_reason(content_class: str) -> str:
    """Map extraction content_class to diagnostics failure reason."""
    if content_class == "aggregate_statistics":
        return diagnostics.AGGREGATE_CONTENT
    if content_class == "foreign":
        return diagnostics.FOREIGN_CONTENT
    return diagnostics.NON_INCIDENT_CONTENT


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
3. Dia da semana COM número entre parênteses: "domingo (10)", "sexta-feira (12)" —
   PRIORIZE o número do dia do mês sobre o dia da semana quando houver conflito
   (ex.: publicação em 11/03/2025 + "domingo (10)" → 2025-03-10, não o domingo anterior).

QUANDO NÃO PODE INFERIR (has_explicit_date = FALSE):
1. Termos vagos sem referência: "recentemente", "há alguns dias", "no início da semana"
2. Não há data de publicação fornecida E texto usa termos relativos
3. Ambiguidade que não pode ser resolvida
4. O texto NÃO menciona quando o crime ocorreu: a data de publicação sozinha NÃO é a
   data do evento — ela serve apenas para resolver expressões relativas do texto.
   Se o artigo não diz QUANDO o crime aconteceu, date = null MESMO que pareça recente.
5. Apenas mês/ano sem dia ("em setembro de 2024") → date = null

ATENÇÃO - DATA DO CRIME vs DATA DA DESCOBERTA:
O campo date refere-se à data em que o CRIME ocorreu. Use date = null (has_explicit_date
= FALSE) SOMENTE quando o texto indica que a morte ocorreu MUITO ANTES da descoberta:
corpo em decomposição, ossada, "a morte não foi recente". Nesses casos a data do crime
é desconhecida mesmo que a data da descoberta seja conhecida.
Fora desses casos, a data em que a vítima foi morta/encontrada informada no texto É a
data do evento — use-a normalmente, inclusive quando o corpo foi encontrado horas ou
até um dia após o crime (ex.: "encontrada morta na noite do dia 18" → 18).

O campo date_verification funciona como um VERIFICADOR:
1. has_explicit_date = TRUE se você consegue determinar a data completa (dia/mês/ano)
2. date_source = "explicit" se está no texto, "inferred_from_publication" se calculada
3. verification_reasoning deve explicar como você chegou à data

Se has_explicit_date = FALSE, o campo date DEVE ser null (nunca ano ou data parcial).

IMPORTANTE: 
- Use a data de publicação para resolver datas relativas
- Documente no verification_reasoning como você resolveu a data
- É MELHOR deixar date como null do que inventar uma data incorreta

SOBRE LOCALIZAÇÃO (location_info.state):
- Preencha o estado (UF) quando estiver explícito no texto OU quando a cidade for
  inequívoca: capitais e cidades notórias (Recife → PE, Manaus → AM, Belém → PA,
  Campina Grande → PB, Londrina → PR), ou quando o contexto identifica a região
  ("Grande Vitória" → ES, "capital de Rondônia" → Porto Velho/RO, "Baixada Fluminense" → RJ).
- location_info.city: se o texto identifica a cidade indiretamente ("capital de
  Rondônia", "Grande Vitória"), preencha com o nome da cidade correspondente.
- Se o nome da cidade é ambíguo entre estados e o texto não desambigua
  (ex.: apenas "Campo Grande", que existe em MS e como bairro no RJ), deixe state = null.

SOBRE event_family e event_subtype — CLASSIFICAÇÃO EM DOIS PASSOS:

Passo 1 — event_family (macro):
- "homicidio": houve óbito por morte violenta intencional (arquivo público)
- "tentativa": não houve óbito (tentativa de homicídio, feminicídio ou latrocínio)
- "acidente_fatal": morte culposa ou acidente sem dolo homicida
- "nao_classificado": não foi possível classificar

Passo 2 — event_subtype (dentro da família):

Se event_family = "homicidio":
- "simples": homicídio sem qualificadora explícita (padrão; na dúvida use simples)
- "qualificado": qualificadora explícita — vítima amarrada/rendida, chacina (≥3 mortos
  no mesmo ataque), "múltiplos disparos à queima-roupa", "dezenas de tiros",
  execução por disparos (headline "executado a tiros" + relato de tiros), tortura,
  emboscada. Briga espontânea ou mera palavra "executado" sem tiros NÃO basta.
- "feminicidio": violência de gênero ou doméstica contra mulher
- "latrocinio": morte durante roubo/assalto
- "infanticidio": morte de criança pelo contexto do texto
- "intervencao_policial": morte em operação policial quando o texto enquadra a morte
  como neutralização em operação (ex.: "foi neutralizado durante operação da PM").
  NÃO use para notícias longas de patrulhamento/abordagem onde criminosos atiram
  primeiro e suspeitos morreram em "confronto" ou "troca de tiros" — nesses casos
  use "simples" (homicídio comum sob investigação do DHPP/DH).
- "morte_transito_doloso": atropelamento intencional ou perseguição fatal com veículo

Se event_family = "tentativa":
- "simples", "feminicidio" ou "latrocinio" conforme o caso

Se event_family = "acidente_fatal":
- "culposo" ou "transito_culposo"

Se event_family = "nao_classificado":
- "outro"

REGRAS:
- Sem óbito → event_family = "tentativa", nunca "homicidio"
- Morte culposa/acidente sem dolo → event_family = "acidente_fatal"
- Feminicídio, latrocínio e qualificado são SUBTIPOS de homicidio, não famílias separadas
- event_family = "homicidio" exige content_class = "incident"

SOBRE content_class — OBRIGATÓRIO EM TODA EXTRAÇÃO:
Defina content_class em todo JSON de saída. Valores permitidos:
- "incident": um evento único de morte violenta no Brasil descrito na notícia (padrão
  quando a matéria trata de um caso concreto).
- "aggregate_statistics": balanço anual, CVLI, totais estaduais/nacionais, "X mortes em
  2025", painéis e estudos sem caso concreto como foco principal.
- "non_incident": suicídio, crueldade contra animais, coluna de opinião, matéria
  jurídica sobre processo antigo sem óbito novo, ou conteúdo fora do escopo de homicídio.
- "accident_disaster": acidente de trânsito culposo, queda, afogamento, desastre natural
  sem homicídio doloso. OBRIGATÓRIO quando event_family = "acidente_fatal".
- "foreign": evento ocorre fora do Brasil ou a matéria trata primariamente de mortes no
  exterior (EUA, Europa, etc.).

SOBRE number_of_victims — NUNCA USE TOTAIS AGREGADOS:
- Conte APENAS as vítimas FATAIS do incidente (mortos), NUNCA inclua feridos.
  Ex.: "três mortos e um ferido" → number_of_victims = 3, não 4.
- Conte APENAS as vítimas do incidente específico descrito (máximo 20).
- NUNCA use totais anuais, CVLI, "4.241 mortes em 2025", balanço estadual ou estatísticas
  de painel como number_of_victims — mesmo que sejam o tema da matéria.
- Se a matéria é estatística agregada sem incidente único, use content_class =
  "aggregate_statistics" e number_of_victims = 1 apenas se houver um caso concreto
  embutido; caso contrário a extração será descartada downstream.

SOBRE homicide_dynamic.method — OBRIGATÓRIO PREENCHER:
- Use um valor do enum quando o texto indicar o meio (tiros → "Arma de fogo",
  facadas → "Arma branca", traumatismo craniano → "Objeto contundente").
- "Não especificado" quando a matéria diz que o método/causa não foi determinado
  ou não divulgado, ou quando há pouquíssima informação sobre a dinâmica.
- Não deixe null se o texto menciona tiros, disparos, facadas ou equivalentes.
- Prefira "Não especificado" a "Outro" quando a perícia não identificou o objeto.

SOBRE TÍTULOS:
- Se não há data completa verificada, use "DATA NÃO INFORMADA" no título
- Exemplo: "FEMINICÍDIO - RESIDÊNCIA SANTA CRUZ - DATA NÃO INFORMADA"

SOBRE NOMES DE VÍTIMAS (identifiable_victims) — OBRIGATÓRIO QUANDO O TEXTO NOMEIA:
- Se o texto traz nome próprio, apelido ou nome social da vítima (ex.: "Wal", "Gesse Alves de
  Sena", "Gustavo Rafael Campos Siqueira"), PREENCHA identifiable_victims[].name com esse
  nome. NÃO deixe name = null só porque idade/gênero já bastam para o resumo.
- Prefira o nome mais completo disponível no texto; se só houver primeiro nome ou apelido,
  use-o mesmo assim (melhor nome parcial do que anônimo).
- Só omita name quando o texto realmente não identifica a pessoa (ex.: "um homem de 31 anos"
  sem nome). Nesses casos age/gender podem ficar preenchidos e name = null.
- Nomes parciais ou sociais ("Wal (identificada apenas como)") ainda contam como nome —
  registre-os; isso evita UniqueEvents anônimos que não deduplicam com fontes nomeadas.

SOBRE AGENTES DE SEGURANÇA (vítimas e autores identificáveis):
- is_security_force=true para PM, PC, PF, PRF, guarda municipal, policial penal, etc.
- security_agent_type: somente se is_security_force=true (PM, PC, PF, PRF, penal, outro).
- security_agent_on_duty: somente se is_security_force=true — true=em serviço/patrulha;
  false=folga/fora de expediente/à paisana; null= texto não informa.

SOBRE VÍTIMA POLÍTICA (identifiable_victims[].political_role):
- Preencher political_role SOMENTE quando o texto identifica a vítima como política ou candidata.
- is_politician_or_candidate=true; status=elected | candidate | former_elected (ex-vereador → former_elected).
- office: cargo sem prefixo "ex-" (ex.: "vereador" mesmo para ex-vereador).
- party: sigla/nome conforme texto; null se não mencionado — NÃO inferir partido.

SOBRE GRUPOS CRIMINOSOS (homicide_dynamic.criminal_group_context):
- Use APENAS informação explícita sobre ESTE homicídio. NÃO inferir de "área dominada pelo tráfico"
  ou antecedentes sem ligação declarada ao caso.
- connected=true quando texto liga o crime a facção/grupo/milícia/organização criminosa.
- groups: nomes verbatim (PCC, Comando Vermelho, milícia, etc.).
- activity: enum — internal-discipline, internal-dispute, population-discipline,
  informant-elimination, debt-enforcement, territorial-dispute, economic-dispute,
  retaliatory, police-ambush, protest (inclui violência anti-estado/reação a política),
  collateral, unspecified (conectado mas mecanismo incerto).
- Se múltiplos se aplicam: territorial-dispute > economic-dispute > retaliatory > unspecified.
- group_attacked / rival_actor / target_force / policy_trigger: somente quando explícitos; null se incerto.
- activity_description: detalhe extra grounded no texto quando enum não basta.

SOBRE OPERAÇÃO POLICIAL (homicide_dynamic.police_operation_context):
- Distinto de event_subtype=intervencao_policial — registre os fatos da operação aqui.
- connected=true quando morte ocorreu durante operação policial oficial descrita.
- responsible_force, operation_name, targeted_armed_groups conforme texto.

SOBRE POLICIAL AUTOR FORA DE SERVIÇO (homicide_dynamic):
- off_duty_police_perpetrator=true quando policial é autor/perpetrador fora de operação oficial.
- off_duty_police_context: genuine_reaction | moonlighting | criminal_organization conforme texto.
"""


def get_instructor_client():
    """Get instructor client via OpenRouter."""
    settings = get_settings()
    api_key = settings.openrouter_api_key
    
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY not configured")
    
    # JSON mode: OpenRouter tool-calling with Gemini intermittently hangs the
    # response stream and breaks on parallel function calls.
    return instructor.from_provider(
        f"openrouter/{settings.extraction_model}",
        api_key=api_key,
        mode=instructor.Mode.JSON,
    )


def extract_event_from_content(
    content: str,
    metadata: dict | None = None,
    model_id: str | None = None,
    *,
    system_prompt: str | None = None,
) -> ViolentDeathEvent:
    """
    Extract structured event data from news content using LLM.

    Args:
        content: News article text
        metadata: Optional source metadata (headline, published_at, publisher, url)
        model_id: Optional model ID override
        system_prompt: Optional override for the extraction system prompt

    Returns:
        ViolentDeathEvent with extracted data
    """
    settings = get_settings()
    api_key = settings.openrouter_api_key

    if not api_key:
        raise ValueError("OPENROUTER_API_KEY not configured")

    model = model_id or settings.extraction_model
    prompt = system_prompt or EXTRACTION_SYSTEM_PROMPT

    client = instructor.from_provider(
        f"openrouter/{model}",
        api_key=api_key,
        mode=instructor.Mode.JSON,
    )

    # Build user message with metadata context
    user_message = _build_extraction_prompt(content, metadata)

    event = client.create(
        response_model=ViolentDeathEvent,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_message},
        ],
        max_retries=3,
        max_tokens=settings.extraction_max_output_tokens,
        timeout=180,
    )

    return apply_extraction_heuristics(event, content, metadata)


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
    import asyncio
    import time
    from sqlalchemy import text

    settings = get_settings()
    model_name = settings.extraction_model

    # Step 1: read the source content/metadata in a short-lived session, then
    # release the connection before the (slow, blocking) LLM extraction call.
    async with async_session_maker() as session:
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

    attempt_number = await diagnostics.count_attempts(source_id, diagnostics.STAGE_EXTRACTION) + 1
    original_length = len(content)

    # Truncate over-long content to avoid token/context-window failures. Most
    # articles are far below this; long pages are usually padded with unrelated
    # boilerplate that hurts extraction anyway.
    if original_length > settings.extraction_max_chars:
        logger.info(
            f"Truncating source {source_id} content from {original_length} to "
            f"{settings.extraction_max_chars} chars"
        )
        content = content[: settings.extraction_max_chars]

    async def _mark_failed(reason: str, detail: str | None, duration_ms: int):
        async with async_session_maker() as session:
            await session.execute(
                text("""
                    UPDATE source_google_news 
                    SET status = 'failed_in_extraction', updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                """),
                {"id": source_id}
            )
            await session.commit()
        await diagnostics.record_attempt(
            stage=diagnostics.STAGE_EXTRACTION,
            outcome=diagnostics.OUTCOME_FAILURE,
            source_google_news_id=source_id,
            failure_reason=reason,
            failure_detail=detail,
            model=model_name,
            content_length=original_length,
            duration_ms=duration_ms,
            attempt_number=attempt_number,
        )

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

    # Step 2: run the blocking LLM extraction off the event loop and WITHOUT
    # holding a DB connection.
    started = time.monotonic()
    try:
        event = await asyncio.to_thread(extract_event_from_content, content, metadata)
    except Exception as e:
        duration_ms = int((time.monotonic() - started) * 1000)
        reason = diagnostics.classify_extraction_exception(e)
        logger.error(f"Extraction failed for source {source_id} ({reason}): {e}")

        if reason == diagnostics.VALIDATION_ERROR:
            async with async_session_maker() as session:
                await session.execute(
                    text("""
                        UPDATE source_google_news
                        SET status = 'discarded',
                            classification_reasoning = :reasoning,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :id
                    """),
                    {
                        "id": source_id,
                        "reasoning": f"Extraction validation failed: {str(e)[:500]}",
                    },
                )
                await session.commit()
            await diagnostics.record_attempt(
                stage=diagnostics.STAGE_EXTRACTION,
                outcome=diagnostics.OUTCOME_DISCARDED,
                source_google_news_id=source_id,
                failure_reason=reason,
                failure_detail=str(e),
                model=model_name,
                content_length=original_length,
                duration_ms=duration_ms,
                attempt_number=attempt_number,
            )
            return None

        await _mark_failed(reason, str(e), duration_ms)
        return None

    if event.content_class != "incident":
        duration_ms = int((time.monotonic() - started) * 1000)
        failure_reason = content_class_failure_reason(event.content_class)
        reasoning = f"Extraction content_class={event.content_class}"
        logger.info(
            f"Discarding source {source_id}: {reasoning} ({failure_reason})"
        )
        async with async_session_maker() as session:
            await session.execute(
                text("""
                    UPDATE source_google_news
                    SET status = 'discarded',
                        classification_reasoning = :reasoning,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                """),
                {"id": source_id, "reasoning": reasoning},
            )
            await session.commit()
        await diagnostics.record_attempt(
            stage=diagnostics.STAGE_EXTRACTION,
            outcome=diagnostics.OUTCOME_DISCARDED,
            source_google_news_id=source_id,
            failure_reason=failure_reason,
            failure_detail=reasoning,
            model=model_name,
            content_length=original_length,
            duration_ms=duration_ms,
            attempt_number=attempt_number,
        )
        return None

    security_force_involved = derive_security_force_involved(event)

    event_data = event.model_dump()

    # Parse date string to datetime if present
    event_date = None
    if event.date_time.date:
        try:
            from datetime import datetime as dt
            event_date = dt.strptime(event.date_time.date, "%Y-%m-%d")
        except ValueError:
            logger.warning(f"Could not parse date: {event.date_time.date}")

    # Step 3: persist the RawEvent in a fresh short-lived session.
    async with async_session_maker() as session:
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
            security_force_involved=security_force_involved,
            event_family=event.event_family,
            event_subtype=event.event_subtype,
            homicide_type=format_legacy_homicide_type(event.event_family, event.event_subtype),
            method_of_death=event.homicide_dynamic.method,
            title=event.homicide_dynamic.title,
            chronological_description=event.homicide_dynamic.chronological_description,
            content_class=str(event.content_class),
            # Full structured data as JSON
            extraction_data=event_data,
            extraction_model=get_settings().extraction_model,
            extraction_success=True,
        )

        session.add(raw_event)

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

    await diagnostics.record_attempt(
        stage=diagnostics.STAGE_EXTRACTION,
        outcome=diagnostics.OUTCOME_SUCCESS,
        source_google_news_id=source_id,
        raw_event_id=raw_event.id,
        model=model_name,
        content_length=original_length,
        duration_ms=int((time.monotonic() - started) * 1000),
        attempt_number=attempt_number,
    )

    logger.info(f"Created RawEvent {raw_event.id} for source {source_id}")
    return raw_event


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

