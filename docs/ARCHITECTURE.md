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
│                   (Vercel — Python Serverless)                       │
│                                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │  /webhook    │  │  /sensors    │  │  /admin                  │  │
│  │  (Meta WA)   │  │  (IoT Data)  │  │  (Dashboard interno)     │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────────────────────┘  │
│         │                 │                                          │
│  ┌──────▼─────────────────▼────────────────────────────────────┐   │
│  │                    Capa de Servicios                         │   │
│  │  MessageService │ SensorService │ AlertService │ AIService   │   │
│  └──────────────────────────┬────────────────────────────────--┘   │
└─────────────────────────────┼────────────────────────────────------┘
                              │
                    ┌─────────▼─────────┐
                    │    Supabase       │
                    │   (PostgreSQL)    │
                    │  - conversations  │
                    │  - sensor_readings│
                    │  - users          │
                    │  - alerts         │
                    └───────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                       RED DE SENSORES IoT                            │
│                                                                      │
│  [Sensor ESP32]  ──── WiFi/eSIM ────►  POST /api/sensors/ingest    │
│  - pH sensor                                                         │
│  - Conductivity sensor                                               │
│  - Temperature sensor (DS18B20)                                      │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                        CI/CD PIPELINE                                │
│                                                                      │
│  GitHub (main branch) ──► Vercel Auto Deploy ──► Production         │
│  GitHub (dev branch)  ──► Vercel Preview ──► Staging                │
└─────────────────────────────────────────────────────────────────────┘
```

## Flujo WhatsApp (entrada de mensaje)

```
1. Pescador escribe a número de WhatsApp de CienRayas
2. Meta → POST /webhook/whatsapp con payload JSON
3. FastAPI valida firma HMAC (X-Hub-Signature-256)
4. MessageRouter identifica tipo: texto / audio / imagen / botón
5. Se procesa intención (NLU básico o Claude API)
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

## Consideraciones de Despliegue en Vercel

**Limitaciones a tener en cuenta:**
- Timeout máximo: 60s (plan Pro) / 10s (Hobby) — mantener handlers rápidos
- No hay WebSockets en serverless functions
- Variables de entorno: configuradas en Vercel Dashboard
- Cada endpoint de FastAPI se mapea como función serverless separada

**Estructura de archivos para Vercel:**
```
api/
  index.py          ← entry point FastAPI (handler Mangum)
vercel.json         ← config de rutas
requirements.txt    ← dependencias Python
```

## Base de Datos — Esquema Principal

```sql
-- Pescadores registrados
users (id, phone_number, name, location, created_at, active)

-- Conversaciones WhatsApp
conversations (id, user_id, wa_message_id, direction, content, timestamp)

-- Lecturas de sensores
sensor_readings (id, sensor_id, ph, conductivity, temperature, timestamp, location_lat, location_lon)

-- Sensores registrados
sensors (id, device_id, api_key_hash, location, active, last_seen)

-- Alertas generadas
alerts (id, sensor_id, type, value, threshold, notified_users, created_at)
```

## Seguridad

- Webhook Meta: validación HMAC-SHA256 obligatoria
- Sensores IoT: API key por dispositivo (hashed en DB)
- Variables sensibles: solo en variables de entorno, nunca en código
- HTTPS: forzado por Vercel
- Rate limiting: en endpoints de ingesta de sensores
