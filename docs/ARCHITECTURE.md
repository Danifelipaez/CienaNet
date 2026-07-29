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
│                     (servidor universitario)                         │
│                                                                      │
│  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌────────────────────┐  │
│  │ /webhook  │ │ /sensors  │ │ /admin    │ │ /dashboard, /data  │  │
│  │ (Meta WA) │ │ (IoT)     │ │ (interno) │ │ (API del frontend) │  │
│  └─────┬─────┘ └─────┬─────┘ └─────┬─────┘ └─────────┬──────────┘  │
│        │             │             │                 │              │
│  ┌─────▼─────────────▼─────────────▼─────────────────▼───────────┐ │
│  │                       Capa de Servicios                        │ │
│  │  message_router · whatsapp_service · sensor_service ·          │ │
│  │  alert_service · ai_service · dashboard_service (ESCRITURA:     │ │
│  │  llama APIs externas + persiste) · snapshot_service (LECTURA:   │ │
│  │  lee lo ya persistido, cero red — usado por el bot y el mapa) · │ │
│  │  points_service · sedimentation_service · system_status_service │ │
│  │  · semaphore · ipp · derived · trends (tendencias 24h/7d) ·     │ │
│  │  signals (anoxia, pulso de agua dulce — estimaciones) ·         │ │
│  │  ingestion/{weather,satellite,alerts_ext,ideam_hidro}           │ │
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
│    Repo separado (CienaRed-Frontend) — deploy en Vercel              │
│                                                                      │
│  app/dashboard/                                                      │
│    ├── mapa/       → mapa-view.tsx (Leaflet, fishing_points/IPP)     │
│    ├── graficas/   → graficas-view.tsx (histórico ambiental)         │
│    ├── ia/         → ia-view.tsx (chat con Gemini vía /dashboard/ai) │
│    └── sistema/    → estado de fuentes de datos (system-status)      │
│                                                                      │
│  app/api/{admin,data}/*  → route handlers Next.js que proxean al    │
│  backend FastAPI (BACKEND_URL) — evitan exponer ADMIN_API_KEY al     │
│  cliente                                                             │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                        CI/CD PIPELINE                                │
│                                                                      │
│  GitHub (CienaRed-Frontend, main) ──► Vercel Auto Deploy ──► Prod    │
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
5. Se procesa intención por palabra clave: saludo, condición del agua,
   dónde pesco, alertas on/off, reporte de captura — o cae a AIProvider
   (Gemini) para texto libre
6. Para condición/dónde-pesco: snapshot_service.read_persisted() lee el
   último estado YA persistido (cero llamadas a APIs externas, cero
   escrituras) — lo refresca el scheduler horario, no el mensaje del
   pescador. dashboard_service.get_latest_snapshot() (el camino que SÍ
   llama APIs externas y persiste) solo lo usan el scheduler y
   GET /data/latest, nunca el bot
7. Se construye respuesta corta (3-4 oraciones, sin jerga)
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

Backend y frontend viven en repos separados y se despliegan cada uno en un
único destino — ver [DEPLOYMENT.md](./DEPLOYMENT.md) para el cómo.

**Backend — servidor universitario (único destino, producción):**
- Proceso persistente (Docker o systemd+uvicorn) — sin límite de timeout por
  función, soporta WebSockets si algún día hacen falta
- Recibe el webhook real de Meta y las lecturas de los sensores ESP32
- `RUN_SCHEDULER=true` en prod (dueño del loop horario de refresco y
  alertas), `false` por defecto en local dev

**Frontend — Vercel (único destino), repo separado `CienaRed-Frontend`:**
- Next.js App Router, deploy automático desde ese repo
- `BACKEND_URL` apunta a la URL pública HTTPS del backend (`https://api.<dominio>`)

**Estructura de archivos para el servidor universitario:**
```
Dockerfile            ← backend
docker-compose.yml    ← orquesta backend + Caddy (TLS automático)
Caddyfile             ← reverse proxy, api.<dominio>
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

-- Snapshots meteorológicos (Open-Meteo) — estacion/humidity_pct: migración 010;
-- wind_gust_kmh (ráfaga real, wind_gusts_10m): migración 011
weather_snapshots (id uuid PK, source varchar DEFAULT 'open-meteo',
                   estacion varchar DEFAULT 'CGSM', timestamp timestamptz,
                   temperature_c float, humidity_pct float,
                   wind_speed_kmh float, wind_direction_deg float,
                   wind_gust_kmh float, precipitation_mm float, created_at timestamptz)

-- Datos satelitales diarios (NASA ERDDAP / NOAA CoastWatch, ver RESOLUCION_FUENTES.md)
-- por_zona: migración 012 — desglose por las 6 zonas IPP, aditivo sobre las
-- columnas escalares (media del box). sst_celsius/chlorophyll_mgm3 quedan NULL
-- si la fuente cayó a baseline — nunca se persiste un baseline como medición.
satellite_data (id uuid PK, source varchar, date date,
                sst_celsius float, chlorophyll_mgm3 float, por_zona jsonb,
                created_at timestamptz)

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
- HTTPS: forzado por Caddy (backend) y Vercel (frontend, repo separado)
- Rate limiting: en endpoints de ingesta de sensores
