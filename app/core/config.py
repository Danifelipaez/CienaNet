"""Configuración de la app cargada desde variables de entorno (.env)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Base de datos (Supabase). Dos URLs por el modelo serverless:
    # - pooler (6543, transaction mode) para el runtime de la app
    # - direct (5432) solo para las migraciones de Alembic
    database_url_pooler: str
    database_url_direct: str

    # Supabase API
    supabase_url: str
    supabase_service_role_key: str

    # Meta WhatsApp Cloud API (opcionales hasta integrar el webhook)
    whatsapp_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_verify_token: str = ""
    whatsapp_app_secret: str = ""

    # Claude API (Anthropic)
    anthropic_api_key: str = ""

    # App
    sensor_api_key_secret: str
    environment: str = "development"

    # Coordenadas centro de la Ciénaga Grande (no secretos)
    cienaga_lat: float = 10.8
    cienaga_lon: float = -74.4


settings = Settings()
