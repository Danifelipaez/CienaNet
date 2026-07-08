# Arquitectura del Sistema — CienaNet Bot

## Diagrama de Alto Nivel

```
┌─────────────────┐     webhook HTTPS      ┌──────────────────────────┐
│  WhatsApp User  │ ◄──────────────────── │     Meta Cloud API        │
│  (Pescador)     │ ─────────────────────► │  (WhatsApp Business API)  │
└─────────────────┘                        └────────────┬─────────────┘
                                                        │ POST /webhook
                                                        ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        FASTAPI BACKEND                               │
│      (servidor universitario — principal · Vercel — respaldo)        │
│                                                                      │
│  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌────────────────────┐  │
│  │ /webhook  │ │ /sensors  │ │ /admin    │ │ /dashboard, /data  │  │
│  │ (Meta WA) │ │ (IoT)     │ │ (interno) │ │ (API del frontend) │  │
│  └─────┬─────┘ └─────┬─────┘ └─────┬─────┘ └─────────┬──────────┘  │
│        │             │             │                 │              │
│  ┌─────▼─────────────▼─────────────▼─────────────────▼───────────┐ │
│  │                       Capa de Servicios                        │ │
│  │  message_router · whatsapp_service · sensor_service ·          │ │
│  │  alert_service · ai_service · dashboard_service ·               │ │
│  │  points_service · sedimentation_service · system_status_service │ │
│  │  · semaphore · ipp · derived · ingestion/{weather,satellite,    │ │
│  │  alerts_ext}                                                    │ │
│  └──────────────────────────┬───────────────────────────────────--┘ │
└─────────────────────────────┼────────────────────────────────------┘
                              │
                    ┌─────────▼─────────┐
                    │    Supabase       │
                    │   (PostgreSQL)    │
                    │  - users          │
                    │  - conversations  │
                    │  - catch_reports  │
                    │  - alert_log      │
                    │  - sensors /      │
                    │    sensor_readings│
                    │  - weather_snap.  │
                    │  - satellite_data │
                    │  - external_alerts│
                    │  - sedimentation_ │
                    │    zones          │
                    │  - daily_semaphore│
                    │  - fishing_points │
                    │  - ai_conversation│
                    │  - ideam_hidro_   │
                    │    readings       │
                    └───────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                       RED DE SENSORES IoT                            │
│                                                                      │
│  [Sensor ESP32]  ──── WiFi/eSIM ────►  POST /api/v1/sensors/ingest │
│  - pH sensor                                                         │
│  - Conductivity sensor                                               │
│  - Temperature sensor (DS18B20)                                      │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                  DASHBOARD (Next.js — App Router)                    │
│         Deploy separado — servidor universitario + Vercel            │
│                                                                      │
│  frontend/app/dashboard/                                            │
│    ├── mapa/       → mapa-view.tsx (Leaflet, fishing_points/IPP)     │
│    ├── graficas/   → graficas-view.tsx (histórico ambiental)         │
│    ├── ia/         → ia-view.tsx (chat con Gemini vía /dashboard/ai) │
│    └── sistema/    → estado de fuentes de datos (system-status)      │
│                                                                      │
│  frontend/app/api/{admin,data}/*  → route handlers Next.js que      │
│  proxean al backend FastAPI (evitan exponer ADMIN_API_KEY al cliente)│
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                        CI/CD PIPELINE                                │
│                                                                      │
│  GitHub (main branch) ──► Vercel Auto Deploy ──► Respaldo/staging   │
│  GitHub (dev branch)  ──► Vercel Preview ──► Preview                │
│  Servidor universitario ──► deploy manual (ver docs/DEPLOYMENT.md)  │
│                             ──► Producción                           │
└─────────────────────────────────────────────────────────────────────┘
```

## Flujo WhatsApp (entrada de mensaje)

```
1. Pescador escribe a número de WhatsApp de CienRayas
2. Meta → POST /webhook/whatsapp con payload JSON
3. FastAPI valida firma HMAC (X-Hub-Signature-256)
4. MessageRouter identifica tipo: texto / audio / imagen / botón
5. Se procesa intención (NLU básico o proveedor de IA via AIProvider)
6. Se consulta DB para historial y datos de sensores recientes
7. Se construye respuesta (texto + botones interactivos si aplica)
8. FastAPI → Meta API → WhatsApp → pescador
9. Se guarda conversación en Supabase
```

## Flujo Sensor IoT (ingesta de datos)

```
1. ESP32 toma lectura cada N minutos
2. ESP32 → POST /api/v1/sensors/ingest (con API key en header)
3. FastAPI valida API key del sensor
4. Se almacena lectura en sensor_readings (Supabase)
5. AlertService evalúa si hay valores fuera de rango normal
6. Si hay alerta → se notifica a pescadores suscritos vía WhatsApp
```

## Despliegues disponibles

Dos destinos, misma base de código y misma Supabase — ver
[DEPLOYMENT.md](./DEPLOYMENT.md) para el cómo. `RUN_SCHEDULER` es la única
variable que difiere entre ambos (controla quién corre el loop horario de
refresco/alertas).

