/**
 * Bilingual (PT/EN) strings and value translators for the public portal.
 *
 * The backend stores human-readable Portuguese canonical values for
 * homicide_type / method_of_death / time_of_day. For PT we render them
 * as-is; for EN we map the known values. Unknown values fall back to the
 * original string so nothing ever disappears from the UI.
 */

export type Lang = 'pt' | 'en';

export interface Strings {
  tagline: string;
  searchPlaceholder: string;
  noResults: string;
  geocodeFailed: string;
  navMap: string;
  navFeed: string;
  navData: string;
  navAbout: string;
  navMethodology: string;
  temporalScope: string;
  aboutMethodologyLink: string;
  langSwitch: string;
  events: string;
  victims: string;
  filters: string;
  clear: string;
  fType: string;
  fMethod: string;
  fPeriod: string;
  trend: string;
  byType: string;
  byState: string;
  timeOfDay: string;
  reset: string;
  emptyArea: string;
  fewer: string;
  more: string;
  loadingMap: string;
  legendTitle: string;
  back: string;
  summary: string;
  method: string;
  securityForce: string;
  timeNote: string;
  feedNote: string;
  dataIntro: string;
  downloadCsv: string;
  recordsExport: string;
  columns: string;
  dictionary: string;
  dataNote: string;
  allEvents: string;
  exportStartDate: string;
  exportEndDate: string;
  exportDateRangeInvalid: string;
  exportDateRangeOptional: string;
  statistics: string;
  inThisView: string;
  mapLoadingStats: string;
  filtersActive: string;
  inVisibleArea: string;
  state: string;
  reportedBy: string;
  newsSource: string;
  newsSources: string;
  victim: string;
  victimsLower: string;
  loadingEvent: string;
  eventNotFound: string;
  aboutEyebrow: string;
  aboutTitle: string;
  aboutP1: string;
  aboutP2: string;
  disclaimerLabel: string;
  disclaimer: string;
}

const PT: Strings = {
  tagline: 'Arquivo público de mortes violentas reportadas no Brasil',
  searchPlaceholder: 'Buscar cidade, bairro, estado ou CEP',
  noResults: 'Nenhum local encontrado',
  geocodeFailed: 'Não foi possível localizar esse endereço',
  navMap: 'Mapa',
  navFeed: 'Linha do tempo',
  navData: 'Dados',
  navAbout: 'Sobre',
  navMethodology: 'Metodologia',
  temporalScope: 'No recorte atual desde {date}',
  aboutMethodologyLink: 'Leia a metodologia completa',
  langSwitch: 'English',
  events: 'eventos registrados',
  victims: 'vítimas fatais',
  filters: 'Filtros',
  clear: 'Limpar',
  fType: 'Tipo de evento',
  fMethod: 'Método',
  fPeriod: 'Período do dia',
  trend: 'Tendência mensal',
  byType: 'Por tipo',
  byState: 'Por estado',
  timeOfDay: 'Período do dia',
  reset: 'Brasil',
  emptyArea: 'Nenhum evento nesta área.',
  fewer: 'menos',
  more: 'mais',
  loadingMap: 'Carregando mapa',
  legendTitle: 'Densidade por área',
  back: 'Voltar',
  summary: 'Resumo do caso',
  method: 'Método',
  securityForce: 'Força de segurança',
  timeNote: 'Período aproximado do registro',
  feedNote: 'Eventos visíveis na área atual do mapa, mais recentes primeiro.',
  dataIntro:
    'Baixe os dados brutos dos eventos geocodados do recorte de 365 dias, com os filtros ativos no momento. O arquivo segue o dicionário de dados completo abaixo.',
  downloadCsv: 'Baixar CSV',
  recordsExport: 'registros geocodados no recorte',
  columns: 'colunas',
  dictionary: 'Dicionário de dados',
  dataNote: 'O download inclui eventos geocodados dos últimos 365 dias com os filtros ativos (não limitado à área visível do mapa).',
  allEvents: 'Todos os eventos geocodados do recorte de 365 dias.',
  exportStartDate: 'Data inicial',
  exportEndDate: 'Data final',
  exportDateRangeInvalid: 'A data inicial não pode ser posterior à data final.',
  exportDateRangeOptional: 'Opcional — deixe em branco para usar o recorte padrão de 365 dias.',
  statistics: 'Estatísticas',
  inThisView: 'Nesta área',
  mapLoadingStats: 'Aguardando área do mapa…',
  filtersActive: ' · filtros ativos',
  inVisibleArea: 'No recorte visível do mapa',
  state: 'Estado',
  reportedBy: 'Reportado por ',
  newsSource: ' fonte jornalística',
  newsSources: ' fontes jornalísticas',
  victim: 'vítima',
  victimsLower: 'vítimas',
  loadingEvent: 'Carregando evento',
  eventNotFound: 'Evento não encontrado.',
  aboutEyebrow: 'Sobre o projeto',
  aboutTitle: 'Um registro do que os dados oficiais nem sempre reportam',
  aboutP1:
    'O Arquivo da Violência reúne, em um só lugar e em tempo real, as mortes violentas noticiadas no Brasil. Cada evento é extraído automaticamente de reportagens da imprensa, geolocalizado e informações sobre a morte são estruturadas em campos comparáveis. Incluímos informações que nem sempre estão disponíveis em dados oficiais, como a geolocalização estimada e o método violento utilizado.',
  aboutP2:
    'Nosso objetivo é tornar visíveis a escala e a distribuição da violência — por bairro, cidade, CEP e período. Oferecemos os dados abertos para jornalistas, pesquisadores e a sociedade, para qualificar o debate e a tomada de decisão sobre segurança pública no país.',
  disclaimerLabel: 'Aviso',
  disclaimer:
    'Nossos dados sobre mortes violentas são obtidos a partir de reportagens jornalísticas. Use-os como referência, não como registro oficial. Consulte a metodologia completa para detalhes sobre coleta, processamento e limitações.',
};

