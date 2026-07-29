"""Estado ambiental YA persistido, sin llamadas de red — camino de LECTURA.

`get_latest_snapshot()` (dashboard_service) es el camino de ESCRITURA: llama a
las APIs externas y persiste. Solo deben invocarlo el scheduler horario
(app/main.py::_hourly_refresh) y GET /data/latest. Todo lo demás — el bot de
WhatsApp, la vista Mapa — lee lo que el scheduler ya dejó en la DB con
`read_persisted()`, que es lo que este módulo expone. Antes, el bot llamaba a
get_latest_snapshot() en cada mensaje: 5+ llamadas de red y 4 escrituras a DB
para responder una oración.
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.environmental import (
    DailySemaphore,
    IdeamHidroReading,
    SatelliteData,
    WeatherSnapshot,
)
from app.services.sensor_service import aggregate_sensor_readings, get_latest_readings
from app.services.signals import anoxia_risk, pulso_agua_dulce
from app.services.trends import get_trends

# Margen sobre el backfill de escritura (7d, ver dashboard_service._IDEAM_BACKFILL_DAYS)
# para tolerar el scheduler caído un par de días sin quedarse sin datos que leer.
_IDEAM_READ_DAYS = 10


def _horas_desde(dt: datetime) -> float:
    return round((datetime.now(UTC) - dt).total_seconds() / 3600, 1)


def _weather_dict(row: WeatherSnapshot | None) -> dict:
    if row is None:
        return {
            "temperature_c": None,
            "humidity_pct": None,
            "wind_speed_kmh": None,
            "wind_direction_deg": None,
            "wind_gust_kmh": None,
            "precipitation_mm": None,
        }
    return {
        "temperature_c": row.temperature_c,
        "humidity_pct": row.humidity_pct,
        "wind_speed_kmh": row.wind_speed_kmh,
        "wind_direction_deg": row.wind_direction_deg,
        "wind_gust_kmh": row.wind_gust_kmh,
        "precipitation_mm": row.precipitation_mm,
    }


async def read_persisted(db: AsyncSession) -> dict:
    """Último estado ambiental YA persistido. Cero llamadas de red.

    Misma forma que get_latest_snapshot() en las claves que consumen
    build_ai_context() y el bot: semaphore, weather, tasajera_weather, satellite,
    water, ipp_ranking, ideam_precipitacion, ideam_nivel_rio — más `edad_horas`
    por fuente, para que el consumidor pueda avisar si el dato está viejo en vez
    de presentarlo como si fuera del momento.
    """
    weather_row = (
        await db.execute(
            select(WeatherSnapshot)
            .where(WeatherSnapshot.estacion == "CGSM")
            .order_by(desc(WeatherSnapshot.timestamp))
            .limit(1)
        )
    ).scalar_one_or_none()
    # Bug vivo antes de esta función: points_service.py tomaba el WeatherSnapshot
    # más reciente sin filtrar estación, así que podía devolver el viento de
    # Tasajera para toda la ciénaga.
    tasajera_row = (
        await db.execute(
            select(WeatherSnapshot)
            .where(WeatherSnapshot.estacion == "Tasajera")
            .order_by(desc(WeatherSnapshot.timestamp))
            .limit(1)
        )
    ).scalar_one_or_none()
    satellite_row = (
        await db.execute(select(SatelliteData).order_by(desc(SatelliteData.date)).limit(1))
    ).scalar_one_or_none()
    semaphore_row = (
        await db.execute(select(DailySemaphore).order_by(desc(DailySemaphore.date)).limit(1))
    ).scalar_one_or_none()

    readings = await get_latest_readings(db)
    water = aggregate_sensor_readings(readings)
    tendencias = await get_trends(db)

    # IdeamHidroReading se escribe en cada refresco (_save_ideam_hidro) y hasta
    # ahora nadie la leía: get_history() vuelve a pedirle la serie a Socrata en
    # vivo. Acá sí se lee de DB — es justo el respaldo para el que existe.
    ideam_cutoff = date.today() - timedelta(days=_IDEAM_READ_DAYS)
    ideam_rows = (
        await db.execute(
            select(IdeamHidroReading)
            .where(IdeamHidroReading.date >= ideam_cutoff)
            .order_by(IdeamHidroReading.date)
        )
    ).scalars().all()
    ideam_precipitacion = [
        {"date": r.date.isoformat(), "estacion": r.estacion, "precipitacion_mm": r.valor}
        for r in ideam_rows
        if r.variable == "precipitacion_mm"
    ]
    ideam_nivel_rio = [
        {"date": r.date.isoformat(), "estacion": r.estacion, "nivel_m": r.valor}
        for r in ideam_rows
        if r.variable == "nivel_m"
    ]

    satellite = {
        "sst_celsius": satellite_row.sst_celsius if satellite_row else None,
        "chlorophyll_mgm3": satellite_row.chlorophyll_mgm3 if satellite_row else None,
        "date": satellite_row.date.isoformat() if satellite_row else None,
        "por_zona": (satellite_row.por_zona if satellite_row else None) or {},
    }
    # build_ai_context indexa snapshot["semaphore"]["reason"] con [] (no .get) —
    # siempre debe existir, aunque no haya fila reciente.
    semaphore = {
        "color": semaphore_row.color if semaphore_row else None,
        "reason": semaphore_row.reason if semaphore_row else "Sin datos recientes",
    }

    return {
        "semaphore": semaphore,
        "weather": _weather_dict(weather_row),
        "tasajera_weather": _weather_dict(tasajera_row) if tasajera_row else None,
        "satellite": satellite,
        "water": water,
        "ipp_ranking": (semaphore_row.ipp_ranking if semaphore_row else None) or [],
        "ideam_precipitacion": ideam_precipitacion,
        "ideam_nivel_rio": ideam_nivel_rio,
        "tendencias": tendencias,
        "senales": {
            "anoxia": anoxia_risk(satellite, _weather_dict(weather_row), water),
            "pulso_agua_dulce": pulso_agua_dulce(
                tendencias.get("lluvia_72h_mm"), water.get("salinity_psu")
            ),
        },
        "edad_horas": {
            "weather": _horas_desde(weather_row.timestamp) if weather_row else None,
            "satellite": (date.today() - satellite_row.date).days * 24.0 if satellite_row else None,
            "water": max((_horas_desde(r.timestamp) for r in readings), default=None),
        },
        # _save_satellite nunca persiste un baseline como si fuera medición (NULL
        # en su lugar), así que un valor no-nulo leído de DB es siempre "medido".
        "origen": {
            "weather": "medido" if weather_row else "sin_dato",
            "satellite": {
                "sst_celsius": "medido" if satellite["sst_celsius"] is not None else "sin_dato",
                "chlorophyll_mgm3": "medido" if satellite["chlorophyll_mgm3"] is not None else "sin_dato",
            },
            "water": "medido" if water else "sin_dato",
        },
    }
