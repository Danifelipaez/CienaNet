# División de Tareas — Sprint 1: Dashboard Backend

> Objetivo del sprint: API que alimente el dashboard científico con datos ambientales en tiempo real e históricos.  
> Equipo: Daniel (Ing. Sistemas / Tech Lead), Valentina (Ing. Sistemas / Dev), Diego (Ing. Civil / Datos)

> **Estado: Sprint 1 completado.** Todas las tareas D-01..D-06 y V-01..V-07 están implementadas en el código actual (ver [ARCHITECTURE.md](./ARCHITECTURE.md) y [KNOWLEDGE_BASE.md](./KNOWLEDGE_BASE.md) para la estructura real). Este documento queda como referencia histórica de la planificación — los snippets de código de abajo son el diseño original y pueden diferir en detalle de la implementación final (ver notas inline donde aplica).

---

## Criterio de división

| Integrante | Perfil | Foco |
|---|---|---|
| **Daniel** | Tech Lead, arquitectura | Infraestructura base, seguridad, CI/CD |
| **Valentina** | Dev + datos Python | Servicios de ingesta, API del dashboard |
| **Diego** | Ing. Civil, dominio ambiental | Validación de fuentes, umbrales, ML features |

Las tareas de Daniel desbloquean las de Valentina — su trabajo va primero.

---

## Daniel — Infraestructura y Arquitectura

### D-01: Setup del proyecto
- Crear estructura de carpetas según [ADR-001](./ADR-001-arquitectura-backend.md)
- Inicializar `pyproject.toml` o `requirements.txt` con librerías de [KNOWLEDGE_BASE.md §11](./KNOWLEDGE_BASE.md)
- Configurar `vercel.json` + `api/index.py` (Mangum)
- Configurar `.env.example` con todas las variables de [KNOWLEDGE_BASE.md §9](./KNOWLEDGE_BASE.md)

### D-02: `app/core/config.py`
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    whatsapp_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_app_secret: str = ""
    whatsapp_verify_token: str = ""
    supabase_url: str
    supabase_service_role_key: str
    ai_api_key: str = ""
    sensor_api_key_secret: str
    environment: str = "development"
    cienaga_lat: float = 10.859056
    cienaga_lon: float = -74.460611

    class Config:
        env_file = ".env"

settings = Settings()
```

> Nota: el diseño original tenía `anthropic_api_key`; el proveedor de IA elegido fue Google Gemini, así que el campo real en `app/core/config.py` es `ai_api_key` + `ai_model` (ver STACK.md).

### D-03: `app/core/database.py`
```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.core.config import settings

engine = create_async_engine(settings.supabase_url.replace("postgresql://", "postgresql+asyncpg://"))
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
```

### D-04: `app/core/security.py`
- Función `verify_hmac_meta(payload: bytes, signature: str) -> bool`
- Función `hash_api_key(raw_key: str) -> str` (PBKDF2)
- Función `verify_sensor_api_key(raw_key: str, db) -> Sensor | None`

### D-05: Modelos SQLAlchemy + migración Alembic
- Crear `app/models/environmental.py`: tablas `sensor_readings`, `weather_snapshots`, `satellite_data`, `external_alerts`, `daily_semaphore`
- Inicializar Alembic: `alembic init alembic`
- Crear primera migración con el schema de [KNOWLEDGE_BASE.md §7](./KNOWLEDGE_BASE.md)
- Aplicar en Supabase

### D-06: CI/CD GitHub Actions
```yaml
# .github/workflows/test.yml
name: Test
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -r requirements.txt
      - run: pytest tests/ -v
```

**Entrega D-01 a D-05 desbloquean todo el trabajo de Valentina.**

---

## Valentina — Servicios de ingesta y API

> Prerequisito: D-01 a D-05 completos (estructura + DB disponible).

### V-01: `app/services/ingestion/weather.py`
Implementar `get_weather_forecast() -> WeatherSnapshot` usando Open-Meteo.  
Código base en [KNOWLEDGE_BASE.md §4.1](./KNOWLEDGE_BASE.md).  
- Cache en memoria 60 min (usar `functools.lru_cache` con TTL manual o `cachetools.TTLCache`)
- Fallback: retornar último snapshot guardado en DB si la API falla

### V-02: `app/services/ingestion/satellite.py`
Implementar `get_sst()` y `get_chlorophyll()` usando `erddapy`.  
Código base en [KNOWLEDGE_BASE.md §4.2](./KNOWLEDGE_BASE.md).  
- SST: lag 2 días (procesamiento NASA)
- Clorofila: lag 4 días, compuesto 8 días
- Fallback: baselines mensuales hardcodeados (valores en PROTOTIPO.md)

### V-03: `app/services/ingestion/alerts_ext.py`
Implementar `get_cyclone_alerts()` parseando RSS de NOAA NHC.  
Código base en [KNOWLEDGE_BASE.md §4.3](./KNOWLEDGE_BASE.md).

### V-04: `app/services/sensor_service.py`
- `process_reading(reading: SensorReading, sensor, db)` — validar + guardar en `sensor_readings`
- `get_latest_readings(db) -> list[SensorReading]` — últimas lecturas por zona
- Router `app/api/v1/routers/sensors.py` con `POST /sensors/ingest`

### V-05: `app/services/dashboard_service.py`
```python
async def get_latest_snapshot(db) -> dict:
    # 1. Obtener datos (paralelo con asyncio.gather)
    weather, satellite, sensors, alerts = await asyncio.gather(
        get_weather_forecast(),
        get_satellite_data(),
        get_latest_readings(db),
        get_cyclone_alerts(),
    )
    # 2. Calcular semáforo e IPP
    water = aggregate_sensor_readings(sensors)
    semaphore = evaluate(weather, satellite, water)
    ipp = rank_zones(water, satellite)
    # 3. Guardar daily_semaphore en DB (upsert por fecha)
    # 4. Retornar snapshot completo
    return {...}