const EN: Strings = {
  tagline: 'A public archive of violent deaths reported in Brazil',
  searchPlaceholder: 'Search city, neighborhood, state or ZIP',
  noResults: 'No place found',
  geocodeFailed: 'Could not locate that address',
  navMap: 'Map',
  navFeed: 'Timeline',
  navData: 'Data',
  navAbout: 'About',
  navMethodology: 'Methodology',
  temporalScope: 'In the current view since {date}',
  aboutMethodologyLink: 'Read the full methodology',
  langSwitch: 'Português',
  events: 'recorded events',
  victims: 'fatal victims',
  filters: 'Filters',
  clear: 'Clear',
  fType: 'Event type',
  fMethod: 'Method',
  fPeriod: 'Time of day',
  trend: 'Monthly trend',
  byType: 'By type',
  byState: 'By state',
  timeOfDay: 'Time of day',
  reset: 'Brazil',
  emptyArea: 'No events in this area.',
  fewer: 'fewer',
  more: 'more',
  loadingMap: 'Loading map',
  legendTitle: 'Density by area',
  back: 'Back',
  summary: 'Case summary',
  method: 'Method',
  securityForce: 'Security force',
  timeNote: 'Approximate time recorded',
  feedNote: 'Events visible in the current map area, most recent first.',
  dataIntro:
    'Download raw data for geocoded events in the 365-day window with the currently active filters. The file follows the full data dictionary below.',
  downloadCsv: 'Download CSV',
  recordsExport: 'geocoded records in current view',
  columns: 'columns',
  dictionary: 'Data dictionary',
  dataNote: 'Download includes geocoded events from the last 365 days matching active filters (not limited to the visible map area).',
  allEvents: 'All geocoded events in the 365-day window.',
  exportStartDate: 'Start date',
  exportEndDate: 'End date',
  exportDateRangeInvalid: 'Start date cannot be after end date.',
  exportDateRangeOptional: 'Optional — leave blank to use the default 365-day window.',
  statistics: 'Statistics',
  inThisView: 'In this view',
  mapLoadingStats: 'Waiting for map area…',
  filtersActive: ' · filters active',
  inVisibleArea: 'In the visible map area',
  state: 'State',
  reportedBy: 'Reported by ',
  newsSource: ' news source',
  newsSources: ' news sources',
  victim: 'victim',
  victimsLower: 'victims',
  loadingEvent: 'Loading event',
  eventNotFound: 'Event not found.',
  aboutEyebrow: 'About the project',
  aboutTitle: 'A record of what official data does not always report',
  aboutP1:
    'Arquivo da Violência gathers, in one place and in near real time, violent deaths reported in the news across Brazil. Each event is automatically extracted from press reports, geolocated and structured into comparable fields. We include information not always available in official data, such as estimated geolocation and the violent method used.',
  aboutP2:
    'Our goal is to make the scale and distribution of violence visible — by neighborhood, city, postal code and period — and to offer open data to journalists, researchers and society, to inform debate and public-security decision-making.',
  disclaimerLabel: 'Notice',
  disclaimer:
    'Our data on violent deaths comes from news reports. Use it as a reference, not as an official record. See the full methodology for details on collection, processing, and limitations.',
};

