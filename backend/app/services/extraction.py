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
from app.services.extraction_derived import (
    derive_security_force_involved,
    derive_security_force_victim,
)
from app.services.extraction_heuristics import apply_extraction_heuristics
from app.services.extraction_schemas import ViolentDeathEvent
from app.taxonomy import format_legacy_homicide_type


def content_class_failure_reason(content_class: str) -> str:
    """Map extraction content_class to diagnostics failure reason."""
    if content_class == "aggregate_statistics":
        return diagnostics.AGGREGATE_CONTENT
    if content_class == "foreign":
        return diagnostics.FOREIGN_CONTENT
    return diagnostics.NON_INCIDENT_CONTENT


# System prompt for extraction (Portuguese - Brazil)
EXTRACTION_SYSTEM_PROMPT_PT = """
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
- location_info.country: preencha "BR" para Brasil, ou outro código ISO se o evento
  ocorreu em outro país.

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
- "incident": um evento único de morte violenta descrito na notícia (padrão
  quando a matéria trata de um caso concreto).
- "aggregate_statistics": balanço anual, CVLI, totais estaduais/nacionais, "X mortes em
  2025", painéis e estudos sem caso concreto como foco principal.
- "non_incident": suicídio, crueldade contra animais, coluna de opinião, matéria
  jurídica sobre processo antigo sem óbito novo, ou conteúdo fora do escopo de homicídio.
- "accident_disaster": acidente de trânsito culposo, queda, afogamento, desastre natural
  sem homicídio doloso. OBRIGATÓRIO quando event_family = "acidente_fatal".
- "foreign": evento ocorre fora do Brasil/Chile ou a matéria trata primariamente de mortes
  no exterior (EUA, Europa, etc.). Use quando o crime não ocorreu no país da fonte.

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
- Vítima policial: NÃO use subtipo especial — preencha is_security_force + security_agent_*
  na vítima; event_subtype segue a dinâmica do crime (simples, latrocinio, qualificado, etc.).
- intervencao_policial = policiais matam alguém; vítima policial = security_agent_* na vítima.
- Grupos não identificados: use is_security_force em unidentified_groups; type/on_duty só
  em identifiable_victims ou identifiable_perpetrators quando houver indivíduo descrito.

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

# System prompt for extraction (Spanish - Chile)
EXTRACTION_SYSTEM_PROMPT_ES = """
Eres un asistente especializado en extraer información de noticias sobre muertes violentas
y convertirlas en descripciones técnicas siguiendo estándares profesionales de la
investigación policial en Chile.

PRINCIPIOS FUNDAMENTALES:
1. Usa SOLAMENTE información explícitamente presente en el texto
2. NUNCA inventes, calcules o inferir información
3. Para campos opcionales, deja null si la información no está disponible
4. Mantén objetividad y neutralidad absoluta
5. Usa terminología legal formal y precisa

REGLA CRÍTICA SOBRE FECHAS - LEE CON ATENCIÓN:

Recibirás metadatos de la noticia incluyendo la FECHA DE PUBLICACIÓN. Usa esta información
para resolver fechas relativas mencionadas en el texto.

RESOLUCIÓN DE FECHAS RELATIVAS:
Si la noticia fue publicada el 21/12/2025 y el texto menciona:
- "ayer" → 20/12/2025
- "anteayer" → 19/12/2025
- "el viernes" → calcula cuál viernes más reciente antes de la publicación
- "esta semana" → semana de la publicación
- "hace tres días" → 18/12/2025

CUÁNDO PUEDES INFERIR LA FECHA (has_explicit_date = TRUE):
1. Fecha completa explícita: "15 de diciembre de 2025", "20/11/2025"
2. Fecha relativa CON referencia de publicación: "ayer" cuando conoces la fecha de publicación
3. Día de la semana CON número entre paréntesis: "domingo (10)", "viernes (12)" —
   PRIORIZA el número del día del mes sobre el día de la semana cuando haya conflicto
   (ej.: publicación el 11/03/2025 + "domingo (10)" → 2025-03-10, no el domingo anterior).

