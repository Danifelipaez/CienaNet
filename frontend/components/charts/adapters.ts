import type {
  WeatherHistoryPoint,
  SatelliteHistoryPoint,
  CatchHistoryPoint,
  SemaphoreHistoryPoint,
  IdeamPrecipitacionPoint,
  IdeamNivelPoint,
} from "@/lib/api";
import type { SeriesPoint, MultiSeries } from "@/components/ui/charts";

function shortDate(iso: string) {
  const d = new Date(iso);
  const mes = d.toLocaleDateString("es-CO", { month: "short" }).replace(".", "");
  return `${String(d.getDate()).padStart(2, "0")} ${mes.charAt(0).toUpperCase()}${mes.slice(1)}`;
}

export function weatherToVientoSeries(rows: WeatherHistoryPoint[]): SeriesPoint[] {
  return rows.filter((r) => r.wind_speed_kmh != null).map((r) => ({ x: shortDate(r.timestamp), v: r.wind_speed_kmh! }));
}

function avg(vals: number[]): number {
  return vals.reduce((a, b) => a + b, 0) / vals.length;
}

function vientoPorDia(rows: WeatherHistoryPoint[]): { dia: string; promedio: number }[] {
  const porDia = new Map<string, number[]>();
  for (const r of rows) {
    if (r.wind_speed_kmh == null) continue;
    const dia = r.timestamp.slice(0, 10);
    if (!porDia.has(dia)) porDia.set(dia, []);
    porDia.get(dia)!.push(r.wind_speed_kmh);
  }
  return [...porDia.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([dia, vals]) => ({ dia, promedio: avg(vals) }));
}

/** Un punto por día (promedio del día) — pensado para cubrir ~1 semana. */
export function weatherToVientoDiario(rows: WeatherHistoryPoint[]): SeriesPoint[] {
  return vientoPorDia(rows).map(({ dia, promedio }) => ({ x: shortDate(dia), v: promedio }));
}

/** Un punto por semana (promedio de los promedios diarios) — pensado para cubrir ~2 meses. */
export function weatherToVientoSemanal(rows: WeatherHistoryPoint[]): SeriesPoint[] {
  const dias = vientoPorDia(rows);
  const semanas: SeriesPoint[] = [];
  for (let i = 0; i < dias.length; i += 7) {
    const semana = dias.slice(i, i + 7);
    semanas.push({ x: shortDate(semana[0].dia), v: avg(semana.map((d) => d.promedio)) });
  }
  return semanas;
}

export function satelliteToTempSeries(rows: SatelliteHistoryPoint[]): SeriesPoint[] {
  return rows.filter((r) => r.sst_celsius != null).map((r) => ({ x: shortDate(r.date), v: r.sst_celsius! }));
}

export function satelliteToChloroSeries(rows: SatelliteHistoryPoint[]): SeriesPoint[] {
  return rows.filter((r) => r.chlorophyll_mgm3 != null).map((r) => ({ x: shortDate(r.date), v: r.chlorophyll_mgm3! }));
}

export function catchToSeries(rows: CatchHistoryPoint[]): SeriesPoint[] {
  return rows.map((r) => ({ x: shortDate(r.date), v: r.cantidad_indice }));
}

export function toCorrelacion(satellite: SatelliteHistoryPoint[], captura: CatchHistoryPoint[]) {
  const byDate = new Map(captura.map((c) => [c.date, c.cantidad_indice]));
  return satellite
    .filter((s) => s.chlorophyll_mgm3 != null && byDate.has(s.date))
    .map((s) => ({ cloro: s.chlorophyll_mgm3!, captura: byDate.get(s.date)! }));
}

const IDEAM_COLORS = ["var(--teal)", "var(--salmon)"];

function groupByEstacion<T extends { date: string; estacion: string }>(
  rows: T[],
  valueKey: keyof T
): MultiSeries[] {
  const porEstacion = new Map<string, SeriesPoint[]>();
  for (const r of rows) {
    if (!porEstacion.has(r.estacion)) porEstacion.set(r.estacion, []);
    porEstacion.get(r.estacion)!.push({ x: r.date, v: Number(r[valueKey]) });
  }
  return [...porEstacion.entries()].map(([estacion, pts], i) => ({
    label: estacion,
    color: IDEAM_COLORS[i % IDEAM_COLORS.length],
    data: pts.sort((a, b) => a.x.localeCompare(b.x)).map((p) => ({ x: shortDate(p.x), v: p.v })),
  }));
}

export function ideamPrecipitacionToSeries(rows: IdeamPrecipitacionPoint[]): MultiSeries[] {
  return groupByEstacion(rows, "precipitacion_mm");
}

export function ideamNivelToSeries(rows: IdeamNivelPoint[]): MultiSeries[] {
  return groupByEstacion(rows, "nivel_m");
}

/** Normaliza colores del backend ("green"/"yellow"/"red" o "verde"/"amarillo"/"rojo") a tono ES. */
export function normalizeTone(color: string): "verde" | "amarillo" | "rojo" {
  if (color === "red" || color === "rojo") return "rojo";
  if (color === "yellow" || color === "amarillo") return "amarillo";
  return "verde";
}

export interface EventoHistorico {
  fecha: string;
  tipo: string;
  sem: "verde" | "amarillo" | "rojo";
  variable: string;
  nota: string;
}

/** Colapsa tramos consecutivos de semáforo amarillo/rojo en eventos con rango de fechas. */
export function semaphoreToEventos(rows: SemaphoreHistoryPoint[]): EventoHistorico[] {
  const eventos: EventoHistorico[] = [];
  let i = 0;
  while (i < rows.length) {
    const tono = normalizeTone(rows[i].color);
    if (tono === "verde") {
      i++;
      continue;
    }
    let j = i;
    while (j < rows.length && normalizeTone(rows[j].color) === tono) j++;
    const start = rows[i].date,
      end = rows[j - 1].date;
    eventos.push({
      fecha: start === end ? shortDate(start) : `${shortDate(start)}–${shortDate(end)}`,
      tipo: tono === "rojo" ? "Alerta crítica" : "Precaución",
      sem: tono,
      variable: rows[i].reason ?? "",
      nota: rows[i].reason ?? "",
    });
    i = j;
  }
  return eventos.reverse().slice(0, 6);
}
