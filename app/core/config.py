"""Configuración de la app cargada desde variables de entorno (.env)."""

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

    # Coordenadas centro de la Ciénaga Grande (no secretos)
    cienaga_lat: float = 10.8
    cienaga_lon: float = -74.4

    # ERDDAP — dataset ids versionados en config, no en código:
    # pueden cambiar si NOAA/Copernicus actualizan el producto satelital.
    erddap_sst_dataset: str = "jplMURSST41"
    # Sector "FG" (Sentinel-3 OLCI, ~278m/diario) cubre la CGSM — ver docs/RESOLUCION_FUENTES.md.
    # Cambia si NOAA reorganiza los sectores (216 en total, uno por bloque geográfico).
    erddap_chl_dataset: str = "noaacwS3AOLCIchlaSectorFGDaily"


settings = Settings()
