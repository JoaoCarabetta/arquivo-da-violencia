/**
 * Canonical event taxonomy (mirrors backend/app/taxonomy.py).
 * Public portal shows homicidio family subtypes only.
 */

import type { Lang } from '@/lib/i18n';
import type { MapPoint } from '@/lib/api';

export type HomicideSubtype =
  | 'simples'
  | 'qualificado'
  | 'feminicidio'
  | 'latrocinio'
  | 'infanticidio'
  | 'intervencao_policial'
  | 'morte_transito_doloso';

/** Display order for homicide subtype filters and stats. */
export const HOMICIDE_SUBTYPE_ORDER: HomicideSubtype[] = [
  'simples',
  'qualificado',
  'feminicidio',
  'latrocinio',
  'infanticidio',
  'intervencao_policial',
  'morte_transito_doloso',
];

const SUBTYPE_LABELS_PT: Record<HomicideSubtype, string> = {
  simples: 'Homicídio simples',
  qualificado: 'Homicídio qualificado',
  feminicidio: 'Feminicídio',
  latrocinio: 'Latrocínio',
  infanticidio: 'Infanticídio',
  intervencao_policial: 'Intervenção policial',
  morte_transito_doloso: 'Morte dolosa no trânsito',
};

const SUBTYPE_LABELS_EN: Record<HomicideSubtype, string> = {
  simples: 'Homicide',
  qualificado: 'Aggravated homicide',
  feminicidio: 'Femicide',
  latrocinio: 'Robbery-homicide',
  infanticidio: 'Infanticide',
  intervencao_policial: 'Police intervention',
  morte_transito_doloso: 'Intentional vehicular death',
};

/** Legacy flat homicide_type labels from prod history → subtype slug. */
const LEGACY_HOMICIDE_TYPE_MAP: Record<string, HomicideSubtype> = {
  'Homicídio': 'simples',
  'Homicídio simples': 'simples',
  'Homicídio Qualificado': 'qualificado',
  'Homicídio qualificado': 'qualificado',
  'Feminicídio': 'feminicidio',
  'Latrocínio': 'latrocinio',
  'Infanticídio': 'infanticidio',
  'Intervenção policial': 'intervencao_policial',
  'Morte no trânsito': 'morte_transito_doloso',
  'Morte dolosa no trânsito': 'morte_transito_doloso',
};

export function isHomicideSubtype(value: string): value is HomicideSubtype {
  return (HOMICIDE_SUBTYPE_ORDER as string[]).includes(value);
}

export function legacyLabelToSubtype(label: string | null | undefined): HomicideSubtype | null {
  if (!label) return null;
  const direct = LEGACY_HOMICIDE_TYPE_MAP[label.trim()];
  if (direct) return direct;
  const lower = label.toLowerCase();
  if (lower.includes('feminic')) return 'feminicidio';
  if (lower.includes('latroc')) return 'latrocinio';
  if (lower.includes('infantic')) return 'infanticidio';
  if (lower.includes('interven') || lower.includes('policial')) return 'intervencao_policial';
  if (lower.includes('trânsito') || lower.includes('transito')) return 'morte_transito_doloso';
  if (lower.includes('qualificad')) return 'qualificado';
  return 'simples';
}

export function pointSubtype(point: MapPoint): HomicideSubtype {
  if (point.su && isHomicideSubtype(point.su)) return point.su;
  return legacyLabelToSubtype(point.t) ?? 'simples';
}

export function formatSubtype(subtype: HomicideSubtype, lang: Lang): string {
  return lang === 'en' ? SUBTYPE_LABELS_EN[subtype] : SUBTYPE_LABELS_PT[subtype];
}

export function formatPointLabel(point: MapPoint, lang: Lang): string {
  return formatSubtype(pointSubtype(point), lang);
}

export function subtypeColor(subtype: HomicideSubtype): string {
  switch (subtype) {
    case 'qualificado':
    case 'feminicidio':
    case 'latrocinio':
      return '#872B26';
    case 'intervencao_policial':
      return '#9E7616';
    case 'infanticidio':
    case 'morte_transito_doloso':
      return '#65645B';
    default:
      return '#C8473F';
  }
}

/** Filter/export API value for a homicide subtype slug. */
export function subtypeFilterValue(subtype: HomicideSubtype): string {
  return subtype;
}

export function formatTaxonomyFields(
  family: string | null | undefined,
  subtype: string | null | undefined,
  legacyType: string | null | undefined,
  lang: Lang
): string {
  if (subtype && isHomicideSubtype(subtype)) {
    return formatSubtype(subtype, lang);
  }
  if (legacyType) {
    const mapped = legacyLabelToSubtype(legacyType);
    if (mapped) return formatSubtype(mapped, lang);
  }
  if (family === 'homicidio') {
    return lang === 'pt' ? 'Homicídio' : 'Homicide';
  }
  return lang === 'pt' ? 'Não classificado' : 'Unclassified';
}

export function taxonomyColor(
  family: string | null | undefined,
  subtype: string | null | undefined,
  legacyType?: string | null
): string {
  if (subtype && isHomicideSubtype(subtype)) return subtypeColor(subtype);
  const mapped = legacyLabelToSubtype(legacyType ?? null);
  if (mapped) return subtypeColor(mapped);
  return 'var(--stone-500)';
}

export function distinctSubtypes(points: MapPoint[]): HomicideSubtype[] {
  const set = new Set<HomicideSubtype>();
  for (const p of points) {
    set.add(pointSubtype(p));
  }
  return HOMICIDE_SUBTYPE_ORDER.filter((s) => set.has(s));
}

/** Short PT label for admin tables. */
export function adminTypeLabel(event: {
  event_subtype?: string | null;
  homicide_type?: string | null;
}): string | null {
  if (event.event_subtype && isHomicideSubtype(event.event_subtype)) {
    return formatSubtype(event.event_subtype, 'pt');
  }
  if (event.homicide_type) {
    const mapped = legacyLabelToSubtype(event.homicide_type);
    if (mapped) return formatSubtype(mapped, 'pt');
    return event.homicide_type;
  }
  return null;
}
