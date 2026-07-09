import type { Lang } from '@/lib/i18n';

export interface MethodologySection {
  id: string;
  title: string;
  paragraphs: string[];
  bullets?: string[];
}

export interface MethodologyContent {
  title: string;
  eyebrow: string;
  intro: string;
  pipelineSteps: string[];
  sections: MethodologySection[];
  disclaimer: string;
}

const PT: MethodologyContent = {
  title: 'Metodologia',
  eyebrow: 'Como os dados são produzidos',
  intro:
    'O Arquivo da Violência monitora mortes violentas no Brasil a partir de reportagens jornalísticas indexadas pelo Google News. O pipeline automatizado descobre manchetes, filtra as relevantes, baixa o texto das matérias, extrai campos estruturados com IA, deduplica coberturas do mesmo fato e geocodifica os eventos canônicos.',
  pipelineSteps: [
    'Ingestão (Google News RSS)',
    'Classificação de manchetes',
    'Download do texto',
    'Extração estruturada (LLM)',
    'Enriquecimento imediato',
    'Deduplicação em batch',
    'Enriquecimento multi-fonte',
    'Geocodificação',
  ],
  sections: [
    {
      id: 'sources',
      title: 'Fontes de dados',
      paragraphs: [
        'A fonte primária é o feed RSS do Google News, configurado para a edição brasileira (hl=pt-BR, gl=BR). Cada manchete é registrada com identificador único (google_news_id), URL resolvida, editora, data de publicação e query de busca que a descobriu.',
        'Hoje o sistema ingere exclusivamente via Google News RSS. Outras fontes (redes sociais, boletins oficiais) não fazem parte do pipeline atual.',
      ],
    },
    {
      id: 'cities',
      title: 'Cidades monitoradas',
      paragraphs: [
        'O monitoramento cobre 63 municípios: todas as 27 capitais estaduais mais cidades com população acima de 500 mil habitantes (IBGE 2022). A busca padrão por cidade usa a janela temporal when:1h (última hora).',
      ],
      bullets: [
        'Execução paralela de até 10 cidades simultâneas',
        'Rate limit conservador de ~12 requisições/minuto ao RSS',
        'Quando uma cidade atinge 100 resultados, a próxima execução fragmenta a busca por veículo (site:g1.globo.com, site:uol.com.br, etc.)',
      ],
    },
    {
      id: 'publishers',
      title: 'Veículos utilizados no sharding',
      paragraphs: [
        'Quando o limite de 100 resultados por query é atingido, a busca é dividida entre os principais veículos nacionais e regionais:',
      ],
      bullets: [
        'G1, UOL, Folha de S.Paulo, Estadão, O Globo, R7, Terra, Metrópoles, CNN Brasil, Band, Jovem Pan, Correio Braziliense, Gazeta do Povo',
        'Regionais: O Dia (RJ), Diário de Pernambuco, O Tempo (MG), A Crítica (AM), entre outros',
      ],
    },
    {
      id: 'classification',
      title: 'Classificação de manchetes',
      paragraphs: [
        'Antes de baixar a matéria completa, um modelo de linguagem (gemini-2.5-flash-lite) analisa apenas a manchete para decidir se trata de morte violenta. Manchetes classificadas como irrelevantes são descartadas; as relevantes seguem para download.',
      ],
      bullets: [
        'TRUE: morte violenta, assassinato, tiroteio com mortos, corpo encontrado, operação policial com morte, feminicídio, latrocínio',
        'FALSE: prisões, feridos sem morte, apreensões, políticas de segurança sem evento concreto',
      ],
    },
    {
      id: 'download',
      title: 'Download de matérias',
      paragraphs: [
        'Matérias aprovadas na classificação são baixadas com httpx (User-Agent de browser) e o texto principal é extraído com trafilatura. Timeout de 20 segundos por URL. Falhas de download são registradas e podem ser reprocessadas.',
      ],
    },
    {
      id: 'extraction',
      title: 'Extração estruturada',
      paragraphs: [
        'O texto da matéria é enviado ao modelo gemini-2.5-flash com schema estruturado (Instructor). Artigos longos são truncados em 32.000 caracteres. O prompt exige usar apenas informações explícitas no texto, com linguagem técnica/jurídica.',
        'Datas relativas ("ontem", "na sexta") são resolvidas com base na data de publicação da notícia. Se a data não for verificável, o campo fica nulo e o título inclui "DATA NÃO INFORMADA".',
      ],
      bullets: [
        'Local: bairro, rua, estabelecimento, cidade, estado, país',
        'Tempo: data, precisão, hora, período do dia (madrugada, manhã, tarde, noite)',
        'Pessoas: vítimas, autores, envolvimento de força de segurança',
        'Estatísticas "Por tipo": além dos subtipos, conta eventos com vítima de força de segurança (is_security_force na vítima)',
        'Dinâmica: subtipo de morte violenta, método de morte, descrição cronológica',
      ],
    },
    {
      id: 'taxonomy',
      title: 'Taxonomia de eventos',
      paragraphs: [
        'O arquivo público registra mortes violentas intencionais. Cada evento recebe uma família (event_family) e um subtipo (event_subtype). Tentativas de morte violenta e acidentes fatais culposos são classificados no pipeline, mas não entram no mapa nem nas estatísticas públicas.',
      ],
      bullets: [
        'Subtipos no arquivo público: simples, qualificado, feminicídio, latrocínio, infanticídio, intervenção policial, morte dolosa no trânsito',
        'Fora do arquivo público: tentativa, acidente fatal, não classificado',
        'Métodos: Arma de fogo, Arma branca, Estrangulamento, Asfixia, Espancamento, Atropelamento, Envenenamento, Objeto contundente, Incêndio, Queda, Outro',
      ],
    },
    {
      id: 'dedup',
      title: 'Deduplicação',
      paragraphs: [
        'O mesmo fato pode ser coberto por várias matérias. A deduplicação ocorre em duas fases:',
      ],
      bullets: [
        'Fase 1 (imediata): após cada extração, busca candidatos por data ±1 dia + mesma cidade, nome de vítima (fuzzy) ou bairro + data. LLM decide match com confiança mínima de 0,7',
        'Fase 2 (batch): eventos pendentes são agrupados por (data, cidade), pré-clusterizados por nome de vítima e consolidados por LLM. Cada cluster vira um UniqueEvent',
        'Preferência por não mesclar em caso de dúvida — eventos duplicados são possíveis',
      ],
    },
    {
      id: 'enrichment',
      title: 'Enriquecimento multi-fonte',
      paragraphs: [
        'Quando um UniqueEvent agrega várias matérias, um LLM sintetiza os campos finais (título, data, local, vítimas, descrição) combinando todas as fontes vinculadas. A regra é não inventar informação — apenas consolidar o que aparece nas matérias.',
      ],
    },
    {
      id: 'geocoding',
      title: 'Geocodificação',
      paragraphs: [
        'Eventos com cidade informada são geocodificados via Google Maps Geocoding API (region=br, language=pt-BR). A precisão declarada reflete o nível de detalhe disponível na entrada, nunca mais fino do que os dados permitem.',
      ],
      bullets: [
        'Precisões: exato, aproximado, centro do bairro, centro da cidade',
        'Sem chave de API, a geocodificação é ignorada e coordenadas ficam nulas',
        'Busca pública do site: CEPs resolvidos via ViaCEP; fallback Nominatim/OpenStreetMap',
      ],
    },
    {
      id: 'fields',
      title: 'Registro canônico (UniqueEvent)',
      paragraphs: [
        'Cada evento deduplicado é um UniqueEvent com campos de classificação, tempo, localização (textual e geocodificada), contagem de vítimas, descrição cronológica, número de fontes vinculadas e flag confirmed (revisão manual, padrão false).',
      ],
    },
    {
      id: 'schedule',
      title: 'Atualização',
      paragraphs: [
        'Quando ENABLE_CRON=true no worker, a ingestão roda no minuto 5 de cada hora (:05 UTC) e o processamento do backlog (classificar, baixar, extrair, deduplicar) no minuto 35 (:35 UTC), ambos a cada hora. A ingestão é independente do processamento, para que novas fontes entrem mesmo quando um run longo ainda está em andamento.',
        'O mapa público carrega eventos dos últimos 365 dias. A data "desde" exibida na interface corresponde ao evento mais antigo com data registrada no arquivo.',
      ],
    },
    {
      id: 'limitations',
      title: 'Limitações',
      paragraphs: [
        'O Arquivo da Violência deve ser utilizado como fonte de referência, não como substituto de registros oficiais (DATASUS, ISP/polícias estaduais).',
      ],
      bullets: [
        'Cobertura limitada a 63 cidades pré-configuradas, não todo o território nacional',
        'Só captura eventos reportados pela mídia indexada pelo Google News',
        'Classificação inicial usa apenas a manchete — títulos ambíguos podem ser descartados ou aceitos incorretamente',
        'Extração depende do conteúdo da matéria; informações ausentes no texto não são inferidas',
        'Sites com paywall, anti-bot ou HTML atípico podem falhar no download',
        'Geocodificação imprecisa quando só há cidade/bairro; endereços exatos são raros',
        'Dados não passam por revisão humana por padrão (confirmed=false)',
        'Limite de 100 resultados por query RSS pode causar perdas em cidades de alto volume',
      ],
    },
  ],
  disclaimer:
    'Os dados são extraídos automaticamente de reportagens jornalísticas e podem conter imprecisões. Use-os como referência, não como registro oficial. Use a aba Dados no painel lateral direito para exportar o CSV com todos os campos.',
};