export function strings(lang: Lang): Strings {
  return lang === 'pt' ? PT : EN;
}

// ---- Value translators (canonical PT value -> display) ----------------

const TYPE_EN: Record<string, string> = {
  'Homicídio': 'Homicide',
  'Homicídio Qualificado': 'Aggravated homicide',
  'Homicídio Culposo': 'Negligent homicide',
  'Tentativa de Homicídio': 'Attempted homicide',
  'Latrocínio': 'Robbery-homicide',
  'Feminicídio': 'Femicide',
  'Infanticídio': 'Infanticide',
  'Outro': 'Other',
  'Não especificado': 'Unspecified',
};

const METHOD_EN: Record<string, string> = {
  'Arma de fogo': 'Firearm',
  'Arma branca': 'Bladed weapon',
  'Estrangulamento': 'Strangulation',
  'Asfixia': 'Asphyxiation',
  'Espancamento': 'Beating',
  'Atropelamento': 'Vehicle',
  'Envenenamento': 'Poisoning',
  'Objeto contundente': 'Blunt object',
  'Incêndio': 'Fire',
  'Queda': 'Fall',
  'Outro': 'Other',
  'Não especificado': 'Unspecified',
};

const PERIOD_EN: Record<string, string> = {
  'madrugada': 'Dawn',
  'manhã': 'Morning',
  'tarde': 'Afternoon',
  'noite': 'Night',
  'não informado': 'Unknown',
};

