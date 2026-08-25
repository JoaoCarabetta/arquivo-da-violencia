/**
 * API client for the Arquivo da Violência backend
 */

import {
  MOCK_PORTAL_ENABLED,
  mockMapPoints,
  mockPublicEventById,
} from '@/dev/mockPortalData';

const API_BASE = '/api';

// =============================================================================
// Types
// =============================================================================

export interface Job {
  job_id: string;
  function: string;
  enqueue_time: string | null;
  status?: string;
}

export interface PipelineStatus {
  redis: string;
  worker_alive?: boolean;
  worker_health?: string | null;
  worker_started_at?: string | null;
  cron_enabled?: boolean;
  queued_jobs: number;
  jobs: Job[];
  error?: string;
}

export interface Stats {
  sources: {
    total: number;
    ready_for_classification: number;
    discarded: number;
    ready_for_download: number;
    failed_in_download: number;
    ready_for_extraction: number;
    failed_in_extraction: number;
    extracted: number;
  };
  classification: {
    violent_death: number;
  };
  raw_events: {
    total: number;
  };
  unique_events: {
    total: number;
  };
}

export interface SourceGoogleNews {
  id: number;
  google_news_url: string | null;
  resolved_url: string | null;
  headline: string | null;
  publisher_name: string | null;
  published_at: string | null;
  fetched_at: string | null;
  updated_at: string | null;
  status: string;
  search_query: string | null;
  content: string | null;
  classification_result: string | null;
  is_violent_death: boolean | null;
}