**Servidor universitario (principal / producción):**
- Proceso persistente (Docker o systemd+uvicorn) — sin límite de timeout por
  función, soporta WebSockets si algún día hacen falta
- Recibe el webhook real de Meta y las lecturas de los sensores ESP32
- `RUN_SCHEDULER=true` — dueño del loop horario de refresco y alertas

**Vercel (respaldo / staging):**
- Serverless, `api/index.py` (handler Mangum) + `vercel.json`
- Timeout máximo: 60s (plan Pro) / 10s (Hobby) — mantener handlers rápidos
- No hay WebSockets en serverless functions
- Cada endpoint de FastAPI se mapea como función serverless separada
- `RUN_SCHEDULER` ausente → default `false`: nunca corre el loop ni envía
  alertas: solo su cron diario existente (`vercel.json`), que refresca el
  snapshot sin enviar alertas

**Estructura de archivos para Vercel:**
```
api/
  index.py          ← entry point FastAPI (handler Mangum)
vercel.json         ← config de rutas
requirements.txt    ← dependencias Python
```

**Estructura de archivos para el servidor universitario:**
```
Dockerfile            ← backend
frontend/Dockerfile   ← dashboard
docker-compose.yml    ← orquesta ambos + Caddy (TLS automático)
Caddyfile             ← reverse proxy, api.<dominio> / dashboard.<dominio>
```

## Base de Datos — Esquema Principal

Modelos ORM reales en `app/models/` (ver también [KNOWLEDGE_BASE.md](./KNOWLEDGE_BASE.md) §2):

```sql
-- app/models/messaging.py
-- Pescador identificado por wa_id (WhatsApp)
users (id uuid PK, wa_id varchar UNIQUE, nombre varchar, comunidad varchar,
       alertas_activas bool, created_at timestamptz, last_message_at timestamptz)

-- Mensaje individual entrante/saliente de WhatsApp (nunca loggear body/wa_id)
conversations (id uuid PK, user_id uuid FK→users, ...)

-- Reporte de captura de un pescador, opcionalmente ligado a un fishing_point
catch_reports (id uuid PK, user_id uuid FK→users, fishing_point_id uuid FK→fishing_points, ...)

-- Registro de alertas enviadas (para no repetir notificaciones)
alert_log (id uuid PK, ...)

-- app/models/environmental.py
-- Sensores IoT registrados (ESP32)
sensors (id uuid PK, device_id varchar UNIQUE, api_key_hash varchar,
         location varchar, active bool, last_seen timestamptz, created_at timestamptz)

-- Lecturas puntuales de sensores
sensor_readings (id uuid PK, sensor_id uuid FK→sensors, timestamp timestamptz,
                 ph float, conductivity_mscm float, temperature_c float,
                 water_level_cm float, created_at timestamptz)

-- Snapshots meteorológicos (Open-Meteo)
weather_snapshots (id uuid PK, source varchar DEFAULT 'open-meteo',
                   timestamp timestamptz, temperature_c float,
                   wind_speed_kmh float, wind_direction_deg float,
                   precipitation_mm float, created_at timestamptz)

-- Datos satelitales diarios (NASA ERDDAP / NOAA CoastWatch, ver RESOLUCION_FUENTES.md)
satellite_data (id uuid PK, source varchar, date date,
                sst_celsius float, chlorophyll_mgm3 float, created_at timestamptz)

-- Alertas de fuentes externas (NOAA NHC, IDEAM)
external_alerts (id uuid PK, source varchar, alert_type varchar,
                 title text, description text, fetched_at timestamptz)

-- Zonas de sedimentación (monitoreo territorial)
sedimentation_zones (id uuid PK, ...)

-- Semáforo diario cacheado (ranking IPP por zona)
daily_semaphore (id uuid PK, date date UNIQUE, color varchar,
                 reason text, ipp_ranking jsonb, created_at timestamptz)

-- Respaldo propio de IDEAM en vivo (precipitación/nivel de río), guardado por el
-- cron diario (GET /data/latest) — la API pública de Socrata sigue siendo la
-- fuente de /data/history, esta tabla es solo respaldo (ver ideam_hidro.py)
ideam_hidro_readings (id uuid PK, variable varchar, estacion varchar, date date,
                      valor float, created_at timestamptz,
                      UNIQUE(variable, estacion, date))

-- app/models/fishing_points.py — conocimiento territorial comunitario
fishing_points (id uuid PK, nombre varchar, lat float, lng float,
                sal_min float, sal_max float, especies jsonb, observacion text,
                created_at timestamptz)

-- app/models/dashboard.py — historial del asistente de IA en el dashboard
ai_conversation (id uuid PK, ...)
```

## Seguridad

- Webhook Meta: validación HMAC-SHA256 obligatoria
- Sensores IoT: API key por dispositivo (hashed en DB)
- Variables sensibles: solo en variables de entorno, nunca en código
- HTTPS: forzado por Vercel
- Rate limiting: en endpoints de ingesta de sensores
