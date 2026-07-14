import type { MapPoint } from '@/lib/api';
import {
  pointHasSecurityForceVictim,
  pointSubtype,
  SECURITY_FORCE_VICTIM_KEY,
} from '@/lib/taxonomy';
import type { MapBounds } from '@/components/map/CrimeMap';
import {
  aggregatePointsToH3Cells,
  h3ResolutionForZoom,
  peakH3Count,
} from '@/lib/h3Grid';

export type PortalMode = 'stats' | 'feed' | 'data';

export type FilterGroup = 'types' | 'methods' | 'periods' | 'states' | 'cities';

export interface PortalFilters {
  /** Homicide subtype slugs (e.g. feminicidio, latrocinio). */
  types: string[];
  methods: string[];
  periods: string[];
  /** UF codes, e.g. "SP". */
  states: string[];
  /** City names from MapPoint.c. */
  cities: string[];
  /** Inclusive ISO date (YYYY-MM-DD), empty = no lower bound. */
  startDate: string;
  /** Inclusive ISO date (YYYY-MM-DD), empty = no upper bound. */
  endDate: string;
}

export const DEFAULT_DATE_RANGE_DAYS = 90;

export const EMPTY_FILTERS: PortalFilters = {
  types: [],
  methods: [],
  periods: [],
  states: [],
  cities: [],
  startDate: '',
  endDate: '',
};

export const DEFAULT_FILTERS: PortalFilters = {
  types: [],
  methods: [],
  periods: [],
  states: [],
  cities: [],
  ...dateRangeForLastDays(DEFAULT_DATE_RANGE_DAYS),
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

function parseIsoDate(iso: string): Date {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, m - 1, d);
}

function mondayOfWeek(d: Date): Date {
  const day = d.getDay();
  const diff = day === 0 ? -6 : 1 - day;
  const monday = new Date(d);
  monday.setDate(d.getDate() + diff);
  monday.setHours(0, 0, 0, 0);
  return monday;
}

function weekKeyForIso(iso: string): string | null {
  const key = pointDateKey(iso);
  if (!key) return null;
  return formatIsoDate(mondayOfWeek(parseIsoDate(key)));
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

function datesMatchDefault(f: PortalFilters): boolean {
  const def = dateRangeForLastDays(DEFAULT_DATE_RANGE_DAYS);
  return f.startDate === def.startDate && f.endDate === def.endDate;
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
    f.types.length > 0 ||
    f.methods.length > 0 ||
    f.periods.length > 0 ||
    f.states.length > 0 ||
    f.cities.length > 0 ||
    !datesMatchDefault(f)
  );
}

/** Apply filters while ignoring one or more dimensions (for filter-option charts). */
export function applyFiltersExcept(
  points: MapPoint[],
  f: PortalFilters,
  except: FilterGroup | FilterGroup[]
): MapPoint[] {
  const skip = new Set(Array.isArray(except) ? except : [except]);
  return applyFilters(points, {
    ...f,
    types: skip.has('types') ? [] : f.types,
    methods: skip.has('methods') ? [] : f.methods,
    periods: skip.has('periods') ? [] : f.periods,
    states: skip.has('states') ? [] : f.states,
    cities: skip.has('cities') ? [] : f.cities,
  });
}

/** Viewport-clipped points with one filter dimension omitted (multi-select bar charts). */
export function pointsInViewExcept(
  allPoints: MapPoint[],
  f: PortalFilters,
  bounds: MapBounds | null,
  except: FilterGroup
): MapPoint[] {
  if (!bounds) return [];
  return pointsInBounds(applyFiltersExcept(allPoints, f, except), bounds);
}

function matchesTypeFilter(point: MapPoint, types: string[]): boolean {
  if (types.length === 0) return true;
  return types.some((t) => {
    if (t === SECURITY_FORCE_VICTIM_KEY) return pointHasSecurityForceVictim(point);
    return pointSubtype(point) === t;
  });
}

