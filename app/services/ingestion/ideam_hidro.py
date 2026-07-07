"""Ingesta hidrometeorológica IDEAM en vivo — estaciones automáticas con telemetría
en la cuenca de la Ciénaga Grande de Santa Marta (ver docs/IDEAM_GBIF_VALIDACION.md).

Mismo backend Socrata de datos.gov.co que sbwg-7ju4, pero datasets separados por
variable con agregación server-side (date_trunc_ymd + sum/avg vía SoQL) — evita
traer miles de filas crudas de 10 min/1h solo para graficar un total/promedio diario.

Cobertura real (confirmada por curl, ver docs/IDEAM_GBIF_VALIDACION.md):
- Precipitación (`s54a-sgyg`): Media Luna y La Gran Vía, cada 10 min.
- Nivel instantáneo del río (`bdmn-sqnh`): Puerto Rico Hacienda (río Fundación) y
  Ganadería Caribe (río Aracataca), cada hora.
No hay dataset de caudal en vivo — requiere curva de calibración que IDEAM solo
publica como producto validado periódico, no como telemetría cruda.
"""

import logging
import time
from datetime import UTC, datetime, timedelta

import httpx

logger = logging.getLogger(__name__)

_SOCRATA_BASE = "https://www.datos.gov.co/resource"
_PRECIP_DATASET = "s54a-sgyg"
_NIVEL_DATASET = "bdmn-sqnh"

# Códigos con el padding de 10 dígitos que exige este backend Socrata (distinto del
# padding usado por sbwg-7ju4). Ver docs/IDEAM_GBIF_VALIDACION.md para el porqué de
# exactamente estas 2 estaciones por variable.
_PRECIP_STATIONS = ["0029065000", "0029065130"]  # Media Luna, La Gran Vía
_NIVEL_STATIONS = ["0029067060", "0029067150"]  # Puerto Rico Hacienda, Ganadería Caribe

_TTL = 1800.0  # 30 min — suficiente para datos que ya llegan con ~2 días de rezago

# ponytail: cache de módulo por (dataset, days) — un par de variables, no necesita más
_cache: dict[tuple[str, int], dict] = {}


async def _fetch_daily_series(
    dataset: str, stations: list[str], agg: str, value_key: str, days: int
) -> list[dict]:
    cache_key = (dataset, days)
    now = time.monotonic()
    cached = _cache.get(cache_key)
    if cached and now - cached["ts"] < _TTL:
        return cached["data"]

    cutoff = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00")
    stations_sql = ",".join(f"'{s}'" for s in stations)
    params = {
        "$select": (
            f"date_trunc_ymd(fechaobservacion) as fecha, codigoestacion, "
            f"nombreestacion, {agg}(valorobservado) as {value_key}"
        ),
        "$where": f"codigoestacion in ({stations_sql}) AND fechaobservacion > '{cutoff}'",
        "$group": "fecha, codigoestacion, nombreestacion",
        "$order": "fecha",
        "$limit": 5000,
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(f"{_SOCRATA_BASE}/{dataset}.json", params=params)
            resp.raise_for_status()
        rows = resp.json()
        result = [
            {
                "date": row["fecha"][:10],
                "estacion": row["nombreestacion"].title(),
                value_key: round(float(row[value_key]), 2),
            }
            for row in rows
            if row.get(value_key) is not None
        ]
        _cache[cache_key] = {"data": result, "ts": now}
        return result
    except Exception as exc:
        logger.warning("IDEAM Socrata (%s) no disponible: %s", dataset, exc)
        return cached["data"] if cached else []


async def get_precipitacion_historia(days: int = 30) -> list[dict]:
    """Precipitación diaria (mm, suma de lecturas de 10 min) por estación."""
    return await _fetch_daily_series(
        _PRECIP_DATASET, _PRECIP_STATIONS, "sum", "precipitacion_mm", days
    )


async def get_nivel_historia(days: int = 30) -> list[dict]:
    """Nivel de río diario (m, promedio de lecturas horarias) por estación."""
    return await _fetch_daily_series(_NIVEL_DATASET, _NIVEL_STATIONS, "avg", "nivel_m", days)
