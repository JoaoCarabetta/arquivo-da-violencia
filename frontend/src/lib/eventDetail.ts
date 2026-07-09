import type { EventSource } from '@/lib/api';
import {
  dictionaryRows,
  fmtDateLong,
  fmtNumber,
  translateLocationPrecision,
  type Lang,
} from '@/lib/i18n';
import { formatSubtype, isHomicideSubtype } from '@/lib/taxonomy';

const DICTIONARY_FIELD_ALIASES: Record<string, string> = {
  id: 'id',
  event_family: 'event_family',
  event_subtype: 'event_subtype',
  homicide_type: 'homicide_type',
  method_of_death: 'method_of_death',
  event_date: 'event_date',
  time_of_day: 'time_of_day',
  country: 'country / state / city',
  state: 'country / state / city',
  city: 'country / state / city',
  neighborhood: 'neighborhood / street',
  street: 'neighborhood / street',
  latitude: 'latitude / longitude',
  longitude: 'latitude / longitude',
  location_precision: 'location_precision',
  victim_count: 'victim_count',
  perpetrator_count: 'perpetrator_count',
  security_force_involved: 'security_force_involved',
  criminal_group_connected: 'criminal_group_connected',
  criminal_groups: 'criminal_groups',
  criminal_group_activity: 'criminal_group_activity',
  criminal_group_activity_description: 'criminal_group_activity_description',
  criminal_group_attacked: 'criminal_group_attacked',
  police_operation_connected: 'police_operation_connected',
  police_operation_force: 'police_operation_force',
  police_operation_targeted_armed_groups: 'police_operation_targeted_armed_groups',
  off_duty_police_perpetrator: 'off_duty_police_perpetrator',
  off_duty_police_context: 'off_duty_police_context',
  politician_or_candidate_victim: 'politician_or_candidate_victim',
  victim_political_status: 'victim_political_status',
  victim_political_office: 'victim_political_office',
  victim_political_party: 'victim_political_party',
  title: 'title',
  chronological_description: 'chronological_description',
  source_count: 'source_count',
  created_at: 'created_at / updated_at',
  updated_at: 'created_at / updated_at',
};

export function dictionaryLabel(fieldKey: string, lang: Lang): string {
  const alias = DICTIONARY_FIELD_ALIASES[fieldKey] ?? fieldKey;
  const row = dictionaryRows(lang).find((entry) => entry.field === alias);
  return row?.desc ?? fieldKey;
}

export function hasDetailValue(value: unknown): boolean {
  if (value == null) return false;
  if (typeof value === 'string') return value.trim().length > 0;
  if (typeof value === 'number') return !Number.isNaN(value);
  if (typeof value === 'boolean') return true;
  return true;
}

export function formatCoordinates(lat: number | null | undefined, lng: number | null | undefined): string {
  if (lat == null || lng == null) return '';
  return `${lat.toFixed(6)}, ${lng.toFixed(6)}`;
}

export function formatRecordDate(iso: string | null | undefined, lang: Lang): string {
  if (!iso) return '';
  return fmtDateLong(iso, lang);
}

export function formatSubtypeSlug(value: string | null | undefined, lang: Lang): string {
  if (!value) return '';
  if (isHomicideSubtype(value)) return formatSubtype(value, lang);
  return value;
}

export function formatBoolean(value: boolean | null | undefined, lang: Lang, yes: string, no: string): string {
  if (value == null) return '';
  return value ? yes : no;
}

export function resolveSourceUrl(source: EventSource): string | null {
  return source.url ?? source.google_news_url ?? null;
}

export function sourceHeadline(source: EventSource, fallback: string): string {
  return source.headline || source.publisher_name || fallback;
}

export function formatCount(value: number | null | undefined, lang: Lang): string {
  if (value == null) return '';
  return fmtNumber(value, lang);
}

export function translateLocationPrecisionLabel(
  value: string | null | undefined,
  lang: Lang
): string {
  return translateLocationPrecision(value, lang);
}

const CRIMINAL_GROUP_ACTIVITY_LABELS: Record<string, Record<Lang, string>> = {
  'internal-discipline': { pt: 'Disciplina interna', en: 'Internal discipline' },
  'internal-dispute': { pt: 'Disputa interna', en: 'Internal dispute' },
  'population-discipline': { pt: 'Disciplina à população', en: 'Population discipline' },
  'informant-elimination': { pt: 'Eliminação de informante', en: 'Informant elimination' },
  'debt-enforcement': { pt: 'Cobrança de dívida', en: 'Debt enforcement' },
  'territorial-dispute': { pt: 'Disputa territorial', en: 'Territorial dispute' },
  'economic-dispute': { pt: 'Disputa econômica', en: 'Economic dispute' },
  retaliatory: { pt: 'Retaliação', en: 'Retaliatory' },
  'police-ambush': { pt: 'Emboscada policial', en: 'Police ambush' },
  protest: { pt: 'Protesto / anti-estado', en: 'Protest / anti-state' },
  collateral: { pt: 'Dano colateral', en: 'Collateral' },
  unspecified: { pt: 'Não especificado', en: 'Unspecified' },
};

const POLITICAL_STATUS_LABELS: Record<string, Record<Lang, string>> = {
  elected: { pt: 'Eleito(a)', en: 'Elected' },
  candidate: { pt: 'Candidato(a)', en: 'Candidate' },
  former_elected: { pt: 'Ex-mandatário(a)', en: 'Former officeholder' },
};

const OFF_DUTY_CONTEXT_LABELS: Record<string, Record<Lang, string>> = {
  genuine_reaction: { pt: 'Reação legítima', en: 'Genuine reaction' },
  moonlighting: { pt: 'Trabalho extra / bico', en: 'Moonlighting' },
  criminal_organization: { pt: 'Organização criminosa', en: 'Criminal organization' },
};

export function formatCriminalGroupActivity(value: string | null | undefined, lang: Lang): string {
  if (!value) return '';
  return CRIMINAL_GROUP_ACTIVITY_LABELS[value]?.[lang] ?? value;
}

export function formatPoliticalStatus(value: string | null | undefined, lang: Lang): string {
  if (!value) return '';
  return value
    .split(';')
    .map((part) => part.trim())
    .filter(Boolean)
    .map((part) => POLITICAL_STATUS_LABELS[part]?.[lang] ?? part)
    .join('; ');
}

export function formatOffDutyPoliceContext(value: string | null | undefined, lang: Lang): string {
  if (!value) return '';
  return OFF_DUTY_CONTEXT_LABELS[value]?.[lang] ?? value;
}

export function formatYesNo(value: boolean | null | undefined, lang: Lang): string {
  return formatBoolean(value, lang, lang === 'pt' ? 'Sim' : 'Yes', lang === 'pt' ? 'Não' : 'No');
}
