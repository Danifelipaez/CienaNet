def test_settings_loads(monkeypatch):
    monkeypatch.setenv("DATABASE_URL_POOLER", "postgresql://x")
    monkeypatch.setenv("DATABASE_URL_DIRECT", "postgresql://x")
    monkeypatch.setenv("SUPABASE_URL", "x")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "x")
    monkeypatch.setenv("SENSOR_API_KEY_SECRET", "x")
    from app.core.config import Settings

    # _env_file=None: el default es el centroide medido (docs/KNOWLEDGE_BASE.md #12); un .env
    # local con CIENAGA_LAT propio no debe decidir si el test pasa.
    assert Settings(_env_file=None).cienaga_lat == 10.859056
