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

const MS_24H = 24 * 60 * 60 * 1000;

export interface Last24hStats {
  total: number;
  victims: number;
}

/** Events in `points` with `d` within the trailing 24 hours (missing/invalid dates excluded). */
export function computeLast24hStats(points: MapPoint[]): Last24hStats {
  const cutoff = Date.now() - MS_24H;
  let total = 0;
  let victims = 0;
  for (const p of points) {
    if (!p.d) continue;
    const t = Date.parse(p.d);
    if (Number.isNaN(t) || t < cutoff) continue;
    total++;
    victims += p.v ?? 0;
  }
  return { total, victims };
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

function niceCeil(value: number): number {
  if (value <= 0) return 1;
  const exponent = Math.floor(Math.log10(value));
  const magnitude = 10 ** exponent;
  const normalized = value / magnitude;
  let nice: number;
  if (normalized <= 1) nice = 1;
  else if (normalized <= 2) nice = 2;
  else if (normalized <= 5) nice = 5;
  else nice = 10;
  return nice * magnitude;
}

/** Round reference ticks (1–2 lines) and scale ceiling for the monthly trend chart. */
export function trendChartScale(peak: number): { scaleMax: number; ticks: number[] } {
  if (peak <= 0) return { scaleMax: 1, ticks: [] };
  const scaleMax = niceCeil(peak);
  if (peak <= 3 || scaleMax <= 4) {
    return { scaleMax, ticks: [scaleMax] };
  }
  return { scaleMax, ticks: [0, scaleMax] };
}

/** Grid cell size in meters — mirrors `cellSizeForZoom` in CrimeMap. */
export function gridCellSizeMeters(zoom: number): number {
  if (zoom < 5) return 40000;
  if (zoom < 7) return 15000;
  if (zoom < 9) return 5000;
  return 1500;
}

/** Zoom level at which the map switches from density grid to individual markers. */
export const SCATTER_ZOOM_THRESHOLD = 12;

/** Peak event count in any single grid cell for the current viewport and zoom. */
export function computeGridPeakCount(
  points: MapPoint[],
  bounds: MapBounds | null,
  zoom: number
): number {
  const inView = bounds ? pointsInBounds(points, bounds) : points;
  if (inView.length === 0) return 0;

  const cellMeters = gridCellSizeMeters(zoom);
  const metersPerDegLat = 111_320;
  const [[minLng, minLat], [maxLng, maxLat]] = bounds ?? [
    [-180, -90],
    [180, 90],
  ];
  const centerLat = (minLat + maxLat) / 2;
  const cosLat = Math.cos((centerLat * Math.PI) / 180) || 1;
  const cellLat = cellMeters / metersPerDegLat;
  const cellLng = cellMeters / (metersPerDegLat * cosLat);

  const counts = new Map<string, number>();
  for (const p of inView) {
    const key = `${Math.floor(p.lat / cellLat)}:${Math.floor(p.lng / cellLng)}`;
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  let peak = 0;
  for (const n of counts.values()) {
    if (n > peak) peak = n;
  }
  return peak;
}

/** Round numeric labels for the map density legend (e.g. 0 — 5 — 10). */
export function densityLegendScale(peak: number): { scaleMax: number; labels: number[] } {
  if (peak <= 0) return { scaleMax: 1, labels: [0, 1] };
  const { scaleMax } = trendChartScale(peak);
  if (scaleMax <= 3) return { scaleMax, labels: [0, scaleMax] };
  const mid = Math.round(scaleMax / 2);
  if (mid <= 0 || mid >= scaleMax) return { scaleMax, labels: [0, scaleMax] };
  return { scaleMax, labels: [0, mid, scaleMax] };
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