export interface RawEvent {
  id: number;
  source_google_news_id: number | null;
  unique_event_id: number | null;
  title: string | null;
  event_date: string | null;
  date_precision: string | null;
  time_of_day: string | null;
  state: string | null;
  city: string | null;
  neighborhood: string | null;
  homicide_type: string | null;
  event_family: string | null;
  event_subtype: string | null;
  method_of_death: string | null;
  victim_count: number | null;
  identified_victim_count: number | null;
  perpetrator_count: number | null;
  security_force_involved: boolean | null;
  chronological_description: string | null;
  extraction_data: Record<string, unknown> | null;
  extraction_success: boolean;
  extraction_error: string | null;
  extraction_model: string | null;
  deduplication_status: string | null;
  is_gold_standard: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface UniqueEvent {
  id: number;
  homicide_type: string | null;
  event_family: string | null;
  event_subtype: string | null;
  method_of_death: string | null;
  event_date: string | null;
  date_precision: string | null;
  time_of_day: string | null;
  country: string | null;
  state: string | null;
  city: string | null;
  neighborhood: string | null;
  street: string | null;
  establishment: string | null;
  full_location_description: string | null;
  latitude: number | null;
  longitude: number | null;
  plus_code: string | null;
  place_id: string | null;
  formatted_address: string | null;
  location_precision: string | null;
  geocoding_source: string | null;
  geocoding_confidence: number | null;
  victim_count: number | null;
  identified_victim_count: number | null;
  victims_summary: string | null;
  perpetrator_count: number | null;
  identified_perpetrator_count: number | null;
  security_force_involved: boolean | null;
  title: string | null;
  chronological_description: string | null;
  additional_context: string | null;
  merged_data: Record<string, unknown> | null;
  source_count: number;
  confirmed: boolean;
  needs_enrichment: boolean;
  last_enriched_at: string | null;
  enrichment_model: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface EventSource {
  id: number;
  headline: string | null;
  publisher_name: string | null;
  url: string | null;
  google_news_url?: string | null;
  published_at: string | null;
  kind?: 'source' | 'raw_fallback';
}

export interface PublicEvent {
  id: number;
  title: string | null;
  event_date: string | null;
  time_of_day: string | null;
  country?: string | null;
  state: string | null;
  city: string | null;
  neighborhood: string | null;
  street?: string | null;
  homicide_type: string | null;
  event_family: string | null;
  event_subtype: string | null;
  method_of_death: string | null;
  victim_count: number | null;
  victims_summary: string | null;
  perpetrator_count?: number | null;
  security_force_involved: boolean | null;
  criminal_group_connected?: boolean | null;
  criminal_groups?: string | null;
  criminal_group_activity?: string | null;
  criminal_group_activity_description?: string | null;
  criminal_group_attacked?: string | null;
  police_operation_connected?: boolean | null;
  police_operation_force?: string | null;
  police_operation_targeted_armed_groups?: boolean | null;
  off_duty_police_perpetrator?: boolean | null;
  off_duty_police_context?: string | null;
  politician_or_candidate_victim?: boolean | null;
  victim_political_status?: string | null;
  victim_political_office?: string | null;
  victim_political_party?: string | null;
  merged_data?: Record<string, unknown> | null;
  chronological_description: string | null;
  latitude: number | null;
  longitude: number | null;
  location_precision?: string | null;
  formatted_address: string | null;
  source_count: number;
  created_at: string;
  updated_at?: string | null;
  sources?: EventSource[];
}

export interface PublicStats {
  total: number;
  last_7_days: number;
  last_30_days: number;
  since: string;
}

export interface TypeStat {
  type: string;
  count: number;
  percent: number;
}

export interface StateStat {
  state: string;
  count: number;
}

export interface DayStat {
  date: string;
  count: number;
}

export interface GeocodeResult {
  latitude: number;
  longitude: number;
  label: string;
  source: string;
  query: string;
  zoom?: number;
}

export interface NearbyEvent {
  id: number;
  distance_km: number;
  event_date: string | null;
  state: string | null;
  city: string | null;
  neighborhood: string | null;
  homicide_type: string | null;
  event_family: string | null;
  event_subtype: string | null;
  method_of_death: string | null;
  victim_count: number | null;
  victims_summary: string | null;
  security_force_involved: boolean | null;
  title: string | null;
  latitude: number;
  longitude: number;
  location_precision: string | null;
  source_count: number;
}

export interface BreakdownItem {
  label: string;
  count: number;
  percent: number;
}

export interface MapPoint {
  id: number;
  lat: number;
  lng: number;
  /** event_family */
  f?: string | null;
  /** event_subtype */
  su?: string | null;
  /** legacy homicide_type label */
  t: string | null;
  m: string | null;
  d: string | null;
  v: number | null;
  s: boolean | null;
  /** security_force_victim — any victim flagged is_security_force */
  sv?: boolean | null;
  /** country code (BR, CL) */
  co?: string | null;
  c: string | null;
  n: string | null;
  st: string | null;
  p: string | null;
}

export interface MapPointsResponse {
  count: number;
  points: MapPoint[];
}

export interface NearbyResponse {
  center: { lat: number; lng: number };
  radius_km: number;
  days: number | null;
  summary: {
    total: number;
    total_victims: number;
    previous_period_total: number | null;
    trend_pct: number | null;
    security_force_involved: number;
    by_type: BreakdownItem[];
    by_method: BreakdownItem[];
  };
  events: NearbyEvent[];
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

export interface RankingRow {
  city?: string;
  state?: string;
  state_abbrev?: string | null;
  country?: string;
  type?: string;
  method?: string;
  victim_count: number;
  event_count: number;
  victim_share: number;
  event_share: number;
  victim_delta: number;
  event_delta: number;
  population?: number | null;
  rate_per_100k?: number | null;
}

export interface RankingsResponse {
  period_days: number;
  period_start: string;
  period_end: string;
  country_filter: string | null;
  total_victims: number;
  total_events: number;
  cities: RankingRow[];
  states: RankingRow[];
  countries: RankingRow[];
  homicide_types: RankingRow[];
  methods: RankingRow[];
  population_vintage?: number;
}

export interface MatrixCell {
  month: string;
  victims: number;
  rate_per_100k?: number;
}

export interface MatrixUF {
  abbrev: string;
  name: string;
  population: number;
  cells: MatrixCell[];
}

export interface MatrixType {
  type: string;
  cells: MatrixCell[];
}

export interface MatrixResponse {
  months: string[];
  ufs: MatrixUF[];
  types: MatrixType[];
}

export interface SourcesByHourData {
  hour: string;
  count: number;
  ready_for_classification: number;
  discarded: number;
  ready_for_download: number;
  failed_in_download: number;
  ready_for_extraction: number;
  failed_in_extraction: number;
  extracted: number;
}

export interface SourcesByHourResponse {
  data: SourcesByHourData[];
  hours: number;
}

// =============================================================================
// API Functions
// =============================================================================

async function fetchJson<T>(url: string, options: RequestInit = {}): Promise<T> {
  // Get token from localStorage
  const token = localStorage.getItem('admin_token');
  
  // Add Authorization header if token exists
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };
  
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  
  const response = await fetch(url, {
    ...options,
    headers,
  });
  
  // Handle 401 Unauthorized - token is invalid or expired
  if (response.status === 401) {
    // Clear invalid token
    localStorage.removeItem('admin_token');
    // Trigger custom event to notify AuthContext (for same-tab communication)
    window.dispatchEvent(new CustomEvent('auth-token-cleared'));
    // Redirect to login if we're in an admin route
    if (window.location.pathname.startsWith('/admin') && !window.location.pathname.includes('/login')) {
      window.location.href = '/admin/login';
    }
    throw new Error('Authentication failed. Please log in again.');
  }
  
  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`);
  }
  return response.json();
}

// Pipeline & Jobs
export async function fetchPipelineStatus(): Promise<PipelineStatus> {
  return fetchJson<PipelineStatus>(`${API_BASE}/pipeline/status`);
}

// Admin Stats
export async function fetchStats(): Promise<Stats> {
  return fetchJson<Stats>(`${API_BASE}/stats`);
}

// Sources
export async function fetchSources(
  page: number = 1,
  perPage: number = 20
): Promise<PaginatedResponse<SourceGoogleNews>> {
  return fetchJson(`${API_BASE}/sources?page=${page}&per_page=${perPage}`);
}

export async function fetchSourceById(id: number): Promise<SourceGoogleNews> {
  return fetchJson<SourceGoogleNews>(`${API_BASE}/sources/${id}`);
}

export async function fetchSourcesByHour(hours: number = 48): Promise<SourcesByHourResponse> {
  return fetchJson<SourcesByHourResponse>(`${API_BASE}/sources/stats/by-hour?hours=${hours}`);
}

// Raw Events
export async function fetchRawEvents(
  page: number = 1,
  perPage: number = 20
): Promise<PaginatedResponse<RawEvent>> {
  return fetchJson(`${API_BASE}/raw-events?page=${page}&per_page=${perPage}`);
}

export async function fetchRawEventById(id: number): Promise<RawEvent> {
  return fetchJson<RawEvent>(`${API_BASE}/raw-events/${id}`);
}

export async function updateRawEvent(
  id: number,
  data: {
    extraction_data?: Record<string, unknown>;
    is_gold_standard?: boolean;
  }
): Promise<RawEvent> {
  return fetchJson<RawEvent>(`${API_BASE}/raw-events/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

// Unique Events
export async function fetchUniqueEvents(
  page: number = 1,
  perPage: number = 20
): Promise<PaginatedResponse<UniqueEvent>> {
  return fetchJson(`${API_BASE}/unique-events?page=${page}&per_page=${perPage}`);
}

// Public API
export async function fetchPublicStats(): Promise<PublicStats> {
  return fetchJson<PublicStats>(`${API_BASE}/public/stats`);
}

export async function fetchStatsByType(): Promise<TypeStat[]> {
  return fetchJson<TypeStat[]>(`${API_BASE}/public/stats/by-type`);
}

export async function fetchStatsByState(): Promise<StateStat[]> {
  return fetchJson<StateStat[]>(`${API_BASE}/public/stats/by-state`);
}

export async function fetchStatsByDay(days: number = 30): Promise<DayStat[]> {
  return fetchJson<DayStat[]>(`${API_BASE}/public/stats/by-day?days=${days}`);
}

export async function fetchPublicEvents(
  page: number = 1,
  perPage: number = 20,
  filters?: {
    search?: string;
    state?: string;
    type?: string;
    city?: string;
    dateFrom?: string;
    dateTo?: string;
  }
): Promise<PaginatedResponse<PublicEvent>> {
  const params = new URLSearchParams();
  params.set('page', page.toString());
  params.set('per_page', perPage.toString());
  
  if (filters?.search) params.set('search', filters.search);
  if (filters?.state) params.set('state', filters.state);
  if (filters?.type) params.set('homicide_type', filters.type);
  if (filters?.city) params.set('city', filters.city);
  if (filters?.dateFrom) params.set('date_from', filters.dateFrom);
  if (filters?.dateTo) params.set('date_to', filters.dateTo);
  
  return fetchJson(`${API_BASE}/public/events?${params.toString()}`);
}

export async function fetchPublicEventById(id: number): Promise<PublicEvent> {
  if (MOCK_PORTAL_ENABLED) {
    const event = mockPublicEventById(id);
    if (!event) throw new Error('Event not found');
    return event;
  }
  return fetchJson<PublicEvent>(`${API_BASE}/public/events/${id}`);
}

// Location / proximity
export async function geocode(input: { q?: string; cep?: string }): Promise<GeocodeResult> {
  const params = new URLSearchParams();
  if (input.cep) params.set('cep', input.cep);
  if (input.q) params.set('q', input.q);
  return fetchJson<GeocodeResult>(`${API_BASE}/public/geocode?${params.toString()}`);
}

export async function fetchNearby(params: {
  lat: number;
  lng: number;
  radiusKm?: number;
  days?: number;
  limit?: number;
}): Promise<NearbyResponse> {
  const qs = new URLSearchParams();
  qs.set('lat', params.lat.toString());
  qs.set('lng', params.lng.toString());
  if (params.radiusKm != null) qs.set('radius_km', params.radiusKm.toString());
  if (params.days != null) qs.set('days', params.days.toString());
  if (params.limit != null) qs.set('limit', params.limit.toString());
  return fetchJson<NearbyResponse>(`${API_BASE}/public/nearby?${qs.toString()}`);
}

export async function fetchMapPoints(filters?: {
  days?: number;
  type?: string;
  country?: string;
  minLng?: number;
  minLat?: number;
  maxLng?: number;
  maxLat?: number;
}): Promise<MapPointsResponse> {
  if (MOCK_PORTAL_ENABLED) {
    return Promise.resolve(mockMapPoints());
  }
  const qs = new URLSearchParams();
  if (filters?.days != null) qs.set('days', filters.days.toString());
  if (filters?.type) qs.set('type', filters.type);
  if (filters?.country) qs.set('country', filters.country);
  if (filters?.minLng != null) qs.set('min_lng', filters.minLng.toString());
  if (filters?.minLat != null) qs.set('min_lat', filters.minLat.toString());
  if (filters?.maxLng != null) qs.set('max_lng', filters.maxLng.toString());
  if (filters?.maxLat != null) qs.set('max_lat', filters.maxLat.toString());
  const suffix = qs.toString() ? `?${qs.toString()}` : '';
  return fetchJson<MapPointsResponse>(`${API_BASE}/public/map-points${suffix}`);
}

export async function fetchRankings(params?: {
  days?: number;
  country?: string;
  cityLimit?: number;
}): Promise<RankingsResponse> {
  const qs = new URLSearchParams();
  if (params?.days != null) qs.set('days', params.days.toString());
  if (params?.country) qs.set('country', params.country);
  if (params?.cityLimit != null) qs.set('city_limit', params.cityLimit.toString());
  const suffix = qs.toString() ? `?${qs.toString()}` : '';
  return fetchJson<RankingsResponse>(`${API_BASE}/public/stats/rankings${suffix}`);
}

export async function fetchStatsMatrix(): Promise<MatrixResponse> {
  return fetchJson<MatrixResponse>(`${API_BASE}/public/stats/matrix`);
}

export interface CoverageMunicipality {
  code: number;
  name: string;
  uf: string;
  official_victims: number;
  official_published: boolean;
  arquivo_victims: number;
  coverage: number | null;
}

export interface CoverageResponse {
  window_start: string;
  methodology: {
    official_bag: string;
    arquivo_filter: string;
    coverage_calculation: string;
  };
  municipalities: CoverageMunicipality[];
}

export async function fetchCoverageStats(): Promise<CoverageResponse> {
  return fetchJson<CoverageResponse>(`${API_BASE}/public/stats/coverage`);
}

// Export URLs
export interface ExportFilters {
  types?: string[];
  methods?: string[];
  periods?: string[];
  states?: string[];
  cities?: string[];
  country?: string;
  days?: number;
  columns?: string[];
  startDate?: string;
  endDate?: string;
}

export function getExportUrl(filters?: ExportFilters): string {
  const qs = new URLSearchParams();
  qs.set('format', 'csv');
  if (filters?.startDate || filters?.endDate) {
    if (filters.startDate) qs.set('start_date', filters.startDate);
    if (filters.endDate) qs.set('end_date', filters.endDate);
  } else {
    qs.set('days', String(filters?.days ?? 365));
  }
  if (filters?.country) qs.set('country', filters.country);
  for (const t of filters?.types ?? []) qs.append('types', t);
  for (const m of filters?.methods ?? []) qs.append('methods', m);
  for (const p of filters?.periods ?? []) qs.append('periods', p);
  for (const st of filters?.states ?? []) qs.append('states', st);
  for (const c of filters?.cities ?? []) qs.append('cities', c);
  for (const c of filters?.columns ?? []) qs.append('columns', c);
  return `${API_BASE}/public/events/export?${qs.toString()}`;
}