const EN: MethodologyContent = {
  title: 'Methodology',
  eyebrow: 'How the data is produced',
  intro:
    'Arquivo da Violência monitors violent deaths in Brazil from news reports indexed by Google News. The automated pipeline discovers headlines, filters relevant ones, downloads article text, extracts structured fields with AI, deduplicates coverage of the same incident, and geocodes canonical events.',
  pipelineSteps: [
    'Ingestion (Google News RSS)',
    'Headline classification',
    'Text download',
    'Structured extraction (LLM)',
    'Immediate enrichment',
    'Batch deduplication',
    'Multi-source enrichment',
    'Geocoding',
  ],
  sections: [
  {
    id: 'sources',
    title: 'Data sources',
    paragraphs: [
      'The primary source is the Google News RSS feed, configured for the Brazilian edition (hl=pt-BR, gl=BR). Each headline is recorded with a unique identifier (google_news_id), resolved URL, publisher, publication date, and the search query that discovered it.',
      'Today the system ingests exclusively via Google News RSS. Other sources (social media, official bulletins) are not part of the current pipeline.',
    ],
  },
  {
    id: 'cities',
    title: 'Monitored cities',
    paragraphs: [
      'Monitoring covers 63 municipalities: all 27 state capitals plus cities with populations above 500,000 (2022 IBGE census). The default city search uses the when:1h time window (last hour).',
    ],
    bullets: [
      'Parallel execution of up to 10 cities simultaneously',
      'Conservative rate limit of ~12 requests/minute to the RSS feed',
      'When a city hits 100 results, the next run splits the search by publisher (site:g1.globo.com, site:uol.com.br, etc.)',
    ],
  },
  {
    id: 'publishers',
    title: 'Publishers used in sharding',
    paragraphs: [
      'When the 100-result limit per query is reached, the search is split across major national and regional outlets:',
    ],
    bullets: [
      'G1, UOL, Folha de S.Paulo, Estadão, O Globo, R7, Terra, Metrópoles, CNN Brasil, Band, Jovem Pan, Correio Braziliense, Gazeta do Povo',
      'Regional: O Dia (RJ), Diário de Pernambuco, O Tempo (MG), A Crítica (AM), among others',
    ],
  },
  {
    id: 'classification',
    title: 'Headline classification',
    paragraphs: [
      'Before downloading the full article, a language model (gemini-2.5-flash-lite) analyzes only the headline to decide if it concerns a violent death. Irrelevant headlines are discarded; relevant ones proceed to download.',
    ],
    bullets: [
      'TRUE: violent death, murder, shootout with deaths, body found, police operation with death, femicide, robbery-homicide',
      'FALSE: arrests, injuries without death, seizures, security policy without a concrete event',
    ],
  },
  {
    id: 'download',
    title: 'Article download',
    paragraphs: [
      'Articles approved in classification are downloaded with httpx (browser User-Agent) and main text is extracted with trafilatura. 20-second timeout per URL. Download failures are recorded and may be retried.',
    ],
  },
  {
    id: 'extraction',
    title: 'Structured extraction',
    paragraphs: [
      'Article text is sent to gemini-2.5-flash with a structured schema (Instructor). Long articles are truncated at 32,000 characters. The prompt requires using only explicit information from the text, with technical/legal language.',
      'Relative dates ("yesterday", "on Friday") are resolved using the news publication date. If the date cannot be verified, the field is null and the title includes "DATE NOT REPORTED".',
    ],
    bullets: [
      'Location: neighborhood, street, establishment, city, state, country',
      'Time: date, precision, time, period of day (dawn, morning, afternoon, night)',
      'People: victims, perpetrators, security-force involvement',
      '"By type" stats: besides subtypes, counts events with a security-force victim (is_security_force on the victim)',
      'Dynamics: violent death subtype, method of death, chronological description',
    ],
  },
  {
    id: 'taxonomy',
    title: 'Event taxonomy',
    paragraphs: [
      'The public archive records intentional violent deaths. Each event has an event_family and event_subtype. Attempted violent deaths and culpable fatal accidents are classified in the pipeline but excluded from the public map and statistics.',
    ],
    bullets: [
      'Public archive subtypes: simple, aggravated, femicide, robbery-homicide, infanticide, police intervention, intentional vehicular death',
      'Outside public archive: attempt, fatal accident, unclassified',
      'Methods: Firearm, Bladed weapon, Strangulation, Asphyxiation, Beating, Vehicle, Poisoning, Blunt object, Fire, Fall, Other',
    ],
  },
  {
    id: 'dedup',
    title: 'Deduplication',
    paragraphs: [
      'The same incident may be covered by multiple articles. Deduplication occurs in two phases:',
    ],
    bullets: [
      'Phase 1 (immediate): after each extraction, candidate matches are found by date ±1 day + same city, victim name (fuzzy), or neighborhood + date. LLM decides match with minimum confidence of 0.7',
      'Phase 2 (batch): pending events are grouped by (date, city), pre-clustered by victim name, and consolidated by LLM. Each cluster becomes a UniqueEvent',
      'Preference for not merging when uncertain — duplicate events are possible',
    ],
  },
  {
    id: 'enrichment',
    title: 'Multi-source enrichment',
    paragraphs: [
      'When a UniqueEvent aggregates multiple articles, an LLM synthesizes final fields (title, date, location, victims, description) combining all linked sources. The rule is not to invent information — only consolidate what appears in the articles.',
    ],
  },
  {
    id: 'geocoding',
    title: 'Geocoding',
    paragraphs: [
      'Events with a city are geocoded via Google Maps Geocoding API (region=br, language=pt-BR). Declared precision reflects the detail level available in the input, never finer than the data allows.',
    ],
    bullets: [
      'Precision levels: exact, approximate, neighborhood center, city center',
      'Without an API key, geocoding is skipped and coordinates remain null',
      'Public site search: ZIP codes resolved via ViaCEP; Nominatim/OpenStreetMap fallback',
    ],
  },
  {
    id: 'fields',
    title: 'Canonical record (UniqueEvent)',
    paragraphs: [
      'Each deduplicated event is a UniqueEvent with classification, time, location (textual and geocoded), victim count, chronological description, linked source count, and confirmed flag (manual review, default false).',
    ],
  },
  {
    id: 'schedule',
    title: 'Update schedule',
    paragraphs: [
      'When ENABLE_CRON=true on the worker, ingestion runs at minute 5 of every hour (:05 UTC) and backlog processing (classify, download, extract, dedup) at minute 35 (:35 UTC), both hourly. Ingest is decoupled from processing so new sources are fetched even while a long prior run is still in progress.',
      'The public map loads events from the last 365 days. The "since" date shown in the interface corresponds to the oldest dated event in the archive.',
    ],
  },
  {
    id: 'limitations',
    title: 'Limitations',
    paragraphs: [
      'Arquivo da Violência should be used as a reference source, not as a substitute for official records (DATASUS, state police/ISP).',
    ],
    bullets: [
      'Coverage limited to 63 pre-configured cities, not the entire national territory',
      'Only captures events reported by media indexed by Google News',
      'Initial classification uses only the headline — ambiguous titles may be discarded or accepted incorrectly',
      'Extraction depends on article content; information absent from the text is not inferred',
      'Sites with paywalls, anti-bot, or atypical HTML may fail to download',
      'Imprecise geocoding when only city/neighborhood is available; exact addresses are rare',
      'Data does not pass human review by default (confirmed=false)',
      '100-result RSS limit may cause losses in high-volume cities',
    ],
  },
  ],
  disclaimer:
    'Data is automatically extracted from news reporting and may contain inaccuracies. Use it as a reference, not as an official record. Use the Data tab in the right panel to export a CSV with all fields.',
};

export function methodologyContent(lang: Lang): MethodologyContent {
  return lang === 'pt' ? PT : EN;
}