function titleCasePt(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

export function translateType(value: string | null | undefined, lang: Lang): string {
  if (!value) return lang === 'pt' ? 'Não classificado' : 'Unclassified';
  if (lang === 'en') return TYPE_EN[value] ?? value;
  return value;
}

export function translateMethod(value: string | null | undefined, lang: Lang): string {
  if (!value) return lang === 'pt' ? 'Não especificado' : 'Unspecified';
  if (lang === 'en') return METHOD_EN[value] ?? value;
  return value;
}

export function translatePeriod(value: string | null | undefined, lang: Lang): string {
  if (!value) return lang === 'pt' ? 'Não informado' : 'Unknown';
  if (lang === 'en') return PERIOD_EN[value.toLowerCase()] ?? titleCasePt(value);
  return titleCasePt(value);
}

/** Color for a homicide type, matching the design's red/gold/stone scheme. */
export function typeColor(value: string | null | undefined): string {
  if (!value) return 'var(--stone-500)';
  const v = value.toLowerCase();
  if (v.includes('qualificad') || v.includes('feminic') || v.includes('latroc')) return '#872B26';
  if (v.includes('tentativa')) return '#9E7616';
  if (v.includes('outro') || v.includes('não especific') || v.includes('culposo')) return '#65645B';
  return '#C8473F';
}

const MONTHS_PT = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'];
const MONTHS_EN = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const MONTHS_FULL_PT = [
  'janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho',
  'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro',
];
const MONTHS_FULL_EN = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

export function monthShort(month: number, lang: Lang): string {
  return (lang === 'pt' ? MONTHS_PT : MONTHS_EN)[month] ?? '';
}

export function locale(lang: Lang): string {
  return lang === 'pt' ? 'pt-BR' : 'en-US';
}

export function fmtNumber(n: number | null | undefined, lang: Lang): string {
  return (n || 0).toLocaleString(locale(lang));
}

export function fmtDateShort(iso: string, lang: Lang): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.getUTCDate()} ${monthShort(d.getUTCMonth(), lang)} ${d.getUTCFullYear()}`;
}

export function fmtDateLong(iso: string, lang: Lang): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const full = lang === 'pt' ? MONTHS_FULL_PT : MONTHS_FULL_EN;
  return lang === 'pt'
    ? `${d.getUTCDate()} de ${full[d.getUTCMonth()]} de ${d.getUTCFullYear()}`
    : `${full[d.getUTCMonth()]} ${d.getUTCDate()}, ${d.getUTCFullYear()}`;
}

export interface DictionaryRow {
  field: string;
  desc: string;
}

export function dictionaryRows(lang: Lang): DictionaryRow[] {
  const pt: [string, string][] = [
    ['id', 'Identificador único do evento'],
    ['homicide_type', 'Tipo de evento'],
    ['method_of_death', 'Método (arma de fogo, etc.)'],
    ['event_date', 'Data do evento (ISO 8601)'],
    ['time_of_day', 'Período do dia'],
    ['country / state / city', 'País, estado e cidade'],
    ['neighborhood / street', 'Bairro e logradouro'],
    ['latitude / longitude', 'Coordenadas geográficas'],
    ['location_precision', 'Precisão da geolocalização'],
    ['victim_count', 'Número de vítimas fatais'],
    ['perpetrator_count', 'Número de perpetradores'],
    ['security_force_involved', 'Envolvimento de forças de segurança'],
    ['title', 'Título resumido do evento'],
    ['chronological_description', 'Descrição cronológica detalhada'],
    ['source_count', 'Número de fontes jornalísticas'],
    ['confirmed', 'Status de confirmação manual'],
    ['created_at / updated_at', 'Datas de registro e atualização'],
  ];
  const en: [string, string][] = [
    ['id', 'Unique event identifier'],
    ['homicide_type', 'Event type'],
    ['method_of_death', 'Method (firearm, etc.)'],
    ['event_date', 'Event date (ISO 8601)'],
    ['time_of_day', 'Time of day'],
    ['country / state / city', 'Country, state and city'],
    ['neighborhood / street', 'Neighborhood and street'],
    ['latitude / longitude', 'Geographic coordinates'],
    ['location_precision', 'Geolocation precision'],
    ['victim_count', 'Number of fatal victims'],
    ['perpetrator_count', 'Number of perpetrators'],
    ['security_force_involved', 'Security-force involvement'],
    ['title', 'Short event title'],
    ['chronological_description', 'Detailed chronological description'],
    ['source_count', 'Number of news sources'],
    ['confirmed', 'Manual confirmation status'],
    ['created_at / updated_at', 'Record and update dates'],
  ];
  return (lang === 'pt' ? pt : en).map(([field, desc]) => ({ field, desc }));
}

export const UF_NAMES: Record<string, string> = {
  AC: 'Acre', AL: 'Alagoas', AP: 'Amapá', AM: 'Amazonas', BA: 'Bahia',
  CE: 'Ceará', DF: 'Distrito Federal', ES: 'Espírito Santo', GO: 'Goiás',
  MA: 'Maranhão', MT: 'Mato Grosso', MS: 'Mato Grosso do Sul', MG: 'Minas Gerais',
  PA: 'Pará', PB: 'Paraíba', PR: 'Paraná', PE: 'Pernambuco', PI: 'Piauí',
  RJ: 'Rio de Janeiro', RN: 'Rio Grande do Norte', RS: 'Rio Grande do Sul',
  RO: 'Rondônia', RR: 'Roraima', SC: 'Santa Catarina', SP: 'São Paulo',
  SE: 'Sergipe', TO: 'Tocantins',
};

export function ufName(uf: string | null | undefined): string {
  if (!uf) return '';
  return UF_NAMES[uf.toUpperCase()] ?? uf;
}