CUÁNDO NO PUEDES INFERIR (has_explicit_date = FALSE):
1. Términos vagos sin referencia: "recientemente", "hace algunos días", "a principios de semana"
2. No hay fecha de publicación Y el texto usa términos relativos
3. Ambigüedad que no puede resolverse
4. El texto NO menciona cuándo ocurrió el crimen: la fecha de publicación sola NO es la
   fecha del evento — sirve solo para resolver expresiones relativas del texto.
   Si el artículo no dice CUÁNDO sucedió el crimen, date = null AUNQUE parezca reciente.
5. Solo mes/año sin día ("en septiembre de 2024") → date = null

ATENCIÓN - FECHA DEL CRIMEN vs FECHA DEL DESCUBRIMIENTO:
El campo date se refiere a la fecha en que el CRIMEN ocurrió. Usa date = null (has_explicit_date
= FALSE) SOLAMENTE cuando el texto indica que la muerte ocurrió MUCHO ANTES del descubrimiento:
cuerpo en descomposición, restos óseos, "la muerte no fue reciente". En esos casos la fecha del crimen
es desconocida aunque la fecha del descubrimiento sea conocida.
Fuera de esos casos, la fecha en que la víctima fue asesinada/encontrada informada en el texto ES la
fecha del evento — úsala normalmente, incluso cuando el cuerpo fue encontrado horas o
hasta un día después del crimen (ej.: "encontrada muerta la noche del 18" → 18).

El campo date_verification funciona como un VERIFICADOR:
1. has_explicit_date = TRUE si puedes determinar la fecha completa (día/mes/año)
2. date_source = "explicit" si está en el texto, "inferred_from_publication" si fue calculada
3. verification_reasoning debe explicar cómo llegaste a la fecha

Si has_explicit_date = FALSE, el campo date DEBE ser null (nunca año o fecha parcial).

IMPORTANTE:
- Usa la fecha de publicación para resolver fechas relativas
- Documenta en verification_reasoning cómo resolviste la fecha
- Es MEJOR dejar date como null que inventar una fecha incorrecta

SOBRE LOCALIZACIÓN (location_info.state):
- Llena la región cuando esté explícita en el texto O cuando la ciudad sea
  inequívoca: capitales y ciudades conocidas (Valparaíso, Concepción, Antofagasta),
  o cuando el contexto identifica la región ("Región Metropolitana" → Metropolitana,
  "capital de Chile" → Santiago/Metropolitana).
- location_info.city: si el texto identifica la ciudad indirectamente ("capital de Chile",
  "Gran Santiago"), llena con el nombre de la ciudad correspondiente.
- location_info.state: usa el nombre completo de la región chilena (Metropolitana, Valparaíso,
  Biobío, etc.) NO los códigos romanos.
- location_info.country: llena "CL" para Chile, o otro código ISO si el evento
  ocurrió en otro país.

SOBRE event_family y event_subtype — CLASIFICACIÓN EN DOS PASOS:

Paso 1 — event_family (macro):
- "homicidio": hubo muerte por violencia intencional (archivo público)
- "tentativa": no hubo muerte (tentativa de homicidio, femicidio o robo con homicidio)
- "acidente_fatal": muerte culposa o accidente sin dolo homicida
- "nao_classificado": no fue posible clasificar

Paso 2 — event_subtype (dentro de la familia):

Si event_family = "homicidio":
- "simples": homicidio sin calificante explícita (por defecto; si hay duda usa simples)
- "qualificado": calificante explícita — víctima amarrada/sometida, masacre (≥3 muertos
  en el mismo ataque), "múltiples disparos a quemarropa", "decenas de tiros",
  ejecución con disparos (titular "ejecutado a tiros" + relato de tiros), tortura,
  emboscada. Riña espontánea o mera palabra "ejecutado" sin tiros NO basta.
- "feminicidio": violencia de género o doméstica contra mujer (en Chile también llamado "femicidio")
- "latrocinio": muerte durante robo/asalto (en Chile: "robo con homicidio")
- "infanticidio": muerte de niño/a por el contexto del texto
- "intervencao_policial": muerte en operación policial cuando el texto enmarca la muerte
  como neutralización en operación (ej.: "fue neutralizado durante operativo de Carabineros").
  NO uses para noticias largas de patrullaje donde criminales disparan primero y sospechosos
  murieron en "enfrentamiento" o "intercambio de disparos" — en esos casos usa "simples"
  (homicidio común bajo investigación de la PDI/Homicidios).
- "morte_transito_doloso": atropello intencional o persecución fatal con vehículo

