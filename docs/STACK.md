# Stack Técnico — CienaNet Bot

## Decisiones de Stack

### Backend: Python + FastAPI
**Por qué FastAPI sobre alternativas:**
- Tipado estático con Pydantic → menos bugs en runtime
- Documentación automática (Swagger/OpenAPI) — útil para que el equipo y la IA entiendan los endpoints
- Rendimiento superior a Flask; comparable a Node.js
- Ecosistema Python para datos (pandas, numpy) — útil cuando integremos datos satelitales
- Curva de aprendizaje baja para el equipo (Valentina ya conoce Python)

**Librería de adaptador para Vercel:** `mangum` (adapta ASGI → AWS Lambda / Vercel serverless)

### Plataforma: Vercel
**Por qué Vercel:**
- Deploy automático desde GitHub en cada push a `main`
- Preview deployments en PRs (staging automático)
- Free tier generoso para MVP
- Variables de entorno gestionadas en dashboard
- HTTPS automático

**Alternativa si Vercel se queda corto:** Railway o Render (mejor soporte para procesos persistentes)

**Actualización:** el servidor universitario es ahora el deployment principal
de producción (recibe el webhook de Meta y corre el scheduler); Vercel pasó a
ser respaldo/staging. Ver [DEPLOYMENT.md](./DEPLOYMENT.md).

### Base de Datos: Supabase (PostgreSQL)
**Por qué Supabase:**
- PostgreSQL completo (no NoSQL con limitaciones)
- Free tier: 500MB, suficiente para MVP
- SDK de Python oficial
- Row Level Security integrado
- Dashboard visual — útil para Diego y Soe para explorar datos sin código

**ORM:** SQLAlchemy 2.0 + Alembic para migraciones

### WhatsApp: Meta Cloud API (oficial)
**Por qué API oficial de Meta sobre alternativas (Twilio, etc.):**
- Sin intermediarios ni costos adicionales por mensaje (solo costos Meta)
- Acceso a todas las funcionalidades: botones, listas, plantillas, audio
- Número propio con eSIM
- Webhooks directos a nuestro backend

**Autenticación:** Token permanente de System User (no token de usuario de 60 días)

### Frontend: Next.js (App Router) + Leaflet
Dashboard científico, deploy Vercel separado del backend (`frontend/`, repo mismo, proyecto Vercel distinto):
- **Next.js 16 (App Router) + TypeScript + React 19** — rutas `dashboard/{mapa,graficas,ia,sistema}`
- **Leaflet** — mapa interactivo de puntos de pesca / zonas IPP (`components/map/`)
- **Route handlers propios** (`frontend/app/api/{admin,data}/*`) — proxean al backend FastAPI en vez de exponer `ADMIN_API_KEY` al navegador
- No usa un SDK de gráficos externo pesado; charts en `components/charts/` sobre datos de `/data/history`

### CI/CD: GitHub Actions + Vercel + deploy manual (universidad)
```
Push a main → Vercel auto-deploy (respaldo/staging)
Push a dev  → Vercel preview deploy (staging)
PR abierto  → Tests en GitHub Actions → Preview deploy
Servidor universitario → deploy manual (git pull + docker compose up -d --build), ver DEPLOYMENT.md
```

### IoT: Arduino + ESP32
- **Microcontrolador:** ESP32 (WiFi + BLE integrado, bajo costo ~$5)
- **Sensores:**
  - pH: electrodo analógico + módulo amplificador
  - Conductividad: electrodo de conductividad (EC)
  - Temperatura: DS18B20 (sonda digital waterproof)
- **Conectividad:** WiFi local o eSIM (SIM7600) para zonas sin WiFi
- **Protocolo hacia API:** HTTP POST con JSON + API key en header
- **Firmware:** Arduino IDE / PlatformIO

### IA / NLU: Google Gemini (AI Studio)
Para procesar mensajes de texto libre en WhatsApp y las respuestas del asistente del dashboard:
- Uso: clasificar intención del pescador, generar respuestas naturales, responder preguntas en el dashboard (`/dashboard/ai/ask`)
- Fallback: respuestas predefinidas si `AI_API_KEY` está vacío (stub, sin IA)
- La interfaz está en `app/services/ai_service.py` (`AIProvider` Protocol); la implementación activa es `GeminiProvider`, vía REST directo (httpx), sin SDK de Google
- Modelo configurado en `AI_MODEL` (default `gemini-flash-lite-latest`, ajustar al id exacto de AI Studio)
- Historial de contexto: últimos `AI_HISTORY_TURNS` mensajes (default 10)
- El Protocol sigue permitiendo cambiar de proveedor en `get_ai_provider()` sin tocar el resto del código, pero hoy solo hay una implementación concreta (Gemini)

## Versiones Específicas

```
python              >= 3.11
fastapi             >= 0.115
uvicorn[standard]   >= 0.32
mangum              >= 0.19
pydantic            >= 2.9
pydantic-settings   >= 2.5
sqlalchemy          >= 2.0
asyncpg             >= 0.30   # driver async PostgreSQL
psycopg2-binary     >= 2.9    # driver sync (Alembic)
alembic             >= 1.13
supabase            >= 2.9
httpx               >= 0.27   # cliente HTTP async para Meta API
python-dotenv       >= 1.0
# IA: sin SDK — Gemini se llama por REST directo (httpx) desde ai_service.py
pytest              >= 8.0
pytest-asyncio      >= 0.24
```

## Variables de Entorno Requeridas

```bash
# Base de datos Supabase — dos URLs por modelo serverless
# (nombres generados por la integración Vercel-Supabase, config.py los lee tal cual):
POSTGRES_PRISMA_URL=       # Puerto 6543 (transaction pooler) — runtime de la app
POSTGRES_URL_NON_POOLING=  # Puerto 5432 (directa) — solo para migraciones Alembic

# Supabase API
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=

# Meta WhatsApp API
WHATSAPP_TOKEN=           # Token de acceso permanente (System User)
WHATSAPP_PHONE_NUMBER_ID= # ID del número registrado en Meta
WHATSAPP_VERIFY_TOKEN=    # Token para verificación de webhook
WHATSAPP_APP_SECRET=      # Para validación HMAC de webhooks

# IA / NLU (Google AI Studio / Gemini)
AI_API_KEY=
AI_MODEL=gemini-flash-lite-latest
AI_HISTORY_TURNS=10

# App
ENVIRONMENT=              # development | staging | production
SENSOR_API_KEY_SECRET=    # Salt para hashear API keys de sensores
RUN_SCHEDULER=            # true SOLO en el deployment dueño del scheduler (ver DEPLOYMENT.md)
```

## Lo que NO usamos y por qué

| Tecnología | Razón de descarte |
|------------|-------------------|
| Next.js / Node como **backend** | El equipo domina Python; no hay ventaja real. (Next.js sí se usa para el **frontend** — dashboard en `frontend/`, deploy Vercel separado — eso es una decisión distinta, no contradice esto) |
| Twilio WhatsApp | Costo adicional por mensaje; somos estudiantes |
| Firebase | Vendor lock-in, pricing impredecible |
| MongoDB | SQL es mejor para datos de series temporales de sensores |
| AWS Lambda directo | Vercel abstrae esto sin perder flexibilidad |
| Django | Demasiado framework para una API; FastAPI es suficiente |
