import type { MapPoint } from '@/lib/api';
import type { MapBounds } from '@/components/map/CrimeMap';

export type PortalMode = 'stats' | 'feed' | 'data';

export interface PortalFilters {
  types: string[];
  methods: string[];
  periods: string[];
}

export const EMPTY_FILTERS: PortalFilters = { types: [], methods: [], periods: [] };

/** Canonical period key — merges spelling variants. */
export function normalizePeriodKey(value: string): string {
  const lower = value.toLowerCase();
  if (lower === 'manha' || lower === 'manhã') return 'manhã';
  return value;
}

function periodFilterVariants(value: string): string[] {
  const lower = value.toLowerCase();
  if (lower === 'manha' || lower === 'manhã') return ['manhã', 'manha'];
  return [value];
}

function matchesPeriodFilter(pointPeriod: string | null, selected: string[]): boolean {
  if (selected.length === 0) return true;
  if (!pointPeriod) return false;
  const allowed = new Set(selected.flatMap(periodFilterVariants));
  return allowed.has(pointPeriod);
}

export function hasActiveFilters(f: PortalFilters): boolean {
  return f.types.length + f.methods.length + f.periods.length > 0;
}

/** Apply the multi-select filters to a list of points. */
export function applyFilters(points: MapPoint[], f: PortalFilters): MapPoint[] {
  if (!hasActiveFilters(f)) return points;
  return points.filter(
    (p) =>
      (f.types.length === 0 || (p.t != null && f.types.includes(p.t))) &&
      (f.methods.length === 0 || (p.m != null && f.methods.includes(p.m))) &&
      matchesPeriodFilter(p.p, f.periods)
  );
}

/** Keep only points inside the current viewport bounds. */
export function pointsInBounds(points: MapPoint[], bounds: MapBounds | null): MapPoint[] {
  if (!bounds) return [];
  const [[minLng, minLat], [maxLng, maxLat]] = bounds;
  return points.filter(
    (p) => p.lng >= minLng && p.lng <= maxLng && p.lat >= minLat && p.lat <= maxLat
  );
}

/** Max individual markers drawn in scatter mode (matches design reference). */
export const SCATTER_POINT_CAP = 1200;

export function capPoints(points: MapPoint[], max = SCATTER_POINT_CAP): MapPoint[] {
  return points.length <= max ? points : points.slice(0, max);
}

export interface ViewportStats {
  total: number;
  victims: number;
  byType: Record<string, number>;
  byState: Record<string, number>;
  byPeriod: Record<string, number>;
  trend: Record<string, number>; // key: `${year}-${month}`
}

export function computeStats(points: MapPoint[]): ViewportStats {
  const s: ViewportStats = { total: points.length, victims: 0, byType: {}, byState: {}, byPeriod: {}, trend: {} };
  for (const p of points) {
    s.victims += p.v ?? 0;
    if (p.t) s.byType[p.t] = (s.byType[p.t] ?? 0) + 1;
    if (p.st) s.byState[p.st] = (s.byState[p.st] ?? 0) + 1;
    if (p.p) s.byPeriod[p.p] = (s.byPeriod[p.p] ?? 0) + 1;
    if (p.d) {
      const d = new Date(p.d);
      if (!Number.isNaN(d.getTime())) {
        const key = `${d.getUTCFullYear()}-${d.getUTCMonth()}`;
        s.trend[key] = (s.trend[key] ?? 0) + 1;
      }
    }
  }
  return s;
}

export interface TrendMonth {
  y: number;
  m: number;
  key: string;
}

/** The trailing 12 months ending at the most recent month present in points (or now). */
export function buildTrendMonths(points: MapPoint[]): TrendMonth[] {
  let latest = new Date();
  for (const p of points) {
    if (!p.d) continue;
    const d = new Date(p.d);
    if (!Number.isNaN(d.getTime()) && d > latest) latest = d;
  }
  let y = latest.getUTCFullYear();
  let m = latest.getUTCMonth();
  const out: TrendMonth[] = [];
  for (let i = 0; i < 12; i++) {
    out.unshift({ y, m, key: `${y}-${m}` });
    m--;
    if (m < 0) {
      m = 11;
      y--;
    }
  }
  return out;
}

/** Distinct, sorted filter values present in the dataset. */
export function distinctValues(points: MapPoint[], key: 't' | 'm' | 'p'): string[] {
  const set = new Set<string>();
  for (const p of points) {
    const v = p[key];
    if (!v) continue;
    set.add(key === 'p' ? normalizePeriodKey(v) : v);
  }
  return [...set].sort((a, b) => a.localeCompare(b));
}