Si event_family = "tentativa":
- "simples", "feminicidio" o "latrocinio" según el caso

Si event_family = "acidente_fatal":
- "culposo" o "transito_culposo"

Si event_family = "nao_classificado":
- "outro"

REGLAS:
- Sin muerte → event_family = "tentativa", nunca "homicidio"
- Muerte culposa/accidente sin dolo → event_family = "acidente_fatal"
- Femicidio, robo con homicidio y calificado son SUBTIPOS de homicidio, no familias separadas
- event_family = "homicidio" exige content_class = "incident"

SOBRE content_class — OBLIGATORIO EN TODA EXTRACCIÓN:
Define content_class en todo JSON de salida. Valores permitidos:
- "incident": un evento único de muerte violenta descrito en la noticia (por defecto
  cuando la noticia trata de un caso concreto).
- "aggregate_statistics": balance anual, totales regionales/nacionales, "X muertes en
  2025", paneles y estudios sin caso concreto como foco principal.
- "non_incident": suicidio, crueldad animal, columna de opinión, noticia legal
  sobre proceso antiguo sin muerte nueva, o contenido fuera del alcance de homicidio.
- "accident_disaster": accidente de tránsito culposo, caída, ahogamiento, desastre natural
  sin homicidio doloso. OBLIGATORIO cuando event_family = "acidente_fatal".
- "foreign": evento ocurre fuera de Chile/Brasil o la noticia trata primariamente de muertes
  en el extranjero (EEUU, Europa, etc.). Usa cuando el crimen no ocurrió en el país de la fuente.

SOBRE number_of_victims — NUNCA USES TOTALES AGREGADOS:
- Cuenta SOLAMENTE las víctimas FATALES del incidente (muertos), NUNCA incluyas heridos.
  Ej.: "tres muertos y un herido" → number_of_victims = 3, no 4.
- Cuenta SOLAMENTE las víctimas del incidente específico descrito (máximo 20).
- NUNCA uses totales anuales, "4.241 muertes en 2025", balance regional o estadísticas
  de panel como number_of_victims — aunque sean el tema de la noticia.
- Si la noticia es estadística agregada sin incidente único, usa content_class =
  "aggregate_statistics" y number_of_victims = 1 solo si hay un caso concreto
  incluido; de lo contrario la extracción será descartada downstream.

SOBRE homicide_dynamic.method — OBLIGATORIO COMPLETAR:
- Usa un valor del enum cuando el texto indique el medio (tiros → "Arma de fogo",
  puñaladas → "Arma branca", traumatismo craneal → "Objeto contundente").
- "Não especificado" cuando la noticia dice que el método/causa no fue determinado
  o no fue divulgado, o cuando hay muy poca información sobre la dinámica.
- No dejes null si el texto menciona disparos, balazos, puñaladas o equivalentes.
- Prefiere "Não especificado" a "Outro" cuando la pericia no identificó el objeto.

SOBRE TÍTULOS:
- Si no hay fecha completa verificada, usa "DATA NÃO INFORMADA" en el título
- Ejemplo: "FEMINICÍDIO - RESIDÊNCIA SANTA CRUZ - DATA NÃO INFORMADA"

