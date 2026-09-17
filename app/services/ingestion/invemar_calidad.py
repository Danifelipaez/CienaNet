"""Ingesta de calidad ambiental del agua — SIICGSM/INVEMAR (REDCAM), estaciones de
monitoreo en la Ciénaga Grande de Santa Marta: oxígeno disuelto, salinidad, pH,
temperatura y sólidos suspendidos totales (ver siicgsm.invemar.org.co/Calidad-ambiental).

El backend público del dashboard emite un token anónimo sin credenciales — mismo
flujo que usa su propio frontend (`fetch("/auth-api/token", {method: "POST"})`,
sin body, confirmado leyendo su bundle JS). No hace falta API key.

`ano`/`muestreo`/`tipo_variable`/`depto` son obligatorios del lado del servidor
(400 si faltan, confirmado a mano) aunque el frontend los mande opcionales. Se
fijan a `2001`/`1` — el default literal del dashboard antes de que el usuario
toque un filtro — porque es la combinación que devuelve la cobertura más amplia
de estaciones (`anotemp`/`factualizacion` en la respuesta confirman que sigue
siendo la condición vigente, no un dato de archivo de 2001; otros años devuelven
subconjuntos más chicos o vacío si esa campaña no tiene datos todavía).

El servidor de INVEMAR no manda su certificado intermedio en el handshake TLS (bug
de su lado, confirmado con `openssl s_client -showcerts`) — httpx con el trust store
default no completa la cadena. `_invemar_extra_ca.pem` trae el intermedio que falta;
ver el comentario de ese archivo para cómo refrescarlo si Let's Encrypt lo rota.
"""

import logging
import ssl
import time
from pathlib import Path

import certifi
import httpx

logger = logging.getLogger(__name__)

_BASE = "https://siicgsm.invemar.org.co"
_TTL = 6 * 3600.0  # ponytail: monitoreo por campaña semestral, no telemetría — TTL largo basta

_EXTRA_CA = Path(__file__).parent / "_invemar_extra_ca.pem"


def _ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context(cafile=certifi.where())
    ctx.load_verify_locations(cafile=str(_EXTRA_CA))
    return ctx


_SSL_CONTEXT = _ssl_context()

VARIABLES = ("Oxigeno Disuelto", "Salinidad", "Temperatura", "pH", "Sólidos Suspendidos Totales")

_token_cache: dict = {}
_data_cache: dict[str, dict] = {}


async def _get_token(client: httpx.AsyncClient) -> str | None:
    now = time.monotonic()
    if _token_cache.get("token") and now < _token_cache.get("exp", 0):
        return _token_cache["token"]
    try:
        resp = await client.post(f"{_BASE}/auth-api/token")
        resp.raise_for_status()
        data = resp.json()
        _token_cache["token"] = data["access_token"]
        _token_cache["exp"] = now + data.get("expires_in", 3600) - 60
        return _token_cache["token"]
    except Exception as exc:
        logger.warning("INVEMAR SIICGSM: no se pudo obtener token: %s", exc)
        return None


async def get_calidad_agua(variable: str = "Oxigeno Disuelto") -> list[dict]:
    """Condición vigente por estación para una variable (ver VARIABLES)."""
    now = time.monotonic()
    cached = _data_cache.get(variable)
    if cached and now - cached["ts"] < _TTL:
        return cached["data"]

    try:
        async with httpx.AsyncClient(timeout=20, verify=_SSL_CONTEXT) as client:
            token = await _get_token(client)
            if not token:
                return cached["data"] if cached else []
            resp = await client.post(
                f"{_BASE}/api/environmental-quality/stations/filtered-data/",
                json={
                    "depto": "MAGDALENA",
                    "desc_tipo_muestreo": "Sustrato Agua",
                    "tipo_variable": "Físico/Químicas",
                    "nombre_var": variable,
                    "ano": 2001,
                    "muestreo": 1,
                },
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
        rows = resp.json()
        result = [
            {
                "estacion": row["nomest"],
                "sector": row["sector"],
                "variable": row["nombre_var"],
                "valor": row["prom"],
                "unidad": row["unidad"],
                "clase": row["clase"],
                "rango": row["label"],
                "lat": row["lat"],
                "lon": row["lon"],
                "actualizado": row["factualizacion"],
            }
            for row in rows
        ]
        _data_cache[variable] = {"data": result, "ts": now}
        return result
    except Exception as exc:
        logger.warning("INVEMAR SIICGSM (%s) no disponible: %s", variable, exc)
        return cached["data"] if cached else []
