import type { MapPoint } from '@/lib/api';
import type { MapBounds } from '@/components/map/CrimeMap';

export type PortalMode = 'stats' | 'feed' | 'data';

export interface PortalFilters {
  types: string[];
  methods: string[];
  periods: string[];
  /** Inclusive ISO date (YYYY-MM-DD), empty = no lower bound. */
  startDate: string;
  /** Inclusive ISO date (YYYY-MM-DD), empty = no upper bound. */
  endDate: string;
}

export const EMPTY_FILTERS: PortalFilters = {
  types: [],
  methods: [],
  periods: [],
  startDate: '',
  endDate: '',
};

const PERIOD_ORDER = ['madrugada', 'manhã', 'manha', 'tarde', 'noite'];

export function sortPeriods(values: string[]): string[] {
  return [...values].sort((a, b) => {
    const ia = PERIOD_ORDER.indexOf(a.toLowerCase());
    const ib = PERIOD_ORDER.indexOf(b.toLowerCase());
    return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
  });
}

function pointDateKey(iso: string | null): string | null {
  if (!iso) return null;
  return iso.slice(0, 10);
}

function matchesDateFilter(iso: string | null, startDate: string, endDate: string): boolean {
  if (!startDate && !endDate) return true;
  const key = pointDateKey(iso);
  if (!key) return false;
  if (startDate && key < startDate) return false;
  if (endDate && key > endDate) return false;
  return true;
}

/** Format a Date as YYYY-MM-DD in local time. */
export function formatIsoDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

export function dateRangeForLastDays(days: number): { startDate: string; endDate: string } {
  const end = new Date();
  const start = new Date();
  start.setDate(start.getDate() - days);
  return { startDate: formatIsoDate(start), endDate: formatIsoDate(end) };
}

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
  return (
    f.types.length +
      f.methods.length +
      f.periods.length +
      (f.startDate ? 1 : 0) +
      (f.endDate ? 1 : 0) >
    0
  );
}

/** Apply the multi-select filters to a list of points. */
export function applyFilters(points: MapPoint[], f: PortalFilters): MapPoint[] {
  if (!hasActiveFilters(f)) return points;
  return points.filter(
    (p) =>
      (f.types.length === 0 || (p.t != null && f.types.includes(p.t))) &&
      (f.methods.length === 0 || (p.m != null && f.methods.includes(p.m))) &&
      matchesPeriodFilter(p.p, f.periods) &&
      matchesDateFilter(p.d, f.startDate, f.endDate)
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