SOBRE NOMBRES DE VÍCTIMAS (identifiable_victims) — OBLIGATORIO CUANDO EL TEXTO NOMBRA:
- Si el texto trae nombre propio, apodo o nombre social de la víctima (ej.: "Wal", "Gesse Alves de
  Sena", "Gustavo Rafael Campos Siqueira"), COMPLETA identifiable_victims[].name con ese
  nombre. NO dejes name = null solo porque edad/género ya basten para el resumen.
- Prefiere el nombre más completo disponible en el texto; si solo hay primer nombre o apodo,
  úsalo igual (mejor nombre parcial que anónimo).
- Solo omite name cuando el texto realmente no identifica a la persona (ej.: "un hombre de 31 años"
  sin nombre). En esos casos age/gender pueden estar completos y name = null.
- Nombres parciales o sociales ("Wal (identificada solo como)") aún cuentan como nombre —
  regístralos; esto evita UniqueEvents anónimos que no dedup con fuentes nombradas.

SOBRE AGENTES DE SEGURIDAD (víctimas y autores identificables):
- is_security_force=true para Carabineros, PDI, Gendarmería, etc.
- security_agent_type: solo si is_security_force=true (PM para Carabineros, PC para PDI,
  penal para Gendarmería, outro para otros).
- security_agent_on_duty: solo si is_security_force=true — true=en servicio/patrullaje;
  false=franco/fuera de servicio/de civil; null= texto no informa.
- Víctima policía: NO uses subtipo especial — completa is_security_force + security_agent_*
  en la víctima; event_subtype sigue la dinámica del crimen (simples, latrocinio, qualificado, etc.).
- intervencao_policial = policías matan a alguien; víctima policía = security_agent_* en la víctima.
- Grupos no identificados: usa is_security_force en unidentified_groups; type/on_duty solo
  en identifiable_victims o identifiable_perpetrators cuando haya individuo descrito.

SOBRE VÍCTIMA POLÍTICA (identifiable_victims[].political_role):
- Completar political_role SOLAMENTE cuando el texto identifica a la víctima como político o candidato.
- is_politician_or_candidate=true; status=elected | candidate | former_elected (ex-concejal → former_elected).
- office: cargo sin prefijo "ex-" (ej.: "concejal" incluso para ex-concejal).
- party: sigla/nombre según texto; null si no mencionado — NO inferir partido.

SOBRE GRUPOS CRIMINALES (homicide_dynamic.criminal_group_context):
- Usa SOLO información explícita sobre ESTE homicidio. NO inferir de "área dominada por narcotráfico"
  o antecedentes sin conexión declarada al caso.
- connected=true cuando texto vincula el crimen a facción/grupo/organización criminal.
- groups: nombres verbatim (Tren de Aragua, Los Gallegos, etc.).
- activity: enum — internal-discipline, internal-dispute, population-discipline,
  informant-elimination, debt-enforcement, territorial-dispute, economic-dispute,
  retaliatory, police-ambush, protest (incluye violencia anti-estado/reacción a política),
  collateral, unspecified (conectado pero mecanismo incierto).
- Si múltiples aplican: territorial-dispute > economic-dispute > retaliatory > unspecified.
- group_attacked / rival_actor / target_force / policy_trigger: solo cuando explícitos; null si incierto.
- activity_description: detalle extra basado en el texto cuando enum no basta.

SOBRE OPERACIÓN POLICIAL (homicide_dynamic.police_operation_context):
- Distinto de event_subtype=intervencao_policial — registra los hechos de la operación aquí.
- connected=true cuando muerte ocurrió durante operación policial oficial descrita.
- responsible_force, operation_name, targeted_armed_groups según texto.

SOBRE POLICÍA AUTOR FUERA DE SERVICIO (homicide_dynamic):
- off_duty_police_perpetrator=true cuando policía es autor/perpetrador fuera de operación oficial.
- off_duty_police_context: genuine_reaction | moonlighting | criminal_organization según texto.
"""

EXTRACTION_SYSTEM_PROMPT = EXTRACTION_SYSTEM_PROMPT_PT  # Default to Portuguese

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
- Vítima policial: NÃO use subtipo especial — preencha is_security_force + security_agent_*
  na vítima; event_subtype segue a dinâmica do crime (simples, latrocinio, qualificado, etc.).
- intervencao_policial = policiais matam alguém; vítima policial = security_agent_* na vítima.
- Grupos não identificados: use is_security_force em unidentified_groups; type/on_duty só
  em identifiable_victims ou identifiable_perpetrators quando houver indivíduo descrito.

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
    
    # Auto-detect language and select appropriate prompt if not overridden
    if system_prompt is None:
        lang = _detect_language(content, metadata)
        system_prompt = EXTRACTION_SYSTEM_PROMPT_ES if lang == "es" else EXTRACTION_SYSTEM_PROMPT_PT
        logger.debug(f"Detected language: {lang}, using {'Spanish' if lang == 'es' else 'Portuguese'} prompt")

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
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        max_retries=3,
        max_tokens=settings.extraction_max_output_tokens,
        timeout=180,
    )

    return apply_extraction_heuristics(event, content, metadata)


def raw_event_fields_from_event(event: ViolentDeathEvent) -> dict:
    """Map a ViolentDeathEvent to denormalized RawEvent column values.

    Shared by forward insert (`extract_source`) and in-place re-extract
    (`batch_jobs.reextract_sources`) so both paths stay aligned.
    """
    event_date = None
    if event.date_time.date:
        try:
            event_date = datetime.strptime(event.date_time.date, "%Y-%m-%d")
        except ValueError:
            logger.warning(f"Could not parse date: {event.date_time.date}")

    return {
        "event_date": event_date,
        "date_precision": event.date_time.date_precision,
        "time_of_day": event.date_time.time_of_day,
        "city": event.location_info.city,
        "state": event.location_info.state,
        "neighborhood": event.location_info.neighborhood,
        "victim_count": event.victims.number_of_victims,
        "identified_victim_count": event.victims.number_of_identifiable_victims,
        "perpetrator_count": (
            event.perpetrators.number_of_perpetrators if event.perpetrators else None
        ),
        "security_force_involved": derive_security_force_involved(event),
        "security_force_victim": derive_security_force_victim(event),
        "event_family": event.event_family,
        "event_subtype": event.event_subtype,
        "homicide_type": format_legacy_homicide_type(
            event.event_family, event.event_subtype
        ),
        "method_of_death": event.homicide_dynamic.method,
        "title": event.homicide_dynamic.title,
        "chronological_description": event.homicide_dynamic.chronological_description,
        "content_class": str(event.content_class),
        "extraction_data": event.model_dump(),
        "extraction_model": get_settings().extraction_model,
        "extraction_success": True,
        "extraction_error": None,
    }


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
    
    parts = ["## METADADOS DA NOTÍCIA / METADATOS DE LA NOTICIA\n"]
    
    if metadata.get("published_at"):
        parts.append(f"**Data de Publicação / Fecha de Publicación:** {metadata['published_at']}")
        parts.append("(Use esta data como referência para resolver datas relativas / Use esta fecha como referencia para resolver fechas relativas)\n")
    
    if metadata.get("headline"):
        parts.append(f"**Manchete / Titular:** {metadata['headline']}\n")
    
    if metadata.get("publisher"):
        parts.append(f"**Fonte / Medio:** {metadata['publisher']}\n")
    
    if metadata.get("url"):
        parts.append(f"**URL:** {metadata['url']}\n")
    
    parts.append("\n## CONTEÚDO DA NOTÍCIA / CONTENIDO DE LA NOTICIA\n")
    parts.append(content)
    
    return "\n".join(parts)


def _detect_language(content: str, metadata: dict | None = None) -> str:
    """Detect if content is Portuguese (BR) or Spanish (CL).
    
    Returns "pt" for Portuguese/Brazil or "es" for Spanish/Chile.
    """
    # Simple heuristic: count Spanish vs Portuguese markers
    content_lower = content.lower()
    
    # Spanish markers
    es_markers = [
        " fue ", " fueron ", " está ", " están ", " había ", " habían ",
        "asesinato", "femicidio", "carabineros", "pdi", " región ",
        " viernes ", " sábado ", " último ", "policía", " ayer ",
    ]
    
    # Portuguese markers  
    pt_markers = [
        " foi ", " foram ", " está ", " estão ", " havia ", " estavam ",
        "assassinato", "feminicídio", " polícia ", " última ", " ontem ",
        " sexta-feira ", " sábado ", "militar", " bairro ",
    ]
    
    es_count = sum(1 for marker in es_markers if marker in content_lower)
    pt_count = sum(1 for marker in pt_markers if marker in content_lower)
    
    # Also check metadata for Chilean sources
    if metadata:
        publisher = (metadata.get("publisher") or "").lower()
        url = (metadata.get("url") or "").lower()
        if any(domain in url or domain in publisher for domain in [".cl", "chile", "santiago"]):
            es_count += 3
    
    return "es" if es_count > pt_count else "pt"


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
                SELECT id, headline, content, published_at, publisher_name, resolved_url, country 
                FROM source_google_news 
                WHERE id = :id
            """),
            {"id": source_id}
        )
        row = result.fetchone()

        if not row:
            logger.warning(f"Source {source_id} not found")
            return None

        source_id_db, headline, content, published_at, publisher_name, resolved_url, country = row

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

    fields = raw_event_fields_from_event(event)

    # Step 3: persist the RawEvent in a fresh short-lived session.
    async with async_session_maker() as session:
        raw_event = RawEvent(
            source_google_news_id=source_id,
            country=country or "BR",  # Use source country, default to BR
            **fields,
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

