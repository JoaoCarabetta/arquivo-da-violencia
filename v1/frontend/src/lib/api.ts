// API Client for the backend
const API_BASE = '/api';

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
  status: 'pending' | 'downloaded' | 'processed' | 'failed' | 'ignored';
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
async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`API Error: ${response.status} ${response.statusText}`);
  }
  return response.json();
}

async function postJson<T>(url: string, body?: unknown): Promise<T> {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    throw new Error(`API Error: ${response.status} ${response.statusText}`);
  }
  return response.json();
}

// Sources API
export async function fetchSources(page = 1, perPage = 20, status?: string) {
  const params = new URLSearchParams({ page: String(page), per_page: String(perPage) });
  if (status) params.set('status', status);
  return fetchJson<PaginatedResponse<SourceGoogleNews>>(`${API_BASE}/sources?${params}`);
}

export async function fetchSourceById(sourceId: number) {
  return fetchJson<SourceGoogleNews>(`${API_BASE}/sources/${sourceId}`);
}

export interface SourcesByHour {
  data: Array<{ hour: string; count: number }>;
  hours: number;
}

export async function fetchSourcesByHour(hours = 24) {
  const params = new URLSearchParams({ hours: String(hours) });
  return fetchJson<SourcesByHour>(`${API_BASE}/sources/stats/by-hour?${params}`);
}

// Raw Events API
export async function fetchRawEvents(page = 1, perPage = 20) {
  const params = new URLSearchParams({ page: String(page), per_page: String(perPage) });
  return fetchJson<PaginatedResponse<RawEvent>>(`${API_BASE}/raw-events?${params}`);
}

// Unique Events API
export async function fetchUniqueEvents(page = 1, perPage = 20) {
  const params = new URLSearchParams({ page: String(page), per_page: String(perPage) });
  return fetchJson<PaginatedResponse<UniqueEvent>>(`${API_BASE}/unique-events?${params}`);
}

// Pipeline API
export async function triggerIngest(query?: string, when = '3d') {
  const params = new URLSearchParams();
  if (query) params.set('query', query);
  params.set('when', when);
  return postJson<{ job_id: string; status: string; task: string }>(`${API_BASE}/pipeline/ingest?${params}`);
}

export async function triggerDownload(limit = 50) {
  return postJson<{ job_id: string; status: string; task: string }>(`${API_BASE}/pipeline/download?limit=${limit}`);
}

export async function triggerExtract(limit = 10) {
  return postJson<{ job_id: string; status: string; task: string }>(`${API_BASE}/pipeline/extract?limit=${limit}`);
}

export async function triggerEnrich(rawEventId: number) {
  return postJson<{ job_id: string; status: string; task: string }>(`${API_BASE}/pipeline/enrich/${rawEventId}`);
}

export interface PipelineStatus {
  redis: 'connected' | 'disconnected';
  queued_jobs: number;
  jobs: Job[];
  error?: string;
}

export async function fetchPipelineStatus() {
  return fetchJson<PipelineStatus>(`${API_BASE}/pipeline/status`);
}

export async function fetchJobStatus(jobId: string) {
  return fetchJson<JobStatus>(`${API_BASE}/pipeline/jobs/${jobId}`);
}

// Stats API
export interface Stats {
  sources: { total: number; pending: number; downloaded: number; processed: number; failed: number };
  raw_events: { total: number };
  unique_events: { total: number };
}

export async function fetchStats() {
  return fetchJson<Stats>(`${API_BASE}/stats`);
}

