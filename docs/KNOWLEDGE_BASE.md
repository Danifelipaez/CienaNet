# Base de Conocimiento — CienaNet Bot

> Documento de referencia rápida para el equipo de desarrollo.  
> Última actualización: 2026-06-26

---

## 1. Qué estamos construyendo (fase actual)

**Primera entrega:** Dashboard de datos ambientales para la comunidad científica de la universidad.  
**Segunda entrega:** Bot WhatsApp para pescadores artesanales.

El backend alimenta primero el dashboard con datos de fuentes externas + sensores IoT propios. El bot WhatsApp consume los mismos datos.

**Stack:** Python 3.11 + FastAPI + Supabase (PostgreSQL) + Vercel serverless (Mangum).  
Ver [STACK.md](./STACK.md) para decisiones completas.

---

## 2. Arquitectura de carpetas

```
app/
├── core/
│   ├── config.py          # Settings (pydantic-settings)
│   ├── database.py        # SQLAlchemy engine + get_db()
│   └── security.py        # HMAC Meta, API key hash, JWT
│
├── api/v1/
│   ├── routers/
│   │   ├── webhook.py     # POST /webhook/whatsapp
│   │   ├── sensors.py     # POST /sensors/ingest
│   │   ├── data.py        # GET /data/* (dashboard API)
│   │   └── admin.py       # GET /admin/*
│   └── dependencies.py    # FastAPI Depends() compartidos
│
├── services/
│   ├── whatsapp_service.py
│   ├── sensor_service.py
│   ├── alert_service.py
│   ├── ai_service.py
│   └── ingestion/         # Una carpeta para servicios de datos externos
│       ├── weather.py     # Open-Meteo
│       ├── satellite.py   # NASA ERDDAP (SST + Clorofila)
│       ├── marine.py      # Copernicus Marine (backup SST)
│       └── alerts_ext.py  # NOAA NHC ciclones
│
├── models/
│   ├── environmental.py   # ORM: sensors, sensor_readings, weather_snapshots,
│   │                      #      satellite_data, external_alerts,
│   │                      #      sedimentation_zones, daily_semaphore
│   ├── messaging.py       # ORM: users (pescadores), conversations, catch_reports, alert_log
│   ├── fishing_points.py  # ORM: fishing_points (conocimiento territorial comunitario)
│   └── dashboard.py       # ORM: ai_conversation (historial del asistente del dashboard)
│
├── schemas/
│   ├── sensor.py          # Pydantic: SensorReadingIn (payload ESP32, una lectura por request)
│   ├── environmental.py   # Pydantic: WeatherData, SatelliteSnapshot, DashboardSnapshot,
│   │                      #      HistoryResponse, etc. — respuestas de /data/*
│   └── dashboard.py       # Pydantic: AskRequest/AskResponse, AIHistoryItem — /dashboard/ai/*
│
└── main.py

api/
└── index.py               # Vercel entry point (Mangum)

frontend/                  # Dashboard Next.js (App Router), deploy Vercel separado
├── app/
│   ├── dashboard/{mapa,graficas,ia,sistema}/page.tsx
│   └── api/{admin,data}/*/route.ts   # Proxies al backend FastAPI
└── components/{map,charts,ia,ui}/
```

Regla de dependencias: `routers → services → models`. Los routers nunca tocan modelos directamente.

No existe `app/schemas/whatsapp.py` ni `app/schemas/common.py` — los payloads del webhook de Meta se leen directo del `Request` JSON en `webhook.py` (sin schema Pydantic dedicado) y no hay wrapper `APIResponse`/`Pagination` genérico todavía.

---

## 3. Fuentes de datos (validadas)

### Resumen de prioridad

