"""Backtest manual: ¿el pronóstico de ráfaga de Open-Meteo habría disparado la
alerta de vendaval (app/services/signals.py::vendaval_risk) con AL MENOS 1 hora
de anticipación para un evento real ya ocurrido?

NO es parte de la suite de pytest ni de la app en ejecución — script de
verificación manual, mismo espíritu que scripts/verify_alert_lock.py. Necesita
salida a internet real hacia *.open-meteo.com. No se pudo correr desde el
sandbox de la sesión que lo escribió (bloqueado por la política de red del
entorno — mismo bloqueo que ya afectaba a ideam.gov.co, ver
docs/ALERTAS_VENDAVAL.md) — hay que correrlo desde una máquina con red real
(el servidor universitario sirve, ya llama a api.open-meteo.com en producción).

Compara dos endpoints de la misma API:
1. Archive API (`archive-api.open-meteo.com`) — qué pasó en realidad ese día
   (dato re-analizado ERA5 / ECMWF IFS, la "verdad de terreno").
2. Previous Runs API (`previous-runs-api.open-meteo.com`) — qué decía el
   pronóstico en corridas de días anteriores (`*_previous_day0` = corrida más
   reciente ese mismo día, `_previous_day1` = un día antes, etc.) para esas
   mismas horas. OJO: el shape exacto de esta respuesta NO se pudo verificar
   desde el entorno donde se escribió este script — confirmar contra
   https://open-meteo.com/en/docs/previous-runs-api antes de confiar en el
   resultado. Si falla, el script igual imprime la parte de Archive API (punto 1).

Uso:
    python scripts/verify_vendaval_forecast_lead.py [lat] [lon] [YYYY-MM-DD]

Default: centroide CGSM (10.859056, -74.460611, el mismo que usa
settings.cienaga_lat/lon), 2026-08-29 — el ÚNICO punto que hoy vigila
get_wind_gust_forecast(). El vendaval reportado por medios el 29 de agosto se
concentró en Magdalena central/sur (Tenerife, Ariguaní, Chibolo, Plato,
Santa Ana, San Zenón...), desplazándose desde Cesar — aproximadamente
80-160 km al sur del centroide CGSM (distancia estimada a ojo sobre el mapa
del departamento, no geocodificada). Para comparar con esos municipios,
correr también con sus coordenadas reales, por ejemplo:

    curl "https://geocoding-api.open-meteo.com/v1/search?name=Plato&country=CO"

(no se adivinaron coordenadas de municipios en este script — solo el
centroide CGSM, que sí es un valor ya usado y confirmado en el proyecto).
"""

import json
import sys
import urllib.request
from urllib.parse import urlencode

UMBRAL_KMH = 62.0  # settings.vendaval_gust_threshold_kmh — mantener sincronizado a mano
CGSM_LAT, CGSM_LON = 10.859056, -74.460611
DEFAULT_DATE = "2026-08-29"
N_CORRIDAS_PREVIAS = 4  # previous_day0 (misma corrida del día) .. previous_day3


def _get(url: str, params: dict) -> dict:
    full = f"{url}?{urlencode(params)}"
    with urllib.request.urlopen(full, timeout=20) as resp:
        return json.loads(resp.read())


def actual_gusts(lat: float, lon: float, date: str) -> dict[str, float | None]:
    """Ground truth: ráfaga observada/reanalizada ese día (archive-api)."""
    data = _get(
        "https://archive-api.open-meteo.com/v1/archive",
        {
            "latitude": lat,
            "longitude": lon,
            "start_date": date,
            "end_date": date,
            "hourly": "wind_gusts_10m",
            "timezone": "America/Bogota",
        },
    )
    hourly = data["hourly"]
    return dict(zip(hourly["time"], hourly["wind_gusts_10m"], strict=True))


def forecast_previous_runs(lat: float, lon: float, date: str) -> dict | None:
    """Qué decía el pronóstico en corridas de hasta N_CORRIDAS_PREVIAS días antes.
    Devuelve None (en vez de lanzar) si el endpoint o el shape no responden como
    se esperaba — ver el aviso grande en el docstring del módulo."""
    try:
        data = _get(
            "https://previous-runs-api.open-meteo.com/v1/forecast",
            {
                "latitude": lat,
                "longitude": lon,
                "start_date": date,
                "end_date": date,
                "hourly": ",".join(
                    f"wind_gusts_10m_previous_day{n}" for n in range(N_CORRIDAS_PREVIAS)
                ),
                "timezone": "America/Bogota",
            },
        )
        return data["hourly"]
    except Exception as exc:  # noqa: BLE001 — script de diagnóstico manual, no la app
        print(f"[aviso] Previous Runs API no respondió como se esperaba: {exc}")
        print("        Revisar https://open-meteo.com/en/docs/previous-runs-api")
        return None


def main() -> None:
    lat = float(sys.argv[1]) if len(sys.argv) > 1 else CGSM_LAT
    lon = float(sys.argv[2]) if len(sys.argv) > 2 else CGSM_LON
    date = sys.argv[3] if len(sys.argv) > 3 else DEFAULT_DATE

    print(f"Punto: {lat}, {lon} — fecha: {date} — umbral vendaval: {UMBRAL_KMH} km/h\n")

    actuales = actual_gusts(lat, lon, date)
    horas_reales = {h: v for h, v in actuales.items() if v is not None and v >= UMBRAL_KMH}
    if horas_reales:
        print(f"Ráfaga REAL >= umbral en {len(horas_reales)} hora(s): {horas_reales}")
    else:
        print("Ninguna hora con ráfaga REAL >= umbral en este punto/fecha —")
        print("si el punto es el centroide CGSM, esto NO contradice que hubo vendaval")
        print("en otro lugar del Magdalena: es un solo punto, no todo el departamento.")

    pronosticos = forecast_previous_runs(lat, lon, date)
    if pronosticos is None:
        return

    times = pronosticos["time"]
    header = f"{'hora local':17} {'real':>6}  " + "  ".join(f"corrida d-{n}" for n in range(N_CORRIDAS_PREVIAS))
    print(f"\n{header}")
    for i, t in enumerate(times):
        real = actuales.get(t)
        celdas = []
        for n in range(N_CORRIDAS_PREVIAS):
            serie = pronosticos.get(f"wind_gusts_10m_previous_day{n}") or []
            val = serie[i] if i < len(serie) else None
            celdas.append(f"{val!s:>11}")
        marca = "  <-- REAL >= umbral" if real is not None and real >= UMBRAL_KMH else ""
        print(f"{t:17} {real!s:>6}  " + "  ".join(celdas) + marca)

    print(
        "\nLectura: si en la hora marcada REAL>=umbral alguna corrida d-N (N>=1, o "
        "incluso d-0 si esa corrida es de horas antes) ya mostraba ráfaga >= "
        f"{UMBRAL_KMH} km/h, ese pronóstico SÍ habría disparado maybe_send_wind_alert() "
        "con anticipación. Si todas las corridas quedan por debajo del umbral hasta "
        "muy cerca de la hora real, el umbral/ventana actual NO habría alcanzado a avisar."
    )


if __name__ == "__main__":
    main()
