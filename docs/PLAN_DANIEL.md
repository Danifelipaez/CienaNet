# Plan de Ejecución — Tareas de Daniel (Infraestructura)

> Sprint 1. Estado inicial: repo vacío (solo `docs/`).
> Meta: dejar la base lista para que Valentina implemente servicios e ingesta.
> Orden estricto: cada paso depende del anterior.

---

## Pre-requisitos (antes de tocar código)

| # | Acción | Dónde |
|---|--------|-------|
| P-1 | Crear proyecto en Supabase, copiar `SUPABASE_URL` y `service_role key` | dashboard Supabase |
| P-2 | Anotar **dos** connection strings de Supabase: directa (5432) y **pooler/transaction (6543)** | Supabase → Database → Connection string |
| P-3 | Crear proyecto en Vercel vinculado al repo de GitHub | dashboard Vercel |
| P-4 | Generar `SENSOR_API_KEY_SECRET` (ej: `openssl rand -hex 32`) | local |

> **Gotcha crítico (serverless):** Vercel abre y cierra funciones constantemente. Conectarse al puerto **5432** agota las conexiones de Postgres. En runtime usar el **pooler de Supabase (puerto 6543, modo transaction)**. El puerto directo 5432 se usa **solo para las migraciones de Alembic**. Esto va en `.env` como dos variables separadas.

---

## D-01 — Scaffolding del proyecto

**Orden de ejecución:** primero, bloquea todo lo demás.

1. Crear estructura de carpetas (vacías con `__init__.py`):
   ```
   app/{core,api/v1/routers,services/ingestion,models,schemas}/__init__.py
   api/__init__.py
   tests/__init__.py
   ```
2. `requirements.txt` — solo lo que D-01..D-06 necesitan (el resto lo agrega Valentina):
   ```
   fastapi>=0.115
   uvicorn[standard]>=0.32
   mangum>=0.19
   pydantic>=2.9
   pydantic-settings>=2.5
   sqlalchemy>=2.0
   asyncpg>=0.30
   alembic>=1.13
   psycopg2-binary>=2.9   # Alembic sync para migraciones
   python-dotenv>=1.0
   pytest>=8.0
   pytest-asyncio>=0.24
   httpx>=0.27            # tests + futuros servicios
   ```
3. `runtime.txt` → `python-3.11`
4. `.env.example` con las variables de [KNOWLEDGE_BASE.md §9](./KNOWLEDGE_BASE.md) + `DATABASE_URL_POOLER` y `DATABASE_URL_DIRECT`
5. `.gitignore` → `.env`, `__pycache__/`, `.pytest_cache/`, `*.pyc`
6. `vercel.json`:
   ```json
   { "rewrites": [{ "source": "/(.*)", "destination": "/api/index" }] }
   ```
7. `api/index.py`:
   ```python
   from mangum import Mangum
   from app.main import app
   handler = Mangum(app)
   ```

**Check:** `pip install -r requirements.txt` corre sin error.

---

## D-02 — `app/core/config.py`

Implementar `Settings(BaseSettings)` según [TAREAS_EQUIPO.md D-02](./TAREAS_EQUIPO.md), con la separación de DB:

```python
database_url_pooler: str   # runtime (puerto 6543)
database_url_direct: str   # migraciones Alembic (puerto 5432)
```

**Check (self-test, dejar en `tests/test_config.py`):**
```python
def test_settings_loads(monkeypatch):
    monkeypatch.setenv("DATABASE_URL_POOLER", "postgresql://x")
    monkeypatch.setenv("DATABASE_URL_DIRECT", "postgresql://x")
    monkeypatch.setenv("SUPABASE_URL", "x")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "x")
    monkeypatch.setenv("SENSOR_API_KEY_SECRET", "x")
    from app.core.config import Settings
    assert Settings().cienaga_lat == 10.8
```

---

## D-03 — `app/core/database.py`

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings

class Base(DeclarativeBase):
    pass

