"""Configuración de la app cargada desde variables de entorno (.env)."""

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Base de datos (Supabase). Nombres generados por la integración Vercel-Supabase.
    # - pooler (transaction mode) para el runtime de la app
    # - non-pooling (direct) solo para las migraciones de Alembic
    postgres_prisma_url: str
    postgres_url_non_pooling: str

    # Supabase API
    supabase_url: str
    supabase_service_role_key: str

    # Meta WhatsApp Cloud API (opcionales hasta integrar el webhook)
    whatsapp_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_verify_token: str = ""
    whatsapp_app_secret: str = ""

    # IA / NLU — proveedor agnóstico; la implementación concreta vive en ai_service.py
    ai_api_key: str = ""
    ai_model: str = "gemini-flash-lite-latest"  # ajustar al id exacto de AI Studio
    ai_history_turns: int = 10  # mensajes previos que se mandan como contexto en WhatsApp

    # App
    sensor_api_key_secret: str
    admin_api_key: str = "change-me"
    environment: str = "development"
    # true SOLO en el deployment dueño del webhook de WhatsApp y del scheduler
    # (hoy: el servidor universitario). Controla si esta instancia agenda el
    # loop horario (_hourly_refresh en app/main.py) — debe estar en true en un
    # único deployment a la vez. Ver docs/DEPLOYMENT.md.
    run_scheduler: bool = False
    # Orígenes de navegador con permiso CORS, separados por coma. Vacío por
    # defecto: el frontend habla con este backend server-to-server vía
    # BACKEND_URL (ver docs/ARCHITECTURE.md), nunca desde el navegador — así
    # que ningún origen de navegador es legítimo salvo que se agregue uno acá.
    cors_allowed_origins: str = ""

    # Coordenadas centro de la Ciénaga Grande (no secretos)
    # Centroide real medido (ver docs/KNOWLEDGE_BASE.md #12)
    cienaga_lat: float = 10.859056
    cienaga_lon: float = -74.460611

    # Coordenadas Tasajera (dato comunitario ilustrativo, ver
    # alembic/versions/003_fishing_points.py y docs/KNOWLEDGE_BASE.md #565 —
    # no validado con medición territorial precisa)
    tasajera_lat: float = 10.972
    tasajera_lon: float = -74.434

    # Umbral de ráfaga (km/h), uno de los factores del índice de outlook de vendaval
    # (docs/ALERTAS_VENDAVAL.md, app/services/signals.py::vendaval_risk). 62 km/h =
    # piso de "vendaval" en la escala Beaufort (grado 8) — NO es un umbral oficial
    # de IDEAM, así que queda configurable por env var.
    vendaval_gust_threshold_kmh: float = 62.0
    # Ventana de pronóstico que se revisa en cada refresco horario — cuántas horas
    # hacia adelante se busca (get_convective_forecast). 48h da margen para el
    # outlook incluso si el refresco horario se atrasa un ciclo.
    vendaval_forecast_hours: int = 48

    # Caja del corredor de aproximación Cesar -> Magdalena centro que vigila el
    # nowcast de rayos (app/services/ingestion/lightning.py). Backtest real del
    # vendaval del 29-ago-2026 (docs/ALERTAS_VENDAVAL.md): el sistema que dañó
    # Tenerife se originó cerca de la frontera con Cesar y cruzó esta caja.
    corredor_lat_min: float = 9.0
    corredor_lat_max: float = 11.3
    corredor_lon_min: float = -75.3
    corredor_lon_max: float = -73.3
    # Minutos máximos de ETA para que tormenta_aproximandose() dispare — más allá
    # de esto el pronóstico de trayectoria lineal es poco confiable (una tormenta
    # real serpentea). 90 min da margen sin alertar con un día de anticipación.
    nowcast_eta_max_min: int = 90
    # Archivos GLM-L2-LCFA por ciclo de 10 min (cadencia real del producto: 20s,
    # ver scripts/verify_glm_lead_29ago.py) — 3 archivos = 1 min de destellos,
    # ~1.3 MB, suficiente para un centroide sin descargar el ciclo completo.
    glm_files_per_ciclo: int = 3

    # ERDDAP — dataset ids versionados en config, no en código:
    # pueden cambiar si NOAA/Copernicus actualizan el producto satelital.
    erddap_sst_dataset: str = "jplMURSST41"
    # Sector "FG" (Sentinel-3 OLCI, ~278m/diario) cubre la CGSM — ver docs/RESOLUCION_FUENTES.md.
    # Cambia si NOAA reorganiza los sectores (216 en total, uno por bloque geográfico).
    erddap_chl_dataset: str = "noaacwS3AOLCIchlaSectorFGDaily"

    @model_validator(mode="after")
    def _reject_default_admin_key_outside_dev(self) -> "Settings":
        # Guarda /admin/* (registro de sensores) y los proxies del dashboard
        # (require_admin). "change-me" es el default público, documentado en
        # docs/KNOWLEDGE_BASE.md — fallar cerrado si queda así fuera de dev.
        if self.environment != "development" and self.admin_api_key in ("", "change-me"):
            raise ValueError(
                "ADMIN_API_KEY no puede quedar en el valor por defecto fuera de development"
            )
        return self


settings = Settings()