| # | Fuente | Datos | Auth | Librería |
|---|--------|-------|------|----------|
| 1 | Open-Meteo | Meteo diaria + histórico desde 1940 | Sin auth | `openmeteo-requests` o `requests` |
| 2 | NASA ERDDAP | SST 1km diario desde 2002 | Sin auth | `erddapy` |
| 3 | NASA ERDDAP | Clorofila 4km/8días desde 2003 | Sin auth | `erddapy` |
| 4 | NOAA NHC RSS | Alertas ciclones tropicales | Sin auth | `feedparser` |
| 5 | IDEAM Datos Abiertos | Estaciones meteo tierra (Socrata) | Sin auth | `sodapy` |
| 6 | Copernicus Marine | SST + Clorofila NRT (backup) | Registro gratuito | `copernicusmarine` |
| 7 | SEPEC/GBIF API | Histórico desembarcos para ML | Sin auth (GBIF) | `requests` |
| 8 | Sensores ESP32 propios | Calidad agua + nivel Ciénaga | API key propia | — |

> **Nota Diego (Ing. Civil):** Calidad del agua (pH, OD, salinidad, turbidez) **no está disponible** en fuentes satelitales con resolución útil para la Ciénaga. Los sensores ESP32 propios son la única fuente en tiempo real. IDEAM DHIME agua: descartado (sin API confiable, datos inconsistentes).

---

## 4. Ejemplos de código por fuente

### 4.1 Open-Meteo — Meteorología

```python
# pip install openmeteo-requests requests-cache retry-requests
import openmeteo_requests
import requests_cache
from retry_requests import retry

cache_session = requests_cache.CachedSession('.cache', expire_after=3600)
retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
client = openmeteo_requests.Client(session=retry_session)

PARAMS = {
    "latitude": settings.cienaga_lat,   # centroide real, ver §12 — 10.859056
    "longitude": settings.cienaga_lon,  # -74.460611
    "hourly": ["temperature_2m", "wind_speed_10m", "wind_direction_10m", "precipitation"],
    "timezone": "America/Bogota",
    "forecast_days": 3
}

def get_weather_forecast() -> dict:
    responses = client.weather_api("https://api.open-meteo.com/v1/forecast", params=PARAMS)
    r = responses[0]
    hourly = r.Hourly()
    return {
        "temperature": hourly.Variables(0).ValuesAsNumpy().tolist(),
        "wind_speed": hourly.Variables(1).ValuesAsNumpy().tolist(),
        "wind_direction": hourly.Variables(2).ValuesAsNumpy().tolist(),
        "precipitation": hourly.Variables(3).ValuesAsNumpy().tolist(),
    }

# Histórico desde 1940:
HISTORICAL_URL = "https://archive-api.open-meteo.com/v1/archive"
# Mismo cliente, agregar "start_date": "2020-01-01", "end_date": "2024-12-31"
```

### 4.2 NASA ERDDAP — SST y Clorofila

```python
# pip install erddapy xarray netCDF4
from erddapy import ERDDAP

ERDDAP_SERVER = "https://coastwatch.pfeg.noaa.gov/erddap"

# Bounding box Ciénaga Grande
LAT_MIN, LAT_MAX = 10.5, 11.2
LON_MIN, LON_MAX = -74.85, -73.9

def get_sst(date_str: str) -> float:
    """Retorna SST promedio para la Ciénaga. date_str formato: '2024-01-15'"""
    e = ERDDAP(server=ERDDAP_SERVER, protocol="griddap")
    e.dataset_id = "jplMURSST41"
    e.griddap_initialize()
    e.constraints = {
        "time>=": f"{date_str}T09:00:00Z",
        "time<=": f"{date_str}T09:00:00Z",
        "latitude>=": LAT_MIN,
        "latitude<=": LAT_MAX,
        "longitude>=": LON_MIN,
        "longitude<=": LON_MAX,
    }
    e.variables = ["analysed_sst"]
    ds = e.to_xarray()
    sst_celsius = float(ds["analysed_sst"].mean()) - 273.15  # Kelvin → Celsius
    return round(sst_celsius, 2)

def get_chlorophyll(date_str: str) -> float:
    """Clorofila-a promedio (mg/m³). Usa compuesto 8 días."""
    e = ERDDAP(server=ERDDAP_SERVER, protocol="griddap")
    e.dataset_id = "erdMH1chla8day"
    e.griddap_initialize()
    e.constraints = {
        "time>=": f"{date_str}T00:00:00Z",
        "time<=": f"{date_str}T00:00:00Z",
        "latitude>=": LAT_MIN,
        "latitude<=": LAT_MAX,
        "longitude>=": LON_MIN,
        "longitude<=": LON_MAX,
    }
    e.variables = ["chlorophyll"]
    ds = e.to_xarray()
    chl = float(ds["chlorophyll"].mean())
    return round(chl, 3) if 0 < chl < 100 else 4.5  # fallback histórico
```

