import type {
  WeatherHistoryPoint,
  SatelliteHistoryPoint,
  CatchHistoryPoint,
  SemaphoreHistoryPoint,
  IdeamPrecipitacionPoint,
  IdeamNivelPoint,
} from "@/lib/api";
import type { SeriesPoint, MultiSeries } from "@/components/ui/charts";
import { formatDate } from "./time-format";

function avg(vals: number[]): number {
  return vals.reduce((a, b) => a + b, 0) / vals.length;
}

const ESTACIONES_CLIMA = ["Tasajera", "CGSM"] as const;
const CLIMA_COLORS: Record<string, string> = { Tasajera: "var(--verde)", CGSM: "var(--teal)" };
export type VistaClima = "hora" | "dia" | "7dias";

function promedioPorDia(rows: { timestamp: string; v: number }[]): { dia: string; promedio: number }[] {
  const porDia = new Map<string, number[]>();
  for (const r of rows) {
    const dia = r.timestamp.slice(0, 10);
    if (!porDia.has(dia)) porDia.set(dia, []);
    porDia.get(dia)!.push(r.v);
  }
  return [...porDia.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([dia, vals]) => ({ dia, promedio: avg(vals) }));
}

/** Serie por estación (Tasajera/CGSM) para una variable de `weather`, en la granularidad pedida. */
function weatherMultiSeries(
  rows: WeatherHistoryPoint[],
  valueKey: "temperature_c" | "humidity_pct" | "wind_speed_kmh",
  vista: VistaClima
): MultiSeries[] {
  return ESTACIONES_CLIMA.map((estacion) => {
    const propias = rows
      .filter((r) => r.estacion === estacion && r[valueKey] != null)
      .map((r) => ({ timestamp: r.timestamp, v: r[valueKey]! }));

    let data: SeriesPoint[];
    if (vista === "hora") {
      data = propias.map((r) => ({ t: r.timestamp, v: r.v }));
    } else {
      const dias = promedioPorDia(propias);
      if (vista === "dia") {
        data = dias.map(({ dia, promedio }) => ({ t: dia, v: promedio }));
      } else {
        const semanas: SeriesPoint[] = [];
        for (let i = 0; i < dias.length; i += 7) {
          const semana = dias.slice(i, i + 7);
          semanas.push({ t: semana[0].dia, v: avg(semana.map((d) => d.promedio)) });
        }
        data = semanas;
      }
    }
    return { label: estacion, color: CLIMA_COLORS[estacion], data };
  });
}

export function weatherToVientoMulti(rows: WeatherHistoryPoint[], vista: VistaClima): MultiSeries[] {
  return weatherMultiSeries(rows, "wind_speed_kmh", vista);
}

export function weatherToTempMulti(rows: WeatherHistoryPoint[], vista: VistaClima): MultiSeries[] {
  return weatherMultiSeries(rows, "temperature_c", vista);
}

export function weatherToHumedadMulti(rows: WeatherHistoryPoint[], vista: VistaClima): MultiSeries[] {
  return weatherMultiSeries(rows, "humidity_pct", vista);
}

export function satelliteToTempSeries(rows: SatelliteHistoryPoint[]): SeriesPoint[] {
  return rows.filter((r) => r.sst_celsius != null).map((r) => ({ t: r.date, v: r.sst_celsius! }));
}

export function satelliteToChloroSeries(rows: SatelliteHistoryPoint[]): SeriesPoint[] {
  return rows.filter((r) => r.chlorophyll_mgm3 != null).map((r) => ({ t: r.date, v: r.chlorophyll_mgm3! }));
}

export function catchToSeries(rows: CatchHistoryPoint[]): SeriesPoint[] {
  return rows.map((r) => ({ t: r.date, v: r.cantidad_indice }));
}

export function toCorrelacion(satellite: SatelliteHistoryPoint[], captura: CatchHistoryPoint[]) {
  const byDate = new Map(captura.map((c) => [c.date, c.cantidad_indice]));
  return satellite
    .filter((s) => s.chlorophyll_mgm3 != null && byDate.has(s.date))
    .map((s) => ({ cloro: s.chlorophyll_mgm3!, captura: byDate.get(s.date)!, date: s.date }));
}

const IDEAM_COLORS = ["var(--teal)", "var(--salmon)"];

function groupByEstacion<T extends { date: string; estacion: string }>(
  rows: T[],
  valueKey: keyof T
): MultiSeries[] {
  const porEstacion = new Map<string, SeriesPoint[]>();
  for (const r of rows) {
    if (!porEstacion.has(r.estacion)) porEstacion.set(r.estacion, []);
    porEstacion.get(r.estacion)!.push({ t: r.date, v: Number(r[valueKey]) });
  }
  return [...porEstacion.entries()].map(([estacion, pts], i) => ({
    label: estacion,
    color: IDEAM_COLORS[i % IDEAM_COLORS.length],
    data: pts.sort((a, b) => a.t.localeCompare(b.t)),
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
      fecha: start === end ? formatDate(start) : `${formatDate(start)}–${formatDate(end)}`,
      tipo: tono === "rojo" ? "Alerta crítica" : "Precaución",
      sem: tono,
      variable: rows[i].reason ?? "",
      nota: rows[i].reason ?? "",
    });
    i = j;
  }
  return eventos.reverse().slice(0, 6);
}
