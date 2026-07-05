/**
 * Fetch helpers hacia el backend FastAPI. Los endpoints públicos (puntos, especies,
 * sedimentación, history, alerts) se llaman directo desde Server Components.
 * Los endpoints con X-Admin-Key (ai/ask, ai/history, system-status) NUNCA se llaman
 * desde aquí en el cliente — pasan por los Route Handlers en app/api/admin/*, que
 * usan backendFetchAdmin() con la clave leída server-side.
 */

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

async function backendFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BACKEND_URL}/api/v1${path}`, { ...init, cache: "no-store" });
  if (!res.ok) throw new Error(`${path} -> HTTP ${res.status}`);
  return res.json() as Promise<T>;
}

export async function backendFetchAdmin<T>(path: string, init?: RequestInit): Promise<T> {
  const adminKey = process.env.ADMIN_API_KEY;
  if (!adminKey) throw new Error("ADMIN_API_KEY no configurada en el servidor");
  return backendFetch<T>(path, {
    ...init,
    headers: { ...init?.headers, "X-Admin-Key": adminKey },
  });
}

// ── Mapa ──────────────────────────────────────────────────────────────────────

export type Condicion = "verde" | "amarillo" | "rojo";

export interface PuntoPesca {
  id: string;
  nombre: string;
  lat: number;
  lng: number;
  especies: string[];
  observacion: string | null;
  temp: number | null;
  clorofila: number | null;
  viento: number | null;
  salinidad: number | null;
  tds: number | null;
  ipp: number;
  condicion: Condicion;
}

export interface Especie {
  id: string;
  label: string;
}

export interface ZonaSedimentacion {
  id: string;
  nombre: string;
  polygon: [number, number][];
  nivel: string;
  observacion: string | null;
}

export const getPoints = () =>
  backendFetch<{ puntos: PuntoPesca[] }>("/dashboard/points").then((r) => r.puntos);

export const getSpecies = () =>
  backendFetch<{ especies: Especie[] }>("/dashboard/species").then((r) => r.especies);

export const getSedimentation = () =>
  backendFetch<{ zonas: ZonaSedimentacion[] }>("/dashboard/sedimentation").then((r) => r.zonas);

// ── Gráficas / históricos ──────────────────────────────────────────────────────

export interface WeatherHistoryPoint {
  timestamp: string;
  temperature_c: number | null;
  wind_speed_kmh: number | null;
  precipitation_mm: number | null;
}

export interface SemaphoreHistoryPoint {
  date: string;
  color: string;
  reason: string | null;
  ipp_ranking: { zone: string; ipp: number }[] | null;
}

export interface SatelliteHistoryPoint {
  date: string;
  sst_celsius: number | null;
  chlorophyll_mgm3: number | null;
}

export interface CatchHistoryPoint {
  date: string;
  cantidad_indice: number;
}

export interface HistoryResponse {
  weather: WeatherHistoryPoint[];
  semaphore: SemaphoreHistoryPoint[];
  satellite: SatelliteHistoryPoint[];
  captura: CatchHistoryPoint[];
}

export const getHistory = (days = 30) => backendFetch<HistoryResponse>(`/data/history?days=${days}`);

// ── Alertas ────────────────────────────────────────────────────────────────────

export interface ExternalAlertItem {
  source: string | null;
  type: string | null;
  title: string | null;
  fetched_at: string;
}

export interface AlertsResponse {
  cyclones: Record<string, unknown>[];
  external: ExternalAlertItem[];
  semaphore_color: string | null;
}

export const getAlerts = () => backendFetch<AlertsResponse>("/data/alerts");

// ── Pregunta a la IA ───────────────────────────────────────────────────────────

export interface AIDato {
  v: string;
  d: string;
  fuente: string;
}

export interface AIParrafo {
  tipo: "texto" | "datos" | "limitaciones";
  titulo: string | null;
  html: string | null;
  items: AIDato[] | null;
}

export interface AskResponse {
  parrafos: AIParrafo[];
  sugerencia: string | null;
}

export interface AIHistoryItem {
  id: string;
  pregunta: string;
  respuesta: AIParrafo[];
  sugerencia: string | null;
  contexto: Record<string, unknown> | null;
  created_at: string;
}

// ── Sistema ────────────────────────────────────────────────────────────────────

export interface ApiStatus {
  id: string;
  nombre: string;
  desc: string;
  estado: "ok" | "degradado" | "caido";
  actualizado: string;
}

export interface BotMetrica {
  id: string;
  label: string;
  valor: string | number;
  sub: string;
}

export interface AlertLogEntry {
  hora: string;
  tipo: string;
  canal: string;
  zonas: string;
  texto: string;
  destinatarios?: number;
}

export interface SystemStatusResponse {
  apis: ApiStatus[];
  bot_metricas: BotMetrica[];
  log_alertas: AlertLogEntry[];
}