### 4.3 NOAA NHC — Alertas ciclones (RSS)

```python
# pip install feedparser
import feedparser
import httpx

NHC_RSS = "https://www.nhc.noaa.gov/index-at.xml"

async def get_cyclone_alerts() -> list[dict]:
    """Retorna alertas activas en el Atlántico."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(NHC_RSS)
    feed = feedparser.parse(resp.text)
    return [
        {"title": e.title, "summary": e.summary, "link": e.link}
        for e in feed.entries
        if "tropical" in e.title.lower() or "hurricane" in e.title.lower()
    ]
```

### 4.4 IDEAM — Estaciones meteorológicas (Socrata)

```python
# pip install sodapy
from sodapy import Socrata

# Dataset: Datos Hidrometeorológicos Crudos IDEAM
# https://www.datos.gov.co/resource/sbwg-7ju4.json
DOMAIN = "www.datos.gov.co"
DATASET = "sbwg-7ju4"

def get_ideam_stations_magdalena() -> list[dict]:
    client = Socrata(DOMAIN, None)  # None = sin token (hasta 1000 resultados/req)
    results = client.get(
        DATASET,
        where="departamento='MAGDALENA'",
        limit=200
    )
    return results

# Para filtrar por fecha y variable (ej: precipitacion):
# where="departamento='MAGDALENA' AND fecha_hora>='2024-01-01'"
```

### 4.5 SEPEC/GBIF — Histórico de pesca para ML

```python
# Sin librería extra, GBIF tiene API REST pública
import httpx

GBIF_API = "https://api.gbif.org/v1/occurrence/search"

async def get_fish_occurrences(species_key: int = 2346182) -> dict:
    """Obtiene registros de pesca en la Ciénaga Grande. species_key ejemplo: lisa (Mugil)"""
    async with httpx.AsyncClient() as client:
        resp = await client.get(GBIF_API, params={
            "decimalLatitude": "10.5,11.2",
            "decimalLongitude": "-74.85,-73.9",
            "taxonKey": species_key,
            "limit": 300,
        })
    return resp.json()
```

### 4.6 Sensores ESP32 — Ingesta IoT

```python
# schemas/sensor.py
from pydantic import BaseModel, field_validator
from datetime import datetime

class SensorReading(BaseModel):
    sensor_id: str
    timestamp: datetime
    ph: float | None = None
    conductivity_mscm: float | None = None  # proxy salinidad
    temperature_c: float | None = None
    water_level_cm: float | None = None

    @field_validator("ph")
    @classmethod
    def ph_range(cls, v):
        if v is not None and not (0 <= v <= 14):
            raise ValueError("pH fuera de rango")
        return v

# routers/sensors.py
from fastapi import APIRouter, Depends, HTTPException, Header
from app.services.sensor_service import process_reading
from app.schemas.sensor import SensorReading
from app.core.security import verify_sensor_api_key

router = APIRouter(prefix="/sensors", tags=["sensors"])

@router.post("/ingest", status_code=201)
async def ingest(
    reading: SensorReading,
    x_api_key: str = Header(...),
    db=Depends(get_db)
):
    sensor = await verify_sensor_api_key(x_api_key, db)
    if not sensor:
        raise HTTPException(403, "API key inválida")
    await process_reading(reading, sensor, db)
    return {"status": "ok"}
```

---

## 5. Semáforo de condiciones (lógica validada del prototipo)

