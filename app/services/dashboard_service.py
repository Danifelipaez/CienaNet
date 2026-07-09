"""Orquestación del snapshot ambiental y persistencia en DB (V-05)."""

import asyncio
import logging
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.environmental import (
    DailySemaphore,
    IdeamHidroReading,
    SatelliteData,
    WeatherSnapshot,
)
from app.core.config import settings
from app.models.messaging import CatchReport
from app.services.ingestion.alerts_ext import get_cyclone_alerts
from app.services.ingestion.ideam_hidro import get_nivel_historia, get_precipitacion_historia
from app.services.ingestion.satellite import get_satellite_data
from app.services.ingestion.weather import get_weather_forecast
from app.services.ipp import rank_zones
from app.services.semaphore import evaluate
from app.services.sensor_service import aggregate_sensor_readings, get_latest_readings

logger = logging.getLogger(__name__)

# Ventana de respaldo IDEAM: el cron corre 1 vez/día (Vercel) — unos días de
# solape cubren el rezago propio de la fuente (~2 días) sin recorrer meses.
_IDEAM_BACKFILL_DAYS = 7


async def get_latest_snapshot(db: AsyncSession) -> dict:
    """Obtiene datos de todas las fuentes y retorna el snapshot actual.

    Estrategia DB-first para satélite: evita llamadas lentas a NASA ERDDAP
    en cada cold-start de Vercel cuando ya hay datos del día en la DB.
    """
    # Se lanza ya para que corra en paralelo con el resto (I/O de red
    # independiente, no comparte la sesión async de SQLAlchemy).
    ideam_task = asyncio.gather(
        get_precipitacion_historia(_IDEAM_BACKFILL_DAYS),
        get_nivel_historia(_IDEAM_BACKFILL_DAYS),
    )

    sat_date = date.today() - timedelta(days=2)
    db_satellite = (
        await db.execute(
            select(SatelliteData).where(
                SatelliteData.date == sat_date,
                SatelliteData.source == "nasa_mur",
            ).limit(1)
        )
    ).scalar_one_or_none()

    tasajera_task = get_weather_forecast(settings.tasajera_lat, settings.tasajera_lon)

    if db_satellite:
        satellite_data = {
            "sst_celsius": db_satellite.sst_celsius,
            "chlorophyll_mgm3": db_satellite.chlorophyll_mgm3,
            "date": db_satellite.date.isoformat(),
        }
        weather_data, tasajera_weather, alerts = await asyncio.gather(
            get_weather_forecast(),
            tasajera_task,
            get_cyclone_alerts(),
        )
    else:
        weather_data, tasajera_weather, satellite_data, alerts = await asyncio.gather(
            get_weather_forecast(),
            tasajera_task,
            get_satellite_data(),
            get_cyclone_alerts(),
        )

    # DB: lecturas de sensores (sesión separada del gather externo)
    readings = await get_latest_readings(db)

    water = aggregate_sensor_readings(readings)
    semaphore = evaluate(weather_data, satellite_data, water)
    ipp = rank_zones(water, satellite_data)
    today = date.today()

    ideam_precipitacion, ideam_nivel_rio = await ideam_task

    # Persistencia secuencial (una sola sesión async, no concurrent)
    await _save_weather(db, weather_data, "CGSM")
    await _save_weather(db, tasajera_weather, "Tasajera")
    await _save_satellite(db, satellite_data, today)
    await _upsert_semaphore(db, today, semaphore, ipp)
    try:
        await _save_ideam_hidro(db, ideam_precipitacion, ideam_nivel_rio)
    except Exception as exc:
        # No fatal: get_latest_snapshot() lo llama también message_router.py (bot
        # de WhatsApp) — un fallo de respaldo (p.ej. migración 008 aún no aplicada
        # en esta DB) no debe romper la respuesta al pescador ni el cron de Vercel.
        logger.warning("No se pudo guardar respaldo IDEAM en DB: %s", exc)
        await db.rollback()

    return {
        "semaphore": {
            "color": semaphore.color,
            "reason": semaphore.reason,
            "safe": semaphore.safe,
        },
        "weather": weather_data,
        "tasajera_weather": tasajera_weather,
        "ideam_precipitacion": ideam_precipitacion,
        "ideam_nivel_rio": ideam_nivel_rio,
        "satellite": satellite_data,
        "water": water,
        "sensors": [
            {
                "zone": r.sensor.location if r.sensor else None,
                "ph": r.ph,
                "temperature_c": r.temperature_c,
                "conductivity_mscm": r.conductivity_mscm,
            }
            for r in readings
        ],
        "ipp_ranking": ipp,
        "cyclone_alerts": alerts,
        "updated_at": datetime.now(UTC).isoformat(),
    }


