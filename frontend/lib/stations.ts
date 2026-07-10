import type { HistoryResponse } from "@/lib/api";

export interface EstacionSnapshot {
  id: string;
  nombre: string;
  lat: number;
  lng: number;
  tempAmbiental: number | null;
  humedad: number | null;
  viento: number | null;
  precipitacion: number | null;
  nivelRio: number | null;
}

// ponytail: coordenadas ilustrativas (sin lat/lng en backend para IDEAM, ver
// app/services/ingestion/ideam_hidro.py) — mismo criterio que tasajera_lat/lon
// en app/core/config.py. CGSM y Tasajera sí tienen coordenadas reales de config.
const COORDS: Record<string, [number, number]> = {
  CGSM: [10.859056, -74.460611],
  Tasajera: [10.972, -74.434],
  "Media Luna": [10.95, -74.28],
  "La Gran Vía": [10.8, -74.25],
  "Puerto Rico Hacienda": [10.65, -74.35],
  "Ganadería Caribe": [10.55, -74.3],
};

function latest<T extends { estacion: string }>(rows: T[]): Map<string, T> {
  const m = new Map<string, T>();
  for (const r of rows) m.set(r.estacion, r); // asume orden ascendente por fecha
  return m;
}

export function historyToEstaciones(history: HistoryResponse): EstacionSnapshot[] {
  const weather = latest(history.weather);
  const precip = latest(history.ideam_precipitacion);
  const nivel = latest(history.ideam_nivel_rio);

  const nombres = new Set([...weather.keys(), ...precip.keys(), ...nivel.keys()]);

  return [...nombres]
    .filter((n) => COORDS[n])
    .map((nombre) => {
      const [lat, lng] = COORDS[nombre];
      const w = weather.get(nombre);
      return {
        id: nombre,
        nombre,
        lat,
        lng,
        tempAmbiental: w?.temperature_c ?? null,
        humedad: w?.humidity_pct ?? null,
        viento: w?.wind_speed_kmh ?? null,
        precipitacion: precip.get(nombre)?.precipitacion_mm ?? null,
        nivelRio: nivel.get(nombre)?.nivel_m ?? null,
      };
    });
}