```python
# services/semaphore.py
from dataclasses import dataclass

@dataclass
class SemaphoreResult:
    color: str        # "green" | "yellow" | "red"
    emoji: str
    reason: str
    safe: bool

def evaluate(weather: dict, satellite: dict, water: dict) -> SemaphoreResult:
    wind_kmh = weather.get("wind_speed", 0)
    gust_kmh = wind_kmh * 1.4   # ponytail: estimado, wttr.in no entrega ráfagas
    precip_mm = weather.get("precipitation", 0)
    oxygen = water.get("dissolved_oxygen_mgl")

    # ROJO
    if wind_kmh > 30 or gust_kmh > 45 or precip_mm > 10:
        return SemaphoreResult("red", "🔴", "Viento o lluvia peligrosa", False)
    if oxygen and oxygen < 3.0:
        return SemaphoreResult("red", "🔴", "Oxígeno disuelto crítico", False)

    # AMARILLO
    sst = satellite.get("sst_celsius", 28)
    salinity = water.get("salinity_psu", 15)
    turbidity = water.get("turbidity_ntu", 50)
    if not (25 <= sst <= 32) or salinity > 32 or turbidity > 120:
        return SemaphoreResult("yellow", "🟡", "Condiciones de precaución", True)
    if oxygen and 3.0 <= oxygen <= 4.5:
        return SemaphoreResult("yellow", "🟡", "Oxígeno bajo, precaución", True)

    return SemaphoreResult("green", "🟢", "Condiciones favorables", True)
```

---

## 6. Índice de Potencial Pesquero (IPP)

```python
# services/ipp.py
WEIGHTS = {"oxygen": 0.25, "sst": 0.20, "salinity": 0.20,
           "chlorophyll": 0.15, "turbidity": 0.10, "ph": 0.10}

ZONES = [
    {"name": "Boca de la Barra",       "sal_min": 20, "sal_max": 36},
    {"name": "Nueva Venecia",           "sal_min":  8, "sal_max": 22},
    {"name": "Buenavista",             "sal_min":  5, "sal_max": 18},
    {"name": "Caño Clarín",            "sal_min":  2, "sal_max": 12},
    {"name": "Tasajera/Puebloviejo",   "sal_min":  3, "sal_max": 15},
    {"name": "Suroccidente",           "sal_min":  0, "sal_max":  8},
]

def _score_oxygen(v: float) -> float:
    if v >= 8: return 100
    if v >= 4.5: return 60
    if v >= 3: return 20
    return 0

def _score_sst(v: float) -> float:
    return 100 if 26 <= v <= 30 else (60 if 24 <= v <= 32 else 20)

def _score_salinity(v: float, zone_min: float, zone_max: float) -> float:
    return 100 if zone_min <= v <= zone_max else 0

def _score_chlorophyll(v: float) -> float:
    return min(100, v * 10)  # escala simple; >10 mg/m³ = saturación

def _score_turbidity(v: float) -> float:
    return 100 if v < 30 else (60 if v < 80 else 20)

def _score_ph(v: float) -> float:
    return 100 if 7.0 <= v <= 8.5 else 30

def calculate_ipp(water: dict, satellite: dict, zone: dict) -> float:
    scores = {
        "oxygen":     _score_oxygen(water.get("dissolved_oxygen_mgl", 6)),
        "sst":        _score_sst(satellite.get("sst_celsius", 28)),
        "salinity":   _score_salinity(water.get("salinity_psu", 15),
                                       zone["sal_min"], zone["sal_max"]),
        "chlorophyll":_score_chlorophyll(satellite.get("chlorophyll_mgm3", 4.5)),
        "turbidity":  _score_turbidity(water.get("turbidity_ntu", 50)),
        "ph":         _score_ph(water.get("ph", 7.5)),
    }
    return round(sum(scores[k] * WEIGHTS[k] for k in WEIGHTS), 1)

def rank_zones(water: dict, satellite: dict) -> list[dict]:
    results = [{"zone": z["name"], "ipp": calculate_ipp(water, satellite, z)} for z in ZONES]
    return sorted(results, key=lambda x: x["ipp"], reverse=True)
```

---

## 7. Schema de base de datos