def build_ai_context(snapshot: dict) -> str:
    """Arma el bloque de contexto ambiental para el prompt de Gemini (dashboard.ask_ai).

    Cubre las mismas fuentes que /data/latest — clima por estación (CGSM + Tasajera,
    con humedad) e hidrometeorología IDEAM (lluvia/nivel de río) — resumidas a su
    última lectura por estación para no inflar el prompt con series completas; el
    histórico completo ya vive en /data/history si se necesita más adelante.
    """
    parts = [
        f"Semáforo: {snapshot['semaphore']['reason']}.",
        f"Clorofila-a: {snapshot['satellite'].get('chlorophyll_mgm3')} mg/m³ (Copernicus Marine). "
        f"Temperatura superficial del agua: {snapshot['satellite'].get('sst_celsius')} °C (NASA MODIS).",
    ]

    def fmt_weather(label: str, w: dict) -> str:
        return (
            f"{label} (Open-Meteo): temperatura {w.get('temperature_c')} °C, "
            f"humedad {w.get('humidity_pct')}%, viento {w.get('wind_speed_kmh')} km/h, "
            f"precipitación {w.get('precipitation_mm')} mm."
        )

    parts.append(fmt_weather("CGSM", snapshot.get("weather") or {}))
    tasajera = snapshot.get("tasajera_weather")
    if tasajera:
        parts.append(fmt_weather("Tasajera", tasajera))

    def latest_por_estacion(rows: list[dict], value_key: str) -> dict[str, tuple[str, float]]:
        latest: dict[str, tuple[str, float]] = {}
        for r in rows:
            prev = latest.get(r["estacion"])
            if prev is None or r["date"] > prev[0]:
                latest[r["estacion"]] = (r["date"], r[value_key])
        return latest

    precip = latest_por_estacion(snapshot.get("ideam_precipitacion") or [], "precipitacion_mm")
    if precip:
        detalle = "; ".join(f"{est} {v} mm ({fecha})" for est, (fecha, v) in precip.items())
        parts.append(f"Precipitación IDEAM, última lectura por estación: {detalle}.")

    nivel = latest_por_estacion(snapshot.get("ideam_nivel_rio") or [], "nivel_m")
    if nivel:
        detalle = "; ".join(f"{est} {v} m ({fecha})" for est, (fecha, v) in nivel.items())
        parts.append(f"Nivel de río IDEAM, última lectura por estación: {detalle}.")

    return " ".join(parts)


async def get_history(db: AsyncSession, days: int) -> dict:
    """Retorna series de tiempo de los últimos N días desde la DB."""
    # Se lanza ya para que corra en paralelo con las queries de DB de abajo (I/O
    # de red independiente, no comparte la sesión async de SQLAlchemy).
    ideam_task = asyncio.gather(get_precipitacion_historia(days), get_nivel_historia(days))

    cutoff = datetime.now(UTC) - timedelta(days=days)
    cutoff_date = cutoff.date()

    weather_rows = (
        await db.execute(
            select(WeatherSnapshot)
            .where(WeatherSnapshot.timestamp >= cutoff)
            .order_by(WeatherSnapshot.timestamp)
        )
    ).scalars().all()

    semaphore_rows = (
        await db.execute(
            select(DailySemaphore)
            .where(DailySemaphore.date >= cutoff_date)
            .order_by(DailySemaphore.date)
        )
    ).scalars().all()

    satellite_rows = (
        await db.execute(
            select(SatelliteData)
            .where(SatelliteData.date >= cutoff_date)
            .order_by(SatelliteData.date)
        )
    ).scalars().all()

    catch_day = func.date(CatchReport.timestamp)
    catch_rows = (
        await db.execute(
            select(catch_day.label("date"), func.avg(CatchReport.cantidad_indice).label("avg"))
            .where(CatchReport.timestamp >= cutoff, CatchReport.cantidad_indice.isnot(None))
            .group_by(catch_day)
            .order_by(catch_day)
        )
    ).all()

    ideam_precipitacion, ideam_nivel_rio = await ideam_task

    return {
        "ideam_precipitacion": ideam_precipitacion,
        "ideam_nivel_rio": ideam_nivel_rio,
        "weather": [
            {
                "timestamp": r.timestamp.isoformat(),
                "estacion": r.estacion,
                "temperature_c": r.temperature_c,
                "humidity_pct": r.humidity_pct,
                "wind_speed_kmh": r.wind_speed_kmh,
                "precipitation_mm": r.precipitation_mm,
            }
            for r in weather_rows
        ],
        "semaphore": [
            {
                "date": r.date.isoformat(),
                "color": r.color,
                "reason": r.reason,
                "ipp_ranking": r.ipp_ranking,
            }
            for r in semaphore_rows
        ],
        "satellite": [
            {
                "date": r.date.isoformat(),
                "sst_celsius": r.sst_celsius,
                "chlorophyll_mgm3": r.chlorophyll_mgm3,
            }
            for r in satellite_rows
        ],
        "captura": [
            {"date": r.date.isoformat(), "cantidad_indice": round(r.avg, 2)}
            for r in catch_rows
        ],
    }