/** Apply the multi-select filters to a list of points. */
export function applyFilters(points: MapPoint[], f: PortalFilters): MapPoint[] {
  return points.filter(
    (p) =>
      matchesTypeFilter(p, f.types) &&
      (f.methods.length === 0 || (p.m != null && f.methods.includes(p.m))) &&
      (f.states.length === 0 || (p.st != null && f.states.includes(p.st))) &&
      (f.cities.length === 0 || (p.c != null && f.cities.includes(p.c))) &&
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
  bySubtype: Record<string, number>;
  byMethod: Record<string, number>;
  byState: Record<string, number>;
  byCity: Record<string, number>;
  byPeriod: Record<string, number>;
  byWeek: Record<string, number>;
  trend: Record<string, number>; // key: `${year}-${month}` → fatal victims
}

/** Zoom at which the stats sidebar switches from state to city breakdown. */
export const CITY_STATS_ZOOM_THRESHOLD = 8;

export function computeStats(points: MapPoint[]): ViewportStats {
  const s: ViewportStats = {
    total: points.length,
    victims: 0,
    bySubtype: {},
    byMethod: {},
    byState: {},
    byCity: {},
    byPeriod: {},
    byWeek: {},
    trend: {},
  };
  for (const p of points) {
    s.victims += p.v ?? 0;
    const subtype = pointSubtype(p);
    s.bySubtype[subtype] = (s.bySubtype[subtype] ?? 0) + 1;
    if (pointHasSecurityForceVictim(p)) {
      s.bySubtype[SECURITY_FORCE_VICTIM_KEY] =
        (s.bySubtype[SECURITY_FORCE_VICTIM_KEY] ?? 0) + 1;
    }
    if (p.m) s.byMethod[p.m] = (s.byMethod[p.m] ?? 0) + 1;
    if (p.st) s.byState[p.st] = (s.byState[p.st] ?? 0) + 1;
    if (p.c) s.byCity[p.c] = (s.byCity[p.c] ?? 0) + 1;
    if (p.p) s.byPeriod[p.p] = (s.byPeriod[p.p] ?? 0) + 1;
    if (p.d) {
      const wk = weekKeyForIso(p.d);
      if (wk) s.byWeek[wk] = (s.byWeek[wk] ?? 0) + (p.v ?? 0);
      const d = new Date(p.d);
      if (!Number.isNaN(d.getTime())) {
        const key = `${d.getUTCFullYear()}-${d.getUTCMonth()}`;
        s.trend[key] = (s.trend[key] ?? 0) + (p.v ?? 0);
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

export interface TrendWeek {
  key: string;
}

/** ISO-week buckets (Monday start) covering an inclusive date range. */
export function buildTrendWeeks(startDate: string, endDate: string): TrendWeek[] {
  if (!startDate || !endDate) return [];
  const start = parseIsoDate(startDate);
  const end = parseIsoDate(endDate);
  if (start > end) return [];

  let cur = mondayOfWeek(start);
  const endMonday = mondayOfWeek(end);
  const out: TrendWeek[] = [];

  while (cur <= endMonday) {
    out.push({ key: formatIsoDate(cur) });
    const next = new Date(cur);
    next.setDate(next.getDate() + 7);
    cur = next;
  }
  return out;
}

export function computeGeoCentroid(
  points: MapPoint[],
  kind: 'states' | 'cities',
  value: string
): { lat: number; lng: number } | null {
  const matching = points.filter((p) => (kind === 'states' ? p.st === value : p.c === value));
  if (matching.length === 0) return null;
  const lat = matching.reduce((sum, p) => sum + p.lat, 0) / matching.length;
  const lng = matching.reduce((sum, p) => sum + p.lng, 0) / matching.length;
  return { lat, lng };
}

export function geoFlyZoom(kind: 'states' | 'cities'): number {
  return kind === 'states' ? 6.5 : 11;
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

/** Round reference ticks (1–2 lines) and scale ceiling for bar charts. */
export function trendChartScale(peak: number): { scaleMax: number; ticks: number[] } {
  if (peak <= 0) return { scaleMax: 1, ticks: [] };
  const scaleMax = niceCeil(peak);
  if (peak <= 3 || scaleMax <= 4) {
    return { scaleMax, ticks: [scaleMax] };
  }
  return { scaleMax, ticks: [0, scaleMax] };
}

/** Zoom level at which the map switches from density grid to individual markers. */
export const SCATTER_ZOOM_THRESHOLD = 12;

/** Points included in H3 hex aggregation — strict viewport, no nationwide fallback. */
export function pointsForHexGrid(points: MapPoint[], bounds: MapBounds | null): MapPoint[] {
  if (!bounds) return [];
  return pointsInBounds(points, bounds);
}

/** Peak fatal-victim count in any single H3 grid cell for the current viewport and zoom. */
export function computeGridPeakCount(
  points: MapPoint[],
  bounds: MapBounds | null,
  zoom: number
): number {
  const inView = bounds ? pointsForHexGrid(points, bounds) : points;
  if (inView.length === 0) return 0;
  const resolution = h3ResolutionForZoom(zoom);
  const cells = aggregatePointsToH3Cells(inView, resolution);
  return peakH3Count(cells);
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
export function distinctValues(points: MapPoint[], key: 'm' | 'p'): string[] {
  const set = new Set<string>();
  for (const p of points) {
    const v = p[key];
    if (!v) continue;
    set.add(key === 'p' ? normalizePeriodKey(v) : v);
  }
  return [...set].sort((a, b) => a.localeCompare(b));
}

export { distinctSubtypes } from '@/lib/taxonomy';
