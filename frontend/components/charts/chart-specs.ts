import type { HistoryResponse } from "@/lib/api";
import type { MultiSeries } from "@/components/ui/charts";
import type { ChartGranularity } from "./time-format";
import {
  type VistaClima,
  weatherToVientoMulti,
  weatherToTempMulti,
  weatherToHumedadMulti,
  satelliteToTempSeries,
  satelliteToChloroSeries,
  ideamPrecipitacionToSeries,
  ideamNivelToSeries,
} from "./adapters";

export interface ChartSpec {
  id: string;
  title: string;
  source: string;
  unit: string;
  span: 6 | 12;
  motif?: "raya" | "mangle" | "cana" | "lirio";
  granularity: ChartGranularity;
  aggregated?: boolean;
  usesVista?: boolean;
  showVistaToggle?: boolean;
  yMin?: number;
  yMax?: number;
  area?: boolean;
  annotate?: (series: MultiSeries[]) => { seriesIndex: number; pointIndex: number; label: string }[];
  getSeries: (history: HistoryResponse, vista: VistaClima) => MultiSeries[];
}

/** Mapea la vista horaria (hora/día/7días) a granularidad + si el punto es un promedio agregado. */
export function vistaToGranularity(vista: VistaClima): { granularity: ChartGranularity; aggregated: boolean } {
  if (vista === "hora") return { granularity: "hour", aggregated: false };
  if (vista === "dia") return { granularity: "day", aggregated: true };
  return { granularity: "week", aggregated: true };
}

function singleSeries(label: string, color: string, data: MultiSeries["data"]): MultiSeries[] {
  return [{ label, color, data }];
}

function peakAnnotation(series: MultiSeries[]) {
  const data = series[0]?.data ?? [];
  if (!data.length) return [];
  const peakIdx = data.reduce((mi, d, i, arr) => (d.v > arr[mi].v ? i : mi), 0);
  return [{ seriesIndex: 0, pointIndex: peakIdx, label: "Pico" }];
}

export const CHART_SPECS: ChartSpec[] = [
  {
    id: "viento",
    title: "Velocidad del viento",
    source: "Open-Meteo — Tasajera / CGSM",
    unit: "km/h",
    span: 12,
    motif: "cana",
    granularity: "hour",
    usesVista: true,
    showVistaToggle: true,
    yMin: 0,
    area: true,
    getSeries: (history, vista) => weatherToVientoMulti(history.weather, vista),
  },
  {
    id: "temp-ambiental",
    title: "Temperatura ambiental",
    source: "Open-Meteo — Tasajera / CGSM",
    unit: "°C",
    span: 6,
    motif: "lirio",
    granularity: "hour",
    usesVista: true,
    getSeries: (history, vista) => weatherToTempMulti(history.weather, vista),
  },
  {
    id: "humedad",
    title: "Humedad relativa",
    source: "Open-Meteo — Tasajera / CGSM",
    unit: "%",
    span: 6,
    motif: "mangle",
    granularity: "hour",
    usesVista: true,
    yMin: 0,
    getSeries: (history, vista) => weatherToHumedadMulti(history.weather, vista),
  },
  {
    id: "temp-superficial",
    title: "Temp. superficial del agua",
    source: "NASA MODIS",
    unit: "°C",
    span: 6,
    motif: "lirio",
    granularity: "day",
    aggregated: false,
    area: true,
    getSeries: (history) => singleSeries("Temp. superficial", "var(--teal)", satelliteToTempSeries(history.satellite)),
  },
  {
    id: "clorofila",
    title: "Clorofila-a",
    source: "Copernicus Marine",
    unit: "mg/m³",
    span: 6,
    motif: "mangle",
    granularity: "day",
    aggregated: false,
    yMin: 0,
    area: true,
    annotate: peakAnnotation,
    getSeries: (history) => singleSeries("Clorofila-a", "var(--verde-sem)", satelliteToChloroSeries(history.satellite)),
  },
  {
    id: "precipitacion",
    title: "Precipitación en la cuenca",
    source: "IDEAM — Media Luna / La Gran Vía",
    unit: "mm/día",
    span: 6,
    motif: "raya",
    granularity: "day",
    aggregated: false,
    yMin: 0,
    area: true,
    getSeries: (history) => ideamPrecipitacionToSeries(history.ideam_precipitacion),
  },
  {
    id: "nivel-rio",
    title: "Nivel de ríos tributarios",
    source: "IDEAM — Puerto Rico Hacienda / Ganadería Caribe",
    unit: "metros",
    span: 6,
    motif: "mangle",
    granularity: "day",
    aggregated: false,
    yMin: 0,
    getSeries: (history) => ideamNivelToSeries(history.ideam_nivel_rio),
  },
];
