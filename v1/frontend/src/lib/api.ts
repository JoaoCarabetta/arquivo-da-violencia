// API Client for the backend
const API_BASE = '/api';

// Helper to get auth token from sessionStorage
function getAuthToken(): string | null {
  return sessionStorage.getItem('admin_token');
}

// Helper to create headers with auth token
function getAuthHeaders(): HeadersInit {
  const token = getAuthToken();
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
  };
  
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  
  return headers;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

export interface SourceGoogleNews {
  id: number;
  google_news_id: string;
  google_news_url: string;
  resolved_url: string | null;
  headline: string | null;
  publisher_name: string | null;
  publisher_url: string | null;
  content: string | null;
  source_type: string | null;
  published_at: string | null;
  search_query: string | null;
  status: 'ready_for_classification' | 'discarded' | 'ready_for_download' | 'failed_in_download' | 'ready_for_extraction' | 'failed_in_extraction' | 'extracted';
  is_violent_death: boolean | null;
  classification_confidence: string | null;
  classification_reasoning: string | null;
  fetched_at: string;
  updated_at: string;
}

export interface RawEvent {
  id: number;
  source_google_news_id: number | null;
  unique_event_id: number | null;
  homicide_type: string | null;
  method_of_death: string | null;
  event_date: string | null;
  date_precision: string | null;
  time_of_day: string | null;
  city: string | null;
  state: string | null;
  neighborhood: string | null;
  victim_count: number | null;
  identified_victim_count: number | null;
  perpetrator_count: number | null;
  identified_perpetrator_count: number | null;
  security_force_involved: boolean | null;
  title: string | null;
  chronological_description: string | null;
  extraction_data: Record<string, unknown>;
  extraction_model: string | null;
  extraction_success: boolean;
  extraction_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface UniqueEvent {
  id: number;
  homicide_type: string | null;
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
  merged_data: Record<string, unknown>;
  source_count: number;
  confirmed: boolean;
  created_at: string;
  updated_at: string;
}

export interface Job {
  job_id: string;
  function: string;
  args: unknown[];
  kwargs: Record<string, unknown>;
  enqueue_time: string;
  score: number;
}

export interface JobStatus {
  status: string;
  result?: unknown;
  error?: string;
}

// Fetch functions
async function fetchJson<T>(url: string, requiresAuth = false): Promise<T> {
  const headers = requiresAuth ? getAuthHeaders() : {};
  const response = await fetch(url, { headers });
  if (!response.ok) {
    throw new Error(`API Error: ${response.status} ${response.statusText}`);
  }
  return response.json();
}

async function postJson<T>(url: string, body?: unknown, requiresAuth = false): Promise<T> {
  const headers = requiresAuth ? getAuthHeaders() : { 'Content-Type': 'application/json' };
  const response = await fetch(url, {
    method: 'POST',
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    throw new Error(`API Error: ${response.status} ${response.statusText}`);
  }
  return response.json();
}

// Sources API (requires auth)
export async function fetchSources(page = 1, perPage = 20, status?: string) {
  const params = new URLSearchParams({ page: String(page), per_page: String(perPage) });
  if (status) params.set('status', status);
  return fetchJson<PaginatedResponse<SourceGoogleNews>>(`${API_BASE}/sources?${params}`, true);
}

export async function fetchSourceById(sourceId: number) {
  return fetchJson<SourceGoogleNews>(`${API_BASE}/sources/${sourceId}`, true);
}

export interface SourcesByHour {
  data: Array<{ 
    hour: string; 
    count: number;
    ready_for_classification?: number;
    discarded?: number;
    ready_for_download?: number;
    failed_in_download?: number;
    ready_for_extraction?: number;
    failed_in_extraction?: number;
    extracted?: number;
  }>;
  hours: number;
}

export async function fetchSourcesByHour(hours = 24) {
  const params = new URLSearchParams({ hours: String(hours) });
  return fetchJson<SourcesByHour>(`${API_BASE}/sources/stats/by-hour?${params}`);
}

// Raw Events API (requires auth)
export async function fetchRawEvents(page = 1, perPage = 20) {
  const params = new URLSearchParams({ page: String(page), per_page: String(perPage) });
  return fetchJson<PaginatedResponse<RawEvent>>(`${API_BASE}/raw-events?${params}`, true);
}

// Unique Events API (requires auth)
export async function fetchUniqueEvents(page = 1, perPage = 20) {
  const params = new URLSearchParams({ page: String(page), per_page: String(perPage) });
  return fetchJson<PaginatedResponse<UniqueEvent>>(`${API_BASE}/unique-events?${params}`, true);
}

// Pipeline API (requires auth)
export async function triggerIngest(query?: string, when = '3d') {
  const params = new URLSearchParams();
  if (query) params.set('query', query);
  params.set('when', when);
  return postJson<{ job_id: string; status: string; task: string }>(`${API_BASE}/pipeline/ingest?${params}`, undefined, true);
}

export async function triggerDownload(limit = 50) {
  return postJson<{ job_id: string; status: string; task: string }>(`${API_BASE}/pipeline/download?limit=${limit}`, undefined, true);
}

export async function triggerExtract(limit = 10) {
  return postJson<{ job_id: string; status: string; task: string }>(`${API_BASE}/pipeline/extract?limit=${limit}`, undefined, true);
}

export async function triggerEnrich(rawEventId: number) {
  return postJson<{ job_id: string; status: string; task: string }>(`${API_BASE}/pipeline/enrich/${rawEventId}`, undefined, true);
}

export interface PipelineStatus {
  redis: 'connected' | 'disconnected';
  queued_jobs: number;
  jobs: Job[];
  error?: string;
}

export async function fetchPipelineStatus() {
  return fetchJson<PipelineStatus>(`${API_BASE}/pipeline/status`, true);
}

export async function fetchJobStatus(jobId: string) {
  return fetchJson<JobStatus>(`${API_BASE}/pipeline/jobs/${jobId}`, true);
}

// Stats API (requires auth)
export interface Stats {
  sources: {
    total: number;
    ready_for_classification: number;
    discarded: number;
    ready_for_download: number;
    ready_for_extraction: number;
    extracted: number;
    failed_in_download: number;
    failed_in_extraction: number;
  };
  classification: {
    violent_death: number;
    not_violent_death: number;
  };
  raw_events: { total: number };
  unique_events: { total: number };
}

export async function fetchStats() {
  return fetchJson<Stats>(`${API_BASE}/stats`, true);
}

// Public API
export interface PublicStats {
  total: number;
  today: number;
  this_week: number;
  this_month: number;
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

export interface SecurityForceStat {
  involved: number;
  not_involved: number;
  unknown: number;
}

export interface PublicEvent {
  id: number;
  event_date: string | null;
  time_of_day: string | null;
  state: string | null;
  city: string | null;
  neighborhood: string | null;
  homicide_type: string | null;
  method_of_death: string | null;
  victim_count: number | null;
  security_force_involved: boolean | null;
  title: string | null;
  chronological_description: string | null;
  latitude: number | null;
  longitude: number | null;
  source_count: number;
  created_at: string;
}

export async function fetchPublicStats() {
  return fetchJson<PublicStats>(`${API_BASE}/public/stats`);
}

export async function fetchStatsByType() {
  return fetchJson<TypeStat[]>(`${API_BASE}/public/stats/by-type`);
}

export async function fetchStatsByState() {
  return fetchJson<StateStat[]>(`${API_BASE}/public/stats/by-state`);
}

export async function fetchStatsByDay(days = 30) {
  return fetchJson<DayStat[]>(`${API_BASE}/public/stats/by-day?days=${days}`);
}

export async function fetchSecurityForceStats() {
  return fetchJson<SecurityForceStat>(`${API_BASE}/public/stats/security-force`);
}

export async function fetchPublicEvents(page = 1, perPage = 20, filters?: {
  state?: string;
  type?: string;
  search?: string;
}) {
  const params = new URLSearchParams({ page: String(page), per_page: String(perPage) });
  if (filters?.state) params.set('state', filters.state);
  if (filters?.type) params.set('type', filters.type);
  if (filters?.search) params.set('search', filters.search);
  return fetchJson<PaginatedResponse<PublicEvent>>(`${API_BASE}/public/events?${params}`);
}

export function getExportUrl(format: 'csv' | 'json', filters?: {
  state?: string;
  type?: string;
}) {
  const params = new URLSearchParams({ format });
  if (filters?.state) params.set('state', filters.state);
  if (filters?.type) params.set('type', filters.type);
  return `${API_BASE}/public/events/export?${params}`;
}

