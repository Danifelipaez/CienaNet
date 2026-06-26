def test_settings_loads(monkeypatch):
    monkeypatch.setenv("DATABASE_URL_POOLER", "postgresql://x")
    monkeypatch.setenv("DATABASE_URL_DIRECT", "postgresql://x")
    monkeypatch.setenv("SUPABASE_URL", "x")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "x")
    monkeypatch.setenv("SENSOR_API_KEY_SECRET", "x")
    from app.core.config import Settings

    assert Settings().cienaga_lat == 10.8