```

### V-06: `app/api/v1/routers/data.py`
Endpoints del dashboard:
- `GET /data/latest` — snapshot actual completo
- `GET /data/history?days=30` — serie de tiempo para gráficos
- `GET /data/zones` — IPP actual por zona
- `GET /data/alerts` — alertas activas (ciclones + semáforo rojo)

### V-07: Background task de actualización
En `main.py`, usar `asyncio` para refrescar datos cada hora:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(hourly_data_refresh())  # corre en background
    yield

async def hourly_data_refresh():
    while True:
        await refresh_and_store_snapshot(...)
        await asyncio.sleep(3600)
```

---

## Diego — Validación de datos y features para ML

> Este trabajo no requiere escribir código FastAPI. Puede hacerse en Jupyter notebooks en `/notebooks/`.

### DG-01: Validar fuentes IDEAM meteorológicas
- Acceder a [datos.gov.co/resource/sbwg-7ju4.json](https://www.datos.gov.co/resource/sbwg-7ju4.json) vía `sodapy`
- Identificar estaciones con cobertura en Magdalena/Ciénaga Grande
- Documentar: ¿qué variables tienen? ¿qué calidad tienen los datos? ¿son útiles como complemento a Open-Meteo?
- Resultado: tabla con nombre estación, variables disponibles, % datos faltantes, recomendación de uso

### DG-02: Validar umbrales del semáforo con contexto local
Revisar los umbrales actuales en [KNOWLEDGE_BASE.md §5](./KNOWLEDGE_BASE.md) y contrastar con:
- Literatura científica de la Ciénaga Grande (INVEMAR, artículos)
- Conocimiento de la comunidad (vía Soe y Luis)
- Preguntas clave: ¿30 km/h es el límite real para pescadores artesanales en canoa? ¿O es menos?
- Resultado: tabla de umbrales revisados con fuentes

### DG-03: Explorar datos históricos para ML
- Descargar histórico Open-Meteo (1990–2024) para la Ciénaga
- Descargar histórico SST NASA ERDDAP (2002–2024)
- Descargar desembarcos SEPEC/AUNAP: [sepec.aunap.gov.co](http://sepec.aunap.gov.co/)
- Descargar ocurrencias GBIF: código base en [KNOWLEDGE_BASE.md §4.5](./KNOWLEDGE_BASE.md)
- Resultado: notebook con series temporales limpias + descripción de correlaciones visibles

### DG-04: Definir features del modelo de ML
Basado en DG-03, proponer:
- Variables predictoras (X): viento, SST, clorofila, salinidad, mes del año, fase lunar
- Variable objetivo (y): capturas por zona (ton/mes) o índice de abundancia
- Tipo de modelo sugerido: ¿regresión? ¿clasificación de temporada buena/mala?
- Resultado: documento `docs/ML_FEATURES.md` con justificación técnica + ambiental

### DG-05: Zonas y coordenadas geoespaciales
- Definir polígonos o puntos representativos de cada zona (para los sensores ESP32 y el dashboard)
- Herramienta sugerida: [geojson.io](https://geojson.io) para dibujar + exportar GeoJSON
- Resultado: archivo `data/zones.geojson` con las 6 zonas del IPP

---

## Dependencias entre tareas

```
Daniel:   D-01 → D-02 → D-03 → D-04 → D-05 → D-06
                                              ↓
Valentina:                              V-01 → V-02 → V-03 → V-04 → V-05 → V-06 → V-07
                                        
Diego:    DG-01   DG-02   DG-03 → DG-04   DG-05
          (paralelas, no dependen del código)
```

Diego puede trabajar desde el primer día en paralelo. Sus outputs (umbrales, features, zonas) informan las implementaciones de Valentina en V-05 y V-06.

---

## Definición de "Done" para este sprint

- [x] `GET /data/latest` retorna datos reales (no mock) de Open-Meteo + NASA ERDDAP
- [x] Sensor ESP32 puede hacer `POST /sensors/ingest` con API key y los datos quedan en Supabase
- [x] Dashboard puede consumir la API (CORS configurado, frontend Next.js desplegado)
- [x] Datos históricos disponibles en `GET /data/history`
- [ ] Diego entregó umbrales revisados y tabla de fuentes IDEAM — ver [IDEAM_GBIF_VALIDACION.md](./IDEAM_GBIF_VALIDACION.md) para estado