```sql
-- Lecturas de sensores IoT propios
sensor_readings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sensor_id UUID REFERENCES sensors(id),
    timestamp TIMESTAMPTZ NOT NULL,
    ph FLOAT,
    conductivity_mscm FLOAT,
    temperature_c FLOAT,
    water_level_cm FLOAT,
    created_at TIMESTAMPTZ DEFAULT now()
)

-- Snapshots meteorológicos (Open-Meteo)
weather_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source VARCHAR(50) DEFAULT 'open-meteo',
    timestamp TIMESTAMPTZ NOT NULL,
    temperature_c FLOAT,
    wind_speed_kmh FLOAT,
    wind_direction_deg FLOAT,
    precipitation_mm FLOAT,
    created_at TIMESTAMPTZ DEFAULT now()
)

-- Datos satelitales (NASA ERDDAP)
satellite_data (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source VARCHAR(50),             -- 'nasa_mur' | 'modis_aqua' | 'copernicus'
    date DATE NOT NULL,
    sst_celsius FLOAT,
    chlorophyll_mgm3 FLOAT,
    created_at TIMESTAMPTZ DEFAULT now()
)

-- Alertas externas (NOAA NHC, IDEAM)
external_alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source VARCHAR(50),
    alert_type VARCHAR(100),
    title TEXT,
    description TEXT,
    fetched_at TIMESTAMPTZ DEFAULT now()
)

-- Semáforo calculado (caché de resultado diario)
daily_semaphore (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    date DATE UNIQUE NOT NULL,
    color VARCHAR(10),
    reason TEXT,
    ipp_ranking JSONB,              -- lista de zonas ordenadas
    created_at TIMESTAMPTZ DEFAULT now()
)
```

---

## 8. Endpoint del dashboard (ejemplo)

```python
# api/v1/routers/data.py
from fastapi import APIRouter, Depends
from app.services.dashboard_service import get_latest_snapshot

router = APIRouter(prefix="/data", tags=["dashboard"])

@router.get("/latest")
async def latest_conditions(db=Depends(get_db)):
    """Retorna el estado ambiental más reciente para el dashboard."""
    return await get_latest_snapshot(db)

# Respuesta ejemplo:
# {
#   "semaphore": {"color": "green", "reason": "Condiciones favorables"},
#   "weather": {"wind_speed_kmh": 12, "temp_c": 28, "precipitation_mm": 0},
#   "satellite": {"sst_celsius": 27.4, "chlorophyll_mgm3": 3.8, "date": "2026-06-24"},
#   "sensors": [{"zone": "Boca de la Barra", "ph": 7.8, "temp_c": 29.1}],
#   "ipp_ranking": [{"zone": "Caño Clarín", "ipp": 82.5}, ...],
#   "cyclone_alerts": [],
#   "updated_at": "2026-06-26T14:30:00Z"
# }
```

---

## 9. Variables de entorno requeridas

Fuente de verdad: [.env.example](../.env.example) y `Settings` en `app/core/config.py` (los nombres deben coincidir exactamente, `pydantic-settings` los mapea case-insensitive a snake_case).

```bash
# Base de datos Supabase — nombres generados por la integración Vercel-Supabase, no renombrar
POSTGRES_PRISMA_URL=          # Pooler de transacción, puerto 6543 — runtime de la app
POSTGRES_URL_NON_POOLING=     # Conexión directa, puerto 5432 — solo Alembic

# Meta WhatsApp
WHATSAPP_TOKEN=
WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_VERIFY_TOKEN=
WHATSAPP_APP_SECRET=          # Para HMAC

# Supabase API
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=

# IA / NLU — Google AI Studio / Gemini (ver app/services/ai_service.py, GeminiProvider)
AI_API_KEY=                   # Vacío = stub sin IA
AI_MODEL=gemini-flash-lite-latest
AI_HISTORY_TURNS=10           # Mensajes previos que se mandan como contexto

# Copernicus Marine (opcional, no usado en el flujo actual — clorofila migró a NOAA CoastWatch/Sentinel-3, ver RESOLUCION_FUENTES.md)
COPERNICUSMARINE_SERVICE_USERNAME=
COPERNICUSMARINE_SERVICE_PASSWORD=

# App
ENVIRONMENT=development
SENSOR_API_KEY_SECRET=        # Salt para hashear API keys ESP32
ADMIN_API_KEY=change-me       # Protege /admin/* (registro de sensores) y los proxies del dashboard

# Coordenadas (defaults en config.py, no secretos — centroide real, ver §12)
CIENAGA_LAT=10.859056
CIENAGA_LON=-74.460611
```

---

## 10. Guardrails de seguridad (no negociables)

