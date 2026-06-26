"""Env dummy para que `settings` instancie sin credenciales reales en local/CI.

Se ejecuta al importar conftest (antes de colectar los tests), de modo que
`app.core.config.settings` se construya con estos valores.
"""

import os

os.environ.setdefault("DATABASE_URL_POOLER", "postgresql://u:p@localhost:6543/db")
os.environ.setdefault("DATABASE_URL_DIRECT", "postgresql://u:p@localhost:5432/db")
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "dummy")
os.environ.setdefault("SENSOR_API_KEY_SECRET", "dummy-salt")
os.environ.setdefault("WHATSAPP_APP_SECRET", "dummy-app-secret")
