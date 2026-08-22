"""Tests del deployment serverless en Vercel (api/index.py + vercel.json).

Nada de esto se puede verificar en el propio Vercel desde CI, así que se chequea
lo que sí es verificable acá: que el entry point exporta la app real, que el pool
de conexiones cambia según la plataforma, y que vercel.json no queda apuntando a
rutas o archivos que ya no existen. Ver docs/DEPLOYMENT.md.
"""

import json
from pathlib import Path

from sqlalchemy.pool import NullPool

import api.index as entrypoint
from app.core.database import _engine_kwargs
from app.main import app

_REPO_ROOT = Path(__file__).resolve().parents[1]
_VERCEL_JSON = json.loads((_REPO_ROOT / "vercel.json").read_text(encoding="utf-8"))


def test_entrypoint_exporta_la_misma_app_que_el_servidor_universitario():
    # Sin Mangum ni una app paralela: Vercel sirve el mismo objeto ASGI.
    assert entrypoint.app is app


def test_engine_serverless_usa_nullpool_y_no_pre_ping():
    kwargs = _engine_kwargs(serverless=True)
    assert kwargs["poolclass"] is NullPool
    # pool_pre_ping no aplica: NullPool abre una conexión nueva por request.
    assert "pool_pre_ping" not in kwargs


def test_engine_persistente_mantiene_pool_con_pre_ping():
    kwargs = _engine_kwargs(serverless=False)
    assert kwargs["pool_pre_ping"] is True
    assert "poolclass" not in kwargs


def test_engine_siempre_desactiva_statement_cache_para_pgbouncer():
    for serverless in (True, False):
        assert _engine_kwargs(serverless=serverless)["connect_args"]["statement_cache_size"] == 0


def test_rewrite_apunta_al_entry_point_que_existe():
    destino = _VERCEL_JSON["rewrites"][0]["destination"]
    assert destino == "/api/index"
    assert (_REPO_ROOT / "api" / "index.py").is_file()


def test_cron_apunta_a_una_ruta_real_de_la_app():
    # El cron diario refresca el snapshot ambiental; nunca manda alertas (eso
    # vive en _hourly_refresh, gateado por RUN_SCHEDULER). Se lee del esquema
    # OpenAPI y no de app.routes: los routers incluidos quedan anidados y la
    # forma exacta cambia entre versiones de Starlette.
    rutas = set(app.openapi()["paths"])
    for cron in _VERCEL_JSON["crons"]:
        assert cron["path"] in rutas, f"cron apunta a {cron['path']}, que no es una ruta de la app"


def test_max_duration_declarado_para_el_entry_point():
    # El default de 10s no alcanza: /data/latest llama a ERDDAP, Open-Meteo,
    # IDEAM y NOAA en el mismo request.
    assert _VERCEL_JSON["functions"]["api/index.py"]["maxDuration"] == 60


def _floors(path: Path) -> dict[str, str]:
    floors = {}
    for linea in path.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#"):
            continue
        nombre, _, version = linea.partition(">=")
        floors[nombre.strip()] = version.strip()
    return floors


def test_requirements_de_vercel_no_se_desincronizan_de_la_raiz():
    # api/requirements.txt es un subconjunto de runtime de requirements.txt: si
    # sube un floor en la raíz y no acá, Vercel instala una versión distinta a
    # la del servidor universitario sin que nadie se entere.
    raiz = _floors(_REPO_ROOT / "requirements.txt")
    vercel = _floors(_REPO_ROOT / "api" / "requirements.txt")
    assert vercel, "api/requirements.txt quedó vacío"
    for paquete, floor in vercel.items():
        assert paquete in raiz, f"{paquete} no está en requirements.txt"
        assert raiz[paquete] == floor, f"floor desincronizado para {paquete}"