# Runtime usa el pooler. asyncpg + pgBouncer transaction mode:
# desactivar prepared statements con statement_cache_size=0
engine = create_async_engine(
    settings.database_url_pooler.replace("postgresql://", "postgresql+asyncpg://"),
    connect_args={"statement_cache_size": 0},
    pool_pre_ping=True,
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
```

> **Gotcha:** pgBouncer en modo *transaction* no soporta prepared statements de asyncpg. Sin `statement_cache_size=0` las queries fallan intermitentemente en producción. Documentado, no descubrir a las 3am.

---

## D-04 — `app/core/security.py`

Tres funciones, todas con type hints:

```python
import hashlib, hmac
from app.core.config import settings

def verify_hmac_meta(payload: bytes, signature_header: str) -> bool:
    """signature_header = 'sha256=<hex>'. Comparar con compare_digest."""
    expected = hmac.new(
        settings.whatsapp_app_secret.encode(),
        payload, hashlib.sha256
    ).hexdigest()
    received = signature_header.removeprefix("sha256=")
    return hmac.compare_digest(expected, received)

def hash_api_key(raw_key: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", raw_key.encode(),
        settings.sensor_api_key_secret.encode(), 100_000
    ).hex()

async def verify_sensor_api_key(raw_key: str, db) -> "Sensor | None":
    """Compara hash contra columna api_key_hash. Depende de D-05 (modelo Sensor)."""
    ...
```

**Check (dejar en `tests/test_security.py`):**
```python
def test_hmac_roundtrip(monkeypatch):
    # firmar un payload con la app_secret y verificar que valida;
    # mutar un byte y verificar que falla
```

> HMAC y hashing son security path — el test va sí o sí (guardrail del proyecto).

---

## D-05 — Modelos + migración Alembic

1. `app/models/environmental.py` — declarar las 5 tablas de [KNOWLEDGE_BASE.md §7](./KNOWLEDGE_BASE.md) como clases `Base`: `Sensor`, `SensorReading`, `WeatherSnapshot`, `SatelliteData`, `ExternalAlert`, `DailySemaphore`.
2. `alembic init alembic`
3. En `alembic/env.py`:
   - `target_metadata = Base.metadata`
   - Usar `settings.database_url_direct` (puerto 5432, **no** el pooler) para migraciones
4. Generar y aplicar:
   ```
   alembic revision --autogenerate -m "initial schema"
   alembic upgrade head
   ```

**Check:** las tablas aparecen en el dashboard de Supabase.

> Migraciones por el puerto directo (5432). El pooler no maneja bien DDL transaccional.

---

## D-06 — `app/main.py` + CI/CD

1. `app/main.py`:
   ```python
   from contextlib import asynccontextmanager
   from fastapi import FastAPI
   from fastapi.middleware.cors import CORSMiddleware

   @asynccontextmanager
   async def lifespan(app: FastAPI):
       yield   # Valentina enganchará el background refresh aquí (V-07)

   app = FastAPI(title="CienaNet Bot", version="0.1.0", lifespan=lifespan)
   app.add_middleware(CORSMiddleware, allow_origins=["*"],  # restringir al dominio del dashboard luego
                      allow_methods=["*"], allow_headers=["*"])

   @app.get("/health")
   async def health():
       return {"status": "ok"}
   ```
2. `.github/workflows/test.yml` según [TAREAS_EQUIPO.md D-06](./TAREAS_EQUIPO.md).
3. Verificar deploy: push a `main` → Vercel despliega → `GET /health` responde `{"status":"ok"}`.

**Check:** `pytest` verde en local y en GitHub Actions; `/health` responde en la URL de Vercel.

---

## Resumen de orden y entregables

```
P-1..P-4  (cuentas + secrets)
   ↓
D-01  scaffolding ────────► desbloquea todo
   ↓
D-02  config  ──►  D-03  database  ──►  D-04  security
                                            ↓
                       D-05  modelos + migración (DB viva en Supabase)
                                            ↓
                       D-06  main.py + CI/CD + deploy verde
                                            ↓
              ✅ Valentina arranca V-01 (servicios de ingesta)
```

| Entregable que desbloquea a Valentina | Tarea |
|---|---|
| `get_db()` funcional | D-03 |
| `verify_sensor_api_key` + `hash_api_key` | D-04 |
| Tablas creadas en Supabase | D-05 |
| `app` montada + deploy funcionando | D-06 |

## Definición de "Done" (tareas Daniel)

- [ ] `pip install -r requirements.txt` limpio
- [ ] `pytest` verde (config, security, hmac)
- [ ] `alembic upgrade head` crea las 5 tablas en Supabase
- [ ] `GET /health` responde en producción (Vercel)
- [ ] GitHub Actions corre tests en cada PR
- [ ] `.env.example` completo y `.env` real fuera de git
