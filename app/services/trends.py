"""Tendencias 24h/7d desde lo ya persistido. Cero llamadas de red.

No vive en dashboard_service.py (ya pasa de 400 líneas) ni reusa get_history()
(esa función llama IDEAM en vivo y devuelve series completas para graficar; acá
se necesitan agregados diarios desde la DB para calcular un delta, no una serie
para dibujar). IdeamHidroReading se escribe en cada refresco y hasta
snapshot_service.read_persisted() nadie la leía — este módulo es otro
consumidor de ese mismo respaldo.
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.environmental import IdeamHidroReading, SatelliteData, SensorReading, WeatherSnapshot
from app.services.derived import salinity_psu

# 7 días completos + hoy, para poder calcular delta_7d.
_TREND_READ_DAYS = 8
_LLUVIA_VENTANA_DIAS = 3

# Banda muerta por variable — un delta más chico que esto se reporta "estable"
# en vez de leerse como tendencia real. Números provisionales: deben salir del
# ruido observado en las series reales tras un par de semanas de datos.
_UMBRAL = {
    "salinity_psu": 1.0,      # PSU
    "water_level_cm": 5.0,    # cm
    "sst_celsius": 0.5,       # °C
    "chlorophyll_mgm3": 3.0,  # mg/m³
}


def _delta(serie: list[tuple[date, float]], dias: int) -> float | None:
    """Diferencia entre el valor más reciente y el punto más cercano a `dias`
    atrás. None si no hay al menos un punto anterior con el que comparar."""
    if len(serie) < 2:
        return None
    fecha_actual, valor_actual = serie[-1]
    objetivo = fecha_actual - timedelta(days=dias)
    pasado = min(serie[:-1], key=lambda p: abs((p[0] - objetivo).days))
    return round(valor_actual - pasado[1], 2)


def _direccion(delta: float | None, umbral: float) -> str | None:
    """'subiendo' | 'bajando' | 'estable' | None. None (no "estable") cuando no
    hay histórico suficiente — no inventar una tendencia plana por falta de dato."""
    if delta is None:
        return None
    if abs(delta) < umbral:
        return "estable"
    return "subiendo" if delta > 0 else "bajando"


def _variable(serie: list[tuple[date, float]], umbral: float) -> dict | None:
    if not serie:
        return None
    delta_24h = _delta(serie, 1)
    delta_7d = _delta(serie, 7)
    return {
        "actual": serie[-1][1],
        "delta_24h": delta_24h,
        "delta_7d": delta_7d,
        # La dirección se basa en el delta de 7 días: menos ruidosa que un
        # salto de un día para decidir si algo "está subiendo" de verdad.
        "direccion": _direccion(delta_7d, umbral),
    }


async def _serie_diaria_sensores(db: AsyncSession) -> tuple[list[tuple[date, float]], list[tuple[date, float]]]:
    """(serie_salinidad, serie_nivel) — un punto por día, derivando la salinidad
    del promedio diario de EC/temperatura (misma convención que
    aggregate_sensor_readings: derivar del promedio, no promediar derivadas)."""
    cutoff = datetime.now(UTC) - timedelta(days=_TREND_READ_DAYS)
    rows = (
        await db.execute(select(SensorReading).where(SensorReading.timestamp >= cutoff))
    ).scalars().all()

    por_dia: dict[date, list[SensorReading]] = {}
    for r in rows:
        por_dia.setdefault(r.timestamp.date(), []).append(r)

    salinidad: list[tuple[date, float]] = []
    nivel: list[tuple[date, float]] = []
    for dia in sorted(por_dia):
        lecturas = por_dia[dia]
        ec_vals = [r.conductivity_mscm for r in lecturas if r.conductivity_mscm is not None]
        temp_vals = [r.temperature_c for r in lecturas if r.temperature_c is not None]
        nivel_vals = [r.water_level_cm for r in lecturas if r.water_level_cm is not None]
        if ec_vals and temp_vals:
            sal = salinity_psu(sum(ec_vals) / len(ec_vals), sum(temp_vals) / len(temp_vals))
            if sal is not None:
                salinidad.append((dia, sal))
        if nivel_vals:
            nivel.append((dia, round(sum(nivel_vals) / len(nivel_vals), 1)))
    return salinidad, nivel


async def _serie_diaria_satelite(db: AsyncSession) -> tuple[list[tuple[date, float]], list[tuple[date, float]]]:
    cutoff = date.today() - timedelta(days=_TREND_READ_DAYS)
    rows = (
        await db.execute(
            select(SatelliteData)
            .where(SatelliteData.date >= cutoff, SatelliteData.source == "nasa_mur")
            .order_by(SatelliteData.date)
        )
    ).scalars().all()
    sst = [(r.date, r.sst_celsius) for r in rows if r.sst_celsius is not None]
    chl = [(r.date, r.chlorophyll_mgm3) for r in rows if r.chlorophyll_mgm3 is not None]
    return sst, chl


async def _lluvia_72h(db: AsyncSession) -> float | None:
    """Lluvia acumulada 72h — insumo de pulso_agua_dulce (F8). IDEAM primero
    (agregación diaria real de la cuenca); si no hay dato en la ventana (rezago
    propio de la fuente o scheduler caído), cae a Open-Meteo CGSM ya persistido."""
    cutoff = datetime.now(UTC) - timedelta(days=_LLUVIA_VENTANA_DIAS)
    ideam_rows = (
        await db.execute(
            select(IdeamHidroReading).where(
                IdeamHidroReading.variable == "precipitacion_mm",
                IdeamHidroReading.date >= cutoff.date(),
            )
        )
    ).scalars().all()
    if ideam_rows:
        return round(sum(r.valor for r in ideam_rows), 1)

    weather_rows = (
        await db.execute(
            select(WeatherSnapshot).where(
                WeatherSnapshot.estacion == "CGSM",
                WeatherSnapshot.timestamp >= cutoff,
            )
        )
    ).scalars().all()
    valores = [r.precipitation_mm for r in weather_rows if r.precipitation_mm is not None]
    return round(sum(valores), 1) if valores else None


async def get_trends(db: AsyncSession) -> dict:
    """Tendencias 24h/7d de lo ya persistido. Cero llamadas de red."""
    salinidad, nivel = await _serie_diaria_sensores(db)
    sst, chl = await _serie_diaria_satelite(db)
    lluvia = await _lluvia_72h(db)

    variables = {}
    for nombre, serie in (
        ("salinity_psu", salinidad),
        ("water_level_cm", nivel),
        ("sst_celsius", sst),
        ("chlorophyll_mgm3", chl),
    ):
        v = _variable(serie, _UMBRAL[nombre])
        if v is not None:
            variables[nombre] = v

    return {"variables": variables, "lluvia_72h_mm": lluvia}