# ── helpers privados ──────────────────────────────────────────────────────────


async def _save_weather(db: AsyncSession, data: dict, estacion: str = "CGSM") -> None:
    if not any(v is not None for v in data.values()):
        return
    # Dedup: no insertar si esta estación ya tiene un snapshot en los últimos 60 min
    cutoff = datetime.now(UTC) - timedelta(hours=1)
    recent = (
        await db.execute(
            select(WeatherSnapshot).where(
                WeatherSnapshot.timestamp >= cutoff,
                WeatherSnapshot.estacion == estacion,
            ).limit(1)
        )
    ).scalar_one_or_none()
    if recent:
        return
    db.add(
        WeatherSnapshot(
            estacion=estacion,
            timestamp=datetime.now(UTC),
            temperature_c=data.get("temperature_c"),
            humidity_pct=data.get("humidity_pct"),
            wind_speed_kmh=data.get("wind_speed_kmh"),
            wind_direction_deg=data.get("wind_direction_deg"),
            precipitation_mm=data.get("precipitation_mm"),
        )
    )
    await db.commit()


async def _save_satellite(db: AsyncSession, data: dict, today: date) -> None:
    sat_date_str = data.get("date") or today.isoformat()
    sat_date = date.fromisoformat(sat_date_str)

    # limit(1): satellite_data no tiene unique en (date, source), así que un día ya
    # puede tener duplicados; la comprobación "¿existe ya?" debe tolerarlos sin
    # reventar (mismo criterio que el read DB-first y _save_weather).
    existing = (
        await db.execute(
            select(SatelliteData).where(
                SatelliteData.date == sat_date,
                SatelliteData.source == "nasa_mur",
            ).limit(1)
        )
    ).scalar_one_or_none()

    if existing:
        return

    db.add(
        SatelliteData(
            source="nasa_mur",
            date=sat_date,
            sst_celsius=data.get("sst_celsius"),
            chlorophyll_mgm3=data.get("chlorophyll_mgm3"),
        )
    )
    await db.commit()


async def _save_ideam_hidro(db: AsyncSession, precipitacion: list[dict], nivel: list[dict]) -> None:
    """Guarda lecturas diarias IDEAM nuevas. Dedup por (variable, estacion, date):
    si ya existe la fila se salta — no se sobreescribe (mismo criterio que
    `_save_satellite`), así que un día ya guardado con dato parcial no se corrige
    después; el rezago propio de la fuente (~2 días) hace que esto sea poco común.
    """
    rows = [("precipitacion_mm", r["estacion"], r["date"], r["precipitacion_mm"]) for r in precipitacion]
    rows += [("nivel_m", r["estacion"], r["date"], r["nivel_m"]) for r in nivel]

    for variable, estacion, date_str, valor in rows:
        row_date = date.fromisoformat(date_str)
        existing = (
            await db.execute(
                select(IdeamHidroReading).where(
                    IdeamHidroReading.variable == variable,
                    IdeamHidroReading.estacion == estacion,
                    IdeamHidroReading.date == row_date,
                ).limit(1)  # tolera duplicados en la comprobación de existencia
            )
        ).scalar_one_or_none()
        if existing:
            continue
        db.add(
            IdeamHidroReading(variable=variable, estacion=estacion, date=row_date, valor=valor)
        )
    await db.commit()


async def _upsert_semaphore(db: AsyncSession, today: date, semaphore, ipp: list) -> None:
    row = (
        await db.execute(select(DailySemaphore).where(DailySemaphore.date == today))
    ).scalar_one_or_none()

    if row:
        row.color = semaphore.color
        row.reason = semaphore.reason
        row.ipp_ranking = ipp
    else:
        db.add(
            DailySemaphore(
                date=today,
                color=semaphore.color,
                reason=semaphore.reason,
                ipp_ranking=ipp,
            )
        )
    await db.commit()
