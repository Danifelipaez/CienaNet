"""Pydantic schemas para respuestas del dashboard (KNOWLEDGE_BASE §8)."""

from datetime import date, datetime

from pydantic import BaseModel


class WeatherData(BaseModel):
    temperature_c: float | None
    humidity_pct: float | None = None
    wind_speed_kmh: float | None
    wind_direction_deg: float | None
    wind_gust_kmh: float | None = None
    precipitation_mm: float | None


class SatelliteSnapshot(BaseModel):
    sst_celsius: float | None
    chlorophyll_mgm3: float | None
    date: str | None


class SemaphoreInfo(BaseModel):
    color: str
    reason: str
    safe: bool


class ZoneIPP(BaseModel):
    zone: str
    ipp: float
    cobertura: float | None = None  # fracción 0-1 del peso IPP que tuvo dato real


class SensorSummary(BaseModel):
    zone: str | None
    ph: float | None
    temperature_c: float | None
    conductivity_mscm: float | None
    water_level_cm: float | None = None


class WaterQuality(BaseModel):
    ph: float | None = None
    temperature_c: float | None = None
    conductivity_mscm: float | None = None
    water_level_cm: float | None = None
    salinity_psu: float | None = None  # derivada PSS-78 (§10)
    tds_mgl: float | None = None       # derivada APHA (§10)


class IdeamPrecipitacionPoint(BaseModel):
    date: str
    estacion: str
    precipitacion_mm: float


class IdeamNivelPoint(BaseModel):
    date: str
    estacion: str
    nivel_m: float


class DashboardSnapshot(BaseModel):
    semaphore: SemaphoreInfo
    weather: WeatherData
    tasajera_weather: WeatherData | None = None
    satellite: SatelliteSnapshot
    water: WaterQuality
    sensors: list[SensorSummary]
    ipp_ranking: list[ZoneIPP]
    cyclone_alerts: list[dict]
    ideam_precipitacion: list[IdeamPrecipitacionPoint] = []
    ideam_nivel_rio: list[IdeamNivelPoint] = []
    # Procedencia por fuente: "medido" | "cache" | "baseline" | "sin_dato" (satellite
    # trae un sub-dict por campo). Sin framework — ver dashboard_service.get_latest_snapshot.
    origen: dict = {}
    # Deltas 24h/7d por variable + lluvia acumulada 72h. Ver app/services/trends.py.
    tendencias: dict = {}
    # Señales compuestas (anoxia, pulso de agua dulce) — ESTIMACIONES, no
    # mediciones. Ver app/services/signals.py.
    senales: dict = {}
    updated_at: str


class WeatherHistoryPoint(BaseModel):
    timestamp: str
    estacion: str
    temperature_c: float | None
    humidity_pct: float | None
    wind_speed_kmh: float | None
    wind_gust_kmh: float | None = None
    precipitation_mm: float | None


class SemaphoreHistoryPoint(BaseModel):
    date: date
    color: str | None  # DailySemaphore.color es nullable en DB
    reason: str | None
    ipp_ranking: list | None


class SatelliteHistoryPoint(BaseModel):
    date: date
    sst_celsius: float | None
    chlorophyll_mgm3: float | None


class CatchHistoryPoint(BaseModel):
    date: date
    cantidad_indice: float


class HistoryResponse(BaseModel):
    weather: list[WeatherHistoryPoint]
    semaphore: list[SemaphoreHistoryPoint]
    satellite: list[SatelliteHistoryPoint]
    captura: list[CatchHistoryPoint]
    ideam_precipitacion: list[IdeamPrecipitacionPoint] = []
    ideam_nivel_rio: list[IdeamNivelPoint] = []
