"""Guardado en DB del snapshot ambiental — usado exclusivamente por
dashboard_service.get_latest_snapshot() (camino de escritura)."""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.environmental import (
    DailySemaphore,
    IdeamHidroReading,
    SatelliteData,
    WeatherSnapshot,
)


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
            wind_gust_kmh=data.get("wind_gust_kmh"),
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

    # No persistir baselines como si fueran medición: si el origen de un campo es
    # "baseline" (la API externa falló o el valor cayó fuera de rango), se guarda
    # NULL — la columna ya es nullable, y ausencia = "no hubo dato", que es la
    # verdad. Antes un 28.0°C / 4.5 mg/m³ de respaldo quedaba en la DB
    # indistinguible de una medición real para siempre.
    origen = data.get("origen") or {}
    sst = data.get("sst_celsius")
    chlorophyll = data.get("chlorophyll_mgm3")
    if origen.get("sst_celsius") == "baseline":
        sst = None
    if origen.get("chlorophyll_mgm3") == "baseline":
        chlorophyll = None

    db.add(
        SatelliteData(
            source="nasa_mur",
            date=sat_date,
            sst_celsius=sst,
            chlorophyll_mgm3=chlorophyll,
            por_zona=data.get("por_zona") or None,
        )
    )
    await db.commit()


async def _save_ideam_hidro(db: AsyncSession, precipitacion: list[dict], nivel: list[dict]) -> None:
    """Guarda lecturas diarias IDEAM nuevas. Dedup por (variable, estacion, date) vía
    ON CONFLICT DO NOTHING sobre la unique constraint del modelo — no se sobreescribe
    (mismo criterio que `_save_satellite`), así que un día ya guardado con dato parcial
    no se corrige después; el rezago propio de la fuente (~2 días) hace que esto sea
    poco común. Un solo INSERT (no un SELECT+INSERT por fila): evita el IntegrityError
    que un SELECT-then-INSERT produciría si dos refrescos corren en paralelo.
    """
    rows = [
        {"variable": "precipitacion_mm", "estacion": r["estacion"], "date": date.fromisoformat(r["date"]), "valor": r["precipitacion_mm"]}
        for r in precipitacion
    ] + [
        {"variable": "nivel_m", "estacion": r["estacion"], "date": date.fromisoformat(r["date"]), "valor": r["nivel_m"]}
        for r in nivel
    ]
    if not rows:
        return

    stmt = pg_insert(IdeamHidroReading).values(rows)
    stmt = stmt.on_conflict_do_nothing(index_elements=["variable", "estacion", "date"])
    await db.execute(stmt)
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
