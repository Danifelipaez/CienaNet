import type { WeatherHistoryPoint, SatelliteHistoryPoint, CatchHistoryPoint, SemaphoreHistoryPoint } from "@/lib/api";
import type { SeriesPoint } from "@/components/ui/charts";

function shortDate(iso: string) {
  const d = new Date(iso);
  const mes = d.toLocaleDateString("es-CO", { month: "short" }).replace(".", "");
  return `${String(d.getDate()).padStart(2, "0")} ${mes.charAt(0).toUpperCase()}${mes.slice(1)}`;
}

export function weatherToVientoSeries(rows: WeatherHistoryPoint[]): SeriesPoint[] {
  return rows.filter((r) => r.wind_speed_kmh != null).map((r) => ({ x: shortDate(r.timestamp), v: r.wind_speed_kmh! }));
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
