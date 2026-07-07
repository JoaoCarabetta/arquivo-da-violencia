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
