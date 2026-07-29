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