1. **HMAC obligatorio** en cada POST a `/webhook/whatsapp` — verificar antes de parsear el body
2. **API key por sensor** — hashear con `hashlib.pbkdf2_hmac` antes de guardar en DB
3. **Responder 200 inmediatamente** al webhook de Meta, procesar en background task
4. **Deduplicar por `message_id`** con TTL 10 minutos (Meta reenvía webhooks)
5. **Nunca loggear** números de teléfono completos ni contenido de mensajes
6. **Type hints + Pydantic** en todos los inputs externos

---

## 11. Librerías a instalar (additions al prototipo)

```
# Nuevas vs prototipo
erddapy>=0.8          # NASA ERDDAP
openmeteo-requests>=0.2
feedparser>=6.0       # NOAA NHC RSS
sodapy>=2.2           # IDEAM Socrata
copernicusmarine>=1.0 # Backup Copernicus (opcional)
sqlalchemy>=2.0
alembic>=1.13
# SDK de IA: agregar el del proveedor elegido (ej: groq, openai, anthropic, etc.)
mangum>=0.19          # Vercel
```

---

## 12. Coordenadas georreferenciadas de la Ciénaga Grande

Puntos medidos en campo/equipo (no estimados), convertidos de DMS a decimal.
La Ciénaga tiene forma aproximada de triángulo apuntando hacia el sur.

| Punto | DMS | Decimal (lat, lon) | Uso |
|-------|-----|---------------------|-----|
| Vértice NE (Embarcadero Tasajera) | 10°58'34.0"N 74°19'33.0"W | 10.976111, -74.325833 | Extremo norte/derecho del triángulo |
| Vértice Sur | 10°32'37"N 74°30'36"W | 10.543611, -74.510000 | Punta sur del triángulo |
| Vértice NW | 11°00'34"N 74°40'55"W | 11.009444, -74.681944 | Extremo norte/izquierdo del triángulo |
| Centroide | 10°51'32.6"N 74°27'38.2"W | 10.859056, -74.460611 | Usado como `CIENAGA_LAT`/`CIENAGA_LON` (ver `app/core/config.py`) |
| Buenavista (palafito) | 10°50'28.8"N 74°30'36.5"W | 10.841333, -74.510139 | Pueblo palafítico de referencia |
| Nueva Venecia (palafito) | 10°49'43.3"N 74°34'28.2"W | 10.828694, -74.574500 | Pueblo palafítico de referencia |

Notas:
- El bounding box de NASA ERDDAP (`app/services/ingestion/satellite.py`, `LAT_MIN/MAX = 10.5/11.2`, `LON_MIN/MAX = -74.85/-73.9`) ya cubre los 3 vértices reales, no requiere cambios.
- `CIENAGA_LAT`/`CIENAGA_LON` (config.py y `.env.example`) se actualizaron de `10.8, -74.4` (aproximado) al centroide real `10.859056, -74.460611`.
- Los puntos de pesca en `alembic/versions/003_fishing_points.py` (incluyendo un punto llamado "Tasajera" en `10.972, -74.434`) son datos comunitarios ilustrativos, no coinciden con estas coordenadas medidas — pendiente de validar/corregir con el equipo territorial si se requiere precisión geográfica real en ese seed data.

---

## Referencias

- [FastAPI Bigger Applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/)
- [erddapy docs](https://ioos.github.io/erddapy/)
- [Open-Meteo API](https://open-meteo.com/en/docs)
- [NOAA NHC RSS](https://www.nhc.noaa.gov/aboutrss.shtml)
- [IDEAM Datos Abiertos Socrata](https://www.datos.gov.co/resource/sbwg-7ju4.json)
- [Copernicus Marine Python](https://pypi.org/project/copernicusmarine/)
- [GBIF Occurrence API](https://api.gbif.org/v1/occurrence/search)
- [SEPEC AUNAP desembarcos](http://sepec.aunap.gov.co/)
- [docs/PROTOTIPO.md](./PROTOTIPO.md) — lógica validada del prototipo
- [docs/ADR-001-arquitectura-backend.md](./ADR-001-arquitectura-backend.md) — decisiones de arquitectura
