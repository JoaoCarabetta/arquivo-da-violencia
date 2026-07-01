/** Export column groups for the data tab and CSV download. */

const STORAGE_KEY = 'arv_export_columns';

export interface ExportColumnGroup {
  id: string;
  /** Matches `field` in dictionaryRows(). */
  dictionaryField: string;
  fields: string[];
}

export const EXPORT_COLUMN_GROUPS: ExportColumnGroup[] = [
  { id: 'id', dictionaryField: 'id', fields: ['id'] },
  { id: 'homicide_type', dictionaryField: 'homicide_type', fields: ['homicide_type'] },
  { id: 'method_of_death', dictionaryField: 'method_of_death', fields: ['method_of_death'] },
  { id: 'event_date', dictionaryField: 'event_date', fields: ['event_date'] },
  { id: 'time_of_day', dictionaryField: 'time_of_day', fields: ['time_of_day'] },
  {
    id: 'location_country_state_city',
    dictionaryField: 'country / state / city',
    fields: ['country', 'state', 'city'],
  },
  {
    id: 'location_neighborhood_street',
    dictionaryField: 'neighborhood / street',
    fields: ['neighborhood', 'street'],
  },
  {
    id: 'coordinates',
    dictionaryField: 'latitude / longitude',
    fields: ['latitude', 'longitude'],
  },
  { id: 'location_precision', dictionaryField: 'location_precision', fields: ['location_precision'] },
  { id: 'victim_count', dictionaryField: 'victim_count', fields: ['victim_count'] },
  { id: 'perpetrator_count', dictionaryField: 'perpetrator_count', fields: ['perpetrator_count'] },
  {
    id: 'security_force_involved',
    dictionaryField: 'security_force_involved',
    fields: ['security_force_involved'],
  },
  { id: 'title', dictionaryField: 'title', fields: ['title'] },
  {
    id: 'chronological_description',
    dictionaryField: 'chronological_description',
    fields: ['chronological_description'],
  },
  { id: 'source_count', dictionaryField: 'source_count', fields: ['source_count'] },
  { id: 'confirmed', dictionaryField: 'confirmed', fields: ['confirmed'] },
  {
    id: 'timestamps',
    dictionaryField: 'created_at / updated_at',
    fields: ['created_at', 'updated_at'],
  },
];

export const DEFAULT_SELECTED_COLUMN_IDS = EXPORT_COLUMN_GROUPS.map((group) => group.id);

export function loadSelectedColumnIds(): string[] {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_SELECTED_COLUMN_IDS;
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed) || parsed.length === 0) return DEFAULT_SELECTED_COLUMN_IDS;
    const valid = new Set(EXPORT_COLUMN_GROUPS.map((group) => group.id));
    const filtered = parsed.filter((id): id is string => typeof id === 'string' && valid.has(id));
    return filtered.length > 0 ? filtered : DEFAULT_SELECTED_COLUMN_IDS;
  } catch {
    return DEFAULT_SELECTED_COLUMN_IDS;
  }
}

export function saveSelectedColumnIds(ids: string[]): void {
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(ids));
}

export function selectedExportFields(ids: string[]): string[] {
  const selected = new Set(ids);
  return EXPORT_COLUMN_GROUPS.filter((group) => selected.has(group.id)).flatMap((group) => group.fields);
}

export function countSelectedFields(ids: string[]): number {
  return selectedExportFields(ids).length;
}
