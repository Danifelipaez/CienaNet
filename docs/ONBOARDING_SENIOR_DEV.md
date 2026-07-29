# Onboarding — CienaNet Bot

Referencia técnica para un dev senior nuevo en el repo. Contexto de negocio,
equipo y planificación histórica viven en [`CONTEXT.md`](./CONTEXT.md),
[`TAREAS_EQUIPO.md`](./TAREAS_EQUIPO.md) y [`PLAN_DANIEL.md`](./PLAN_DANIEL.md)
— no se repiten aquí.

---

## 1. Qué es

Backend FastAPI que expone datos ambientales de la Ciénaga Grande de Santa
Marta por dos canales: un bot de WhatsApp (Meta Cloud API) para pescadores
artesanales, y una API de dashboard consumida por un frontend Next.js en
repo separado (`CienaRed-Frontend`, deploy Vercel). Combina una red propia de
sensores ESP32 con Open-Meteo, NASA/NOAA ERDDAP e IDEAM.

Implicación de producto que sí afecta código: las respuestas del bot deben
ser cortas (3-4 oraciones), sin jerga técnica y con una recomendación
concreta (`app/services/condicion_message.py`, `message_router.py`).

Proyecto universitario en fase MVP, código escrito con asistencia intensiva
de IA — guardrails vinculantes en [`GUARDRAILS.md`](./GUARDRAILS.md) y
[`VIBECODING.md`](./VIBECODING.md).

---

## 2. Stack

| Pieza | Elegido |
|---|---|
| Backend | Python 3.11, FastAPI |
| DB | Supabase (PostgreSQL) |
| ORM | SQLAlchemy 2.0 async + Alembic |
| WhatsApp | Meta Cloud API oficial |
| IA/NLU | Google Gemini vía REST directo (`httpx`, sin SDK), detrás de un `Protocol AIProvider` en `ai_service.py` |
| Frontend | Next.js 16 (App Router), TypeScript, React 19, Leaflet — repo separado |
| Deploy backend | Servidor universitario (Docker o systemd+uvicorn), proceso persistente |
| IoT | ESP32 + pH/EC/DS18B20, ~$110 USD/nodo |

Versiones exactas, variables de entorno y alternativas descartadas (Twilio,
Firebase, MongoDB, Django, Vercel serverless para el backend):
[`STACK.md`](./STACK.md).

---

## 3. Estructura y regla de dependencias

```
app/
├── api/v1/routers/   # webhook.py, sensors.py, data.py, admin.py, dashboard.py — solo HTTP
├── api/v1/dependencies.py  # auth: API key sensores, admin, sesión DB
├── services/          # toda la lógica de negocio
│   ├── message_router.py, condicion_message.py, whatsapp_service.py, ai_service.py
│   ├── sensor_service.py, alert_service.py, semaphore.py, ipp.py  # IPP: ranking de zonas por potencial de pesca
│   ├── dashboard_service.py       # get_latest_snapshot() — camino de ESCRITURA
│   ├── dashboard_persistence.py, dashboard_history.py, ai_context.py
│   ├── snapshot_service.py        # read_persisted() — camino de LECTURA (bot, mapa)
│   ├── trends.py, signals.py      # tendencias y estimaciones sobre lo persistido
│   ├── points_service.py, sedimentation_service.py
│   ├── system_status_service.py, derived.py
│   └── ingestion/      # weather.py, satellite.py, alerts_ext.py, ideam_hidro.py
├── models/             # SQLAlchemy ORM: environmental.py, messaging.py, fishing_points.py, dashboard.py
├── schemas/            # Pydantic: sensor.py, environmental.py, dashboard.py
├── core/               # config.py, database.py, security.py
└── main.py             # app, lifespan, routers, CORS, /health

tests/            # pytest, un archivo por servicio/router crítico
alembic/versions/  # 12 migraciones aplicadas (001..012)
```

Regla no negociable (ver [`ADR-001`](./ADR-001-arquitectura-backend.md)):

```
routers → services → models
routers → schemas   (solo input/output)
services → core/

PROHIBIDO: routers → models directo · models → services · services → routers
```

Lógica de negocio en un router, o query directa a DB fuera de `services/`,
es un defecto a corregir antes de agregar funcionalidad nueva.

Convenciones: archivos >~300 líneas se dividen en módulos, type hints en
todo, Pydantic para todo input externo, nunca `print()` (usar `logging`),
código y comentarios en inglés, mensajes al pescador en español simple, PRs
~200 líneas de diff.

---

## 4. Modelo de datos

| Tabla | Modelo | Contenido |
|---|---|---|
| `users` | `messaging.py` | Pescador por `wa_id` (WhatsApp) |
| `conversations` | `messaging.py` | Mensajes entrantes/salientes (`body` nunca se loggea) |
| `catch_reports` | `messaging.py` | Reporte de captura, opcionalmente ligado a `fishing_points` |
| `alert_log` | `messaging.py` | Alertas ya enviadas (evita reenvíos) |
| `sensors` | `environmental.py` | Sensores ESP32, `api_key_hash` |
| `sensor_readings` | `environmental.py` | pH, conductividad, temperatura, nivel de agua |
| `weather_snapshots` | `environmental.py` | Snapshots Open-Meteo |
| `satellite_data` | `environmental.py` | SST y clorofila (NASA/NOAA ERDDAP) |
| `external_alerts` | `environmental.py` | Alertas NOAA NHC / IDEAM |
| `sedimentation_zones` | `environmental.py` | Monitoreo territorial |
| `daily_semaphore` | `environmental.py` | Semáforo + ranking IPP, cacheado por día |
| `ideam_hidro_readings` | `environmental.py` | Respaldo propio de IDEAM en vivo |
| `fishing_points` | `fishing_points.py` | Zonas/especies, conocimiento comunitario |
| `ai_conversation` | `dashboard.py` | Historial del chat de IA del dashboard |

DDL completo: [`ARCHITECTURE.md`](./ARCHITECTURE.md) · [`KNOWLEDGE_BASE.md`](./KNOWLEDGE_BASE.md) §7.

---

## 5. Flujos end-to-end

**Mensaje de WhatsApp entrante**
```
Meta → POST /api/v1/webhook/whatsapp
  1. verify_hmac_meta() valida X-Hub-Signature-256 (app/core/security.py)
  2. MessageRouter identifica tipo (texto/audio/imagen/botón)
  3. Intención por palabra clave: saludo, condición, dónde pesco,
     alertas on/off, reporte de captura — o AIProvider si es texto libre
  4. condición/dónde-pesco → snapshot_service.read_persisted(): cero red,
     cero escritura. NO usar get_latest_snapshot() aquí.
  5. Respuesta corta en español vía Meta API, se guarda en Supabase
```

**Ingesta de sensor IoT**
```
ESP32 → POST /api/v1/sensors/ingest  (X-Api-Key, una lectura por request)
  1. get_current_sensor() valida la key contra el hash en DB
  2. SensorReadingIn valida rango (conductividad 0-80 mS/cm, nivel 0-500 cm) → 422 si no
  3. process_reading() persiste en sensor_readings
  4. async: semaphore.py + alert_service.py evalúan snapshot agregado y
     disparan WhatsApp si aplica. get_latest_readings() filtra por sensor
     activo y antigüedad máx. 6h.
```

**Refresco horario** — `app/main.py::_hourly_refresh()`, activo solo si
`settings.run_scheduler` (un único deployment corriendo el loop, ver §7.1).
Llama `dashboard_service.get_latest_snapshot()` (clima + satélite + sensores
+ IPP + tendencias + señales) y `alert_service.maybe_send_alert()`.

**IPP** (Índice de Potencial Pesquero) es un score 0-100 por zona
(`ipp.py::ZONES`, 6 zonas), calculado a partir de las señales disponibles
(SST, clorofila, viento, agua) ponderadas y renormalizadas solo sobre las que
tienen dato real (`cobertura`, 0.0-1.0, indica esa fracción). Se cachea una
vez al día en `daily_semaphore` y es la base del ranking que responde "dónde
pesco" en el bot y el mapa del dashboard. Fórmula completa:
[`KNOWLEDGE_BASE.md`](./KNOWLEDGE_BASE.md).

---

## 6. API

Prefijo `/api/v1` en todo excepto `/health`. Schemas exactos en Swagger
(`/docs`, autogenerado) — esta tabla cubre solo lo que Swagger no dice: auth
y comportamiento no obvio.

| Endpoint | Auth | Notas |
|---|---|---|
| `GET /webhook/whatsapp` | query `hub.verify_token` | Verificación inicial de Meta, una sola vez |
| `POST /webhook/whatsapp` | `X-Hub-Signature-256` (HMAC-SHA256) | Sin schema Pydantic, se lee del `Request` crudo. Solo procesa `type: text`; audio/imagen/botón/lista se ignoran (deliberado, ver `ponytail:` en el archivo). Responde `200 {"status":"ok"}` siempre, incluso si falla un mensaje individual — Meta reintenta agresivo si no recibe 200 |
| `POST /sensors/ingest` | `X-Api-Key` (PBKDF2 contra `sensors.api_key_hash`) | Una lectura por request, no batch. `422` si un campo está fuera de rango físico |
| `GET /data/latest` | ninguna | `DashboardSnapshot`. `salinity_psu`/`tds_mgl` son derivados (`derived.py`), no crudos. `origen` marca cada fuente como medido/cache/baseline/sin_dato — un valor baseline nunca se persiste como medición real |
| `GET /data/history?days=` | ninguna | 1-365, default 30. Series independientes, no alineadas por timestamp entre sí |
| `GET /data/zones` | ninguna | dict plano, sin schema tipado |
| `GET /data/alerts` | ninguna | combina llamada en vivo a NOAA NHC con alertas ya persistidas |
| `POST/GET /admin/sensors` | `X-Admin-Key` | `raw_api_key` se muestra una única vez al crear; no hay endpoint para recuperarla, solo rotar |
| `GET /dashboard/points`, `/species`, `/sedimentation` | ninguna | solo lectura, sin datos sensibles |
| `POST /dashboard/ai/ask` | `X-Admin-Key` + `X-User-Id` | `X-User-Id` es un UUID que genera el frontend (`localStorage`), no autenticación — no hay login de usuario todavía |
| `GET/DELETE /dashboard/ai/history*` | `X-Admin-Key` + `X-User-Id` | acotado al `user_id` del header |
| `GET /dashboard/system-status` | `X-Admin-Key` | `estado` por antigüedad del dato (umbral distinto por fuente); no hay métrica de latencia real |
| `GET /health` | ninguna | sin prefijo `/api/v1`, para healthcheck de Docker/systemd |

Ejemplos completos de request/response: [`WHATSAPP_API.md`](./WHATSAPP_API.md),
[`ARCHITECTURE.md`](./ARCHITECTURE.md).

---

## 7. Seguridad — no negociable

1. HMAC-SHA256 en todo request al webhook de Meta, validado antes de tocar
   el body (`verify_hmac_meta()`).
2. Nunca loggear contenido de mensajes, números de teléfono completos, ni
   tokens/API keys.
3. API key por sensor, hasheada con PBKDF2 — revocar una no afecta a otras.
4. Variables sensibles solo en `.env`.
5. Toda data externa se valida con Pydantic en el borde.
6. `ADMIN_API_KEY` protege `/admin/*` y los proxies del dashboard — mismo
   valor en `.env` backend y `.env.local` de `CienaRed-Frontend`; las
   llamadas dashboard→backend son siempre servidor-a-servidor.

Checklist de revisión antes de commitear código generado por IA:
[`GUARDRAILS.md`](./GUARDRAILS.md).

### 7.1 `RUN_SCHEDULER`

Un único proceso persistente en producción. `RUN_SCHEDULER=true` activa el
loop horario (refresco + alertas); en local queda `false` por defecto.
`pg_advisory_xact_lock` en `alert_service.py::maybe_send_alert()` protege
contra duplicados si dos instancias corrieran a la vez. Runbook completo:
[`DEPLOYMENT.md`](./DEPLOYMENT.md).

---

## 8. Gotchas

- **pgBouncer + asyncpg**: el pooler de Supabase corre en modo *transaction*
  (puerto 6543). Sin `connect_args={"statement_cache_size": 0}` en el engine
  de SQLAlchemy, las queries fallan intermitentemente en producción — ya
  pasó, no es teórico. Migraciones de Alembic van por el puerto directo
  (5432, `POSTGRES_URL_NON_POOLING`), nunca por el pooler.
- **Ventana de 24h de WhatsApp**: Meta solo permite mensajes libres dentro de
  las 24h después del último mensaje del usuario. Alertas proactivas fuera
  de esa ventana requieren templates pre-aprobados por Meta — pendiente (ver
  [`WHATSAPP_API.md`](./WHATSAPP_API.md)). Ingesta acepta una lectura por
  request; firmware con buffer local hace un POST por lectura al reconectar.
- **`.env` del servidor universitario**: históricamente con keys duplicadas
  (`ADMIN_API_KEY`, `SENSOR_API_KEY_SECRET`); `python-dotenv` toma la última
  ocurrencia sin avisar. Reconstruir desde `.env.example` línea por línea, no
  copiar el `.env` local.
- **Coordenadas**: `CIENAGA_LAT`/`CIENAGA_LON` son el centroide medido en
  campo (`10.859056, -74.460611`). Los `fishing_points` seed
  (`alembic/versions/003_fishing_points.py`) son datos comunitarios
  ilustrativos, no coinciden con las coordenadas medidas. Las 6 zonas del IPP
  (`ipp.py::ZONES`) tienen su propio `lat`/`lng`: 3 medidas en campo, 3
  estimadas (pendiente DG-05). Zona e IPP no comparten coordenadas con
  `fishing_points` — son dos fuentes de confianza distinta.
- **Calidad de agua no viene de satélite**: pH, oxígeno disuelto, salinidad y
  turbidez no tienen fuente satelital con resolución útil aquí — los ESP32
  propios son la única fuente en tiempo real. No reemplazar con una API
  externa sin validar con el equipo de ingeniería civil primero.
- **`AI_API_KEY` vacío** → stub sin IA (fallback esperado, no un error). El
  `Protocol AIProvider` permite otro proveedor sin tocar el resto del código;
  hoy solo existe la implementación de Gemini.
- **Baseline nunca se persiste como medición**: si ERDDAP falla o el valor
  cae fuera de rango, `satellite_data.sst_celsius`/`chlorophyll_mgm3` quedan
  `NULL`, no el número de respaldo. El bloque `origen` de cada snapshot marca
  medido/cache/baseline/sin_dato (`dashboard_service.py::_save_satellite`).
- **El bot solo lee**: `message_router.py` llama únicamente
  `snapshot_service.read_persisted()`. Un cambio que necesite disparar una
  llamada nueva a API externa va en `dashboard_service.get_latest_snapshot()`
  (scheduler y `GET /data/latest` únicamente), no en el bot.
- El texto de "condición del agua" vive en `condicion_message.py`, extraído
  de `message_router.py` por la regla de 300 líneas — buscar
  `_mensaje_condicion`/`_ANOXIA_EN_BOT` ahí, no en el router de mensajes.
- Riesgo de anoxia (`signals.py`) calculado pero apagado en el bot
  (`_ANOXIA_EN_BOT = False`) — 8 umbrales sin validar contra un evento real,
  visible solo en el dashboard.
- El proyecto Vercel `ciena-net` de este mismo repo sigue linkeado
  (`.vercel/repo.json`, gitignored) y hace auto-deploy en cada push — sirve
  tráfico real en paralelo al servidor universitario. Ver "Deuda: doble
  despliegue" en [`DEPLOYMENT.md`](./DEPLOYMENT.md).

---

## 9. Testing

`tests/` — un archivo por servicio/router crítico, `pytest` + `pytest-asyncio`.
Todo lo que toque HMAC, hashing o envío de alertas necesita test — no
opcional. `scripts/verify_alert_lock.py` prueba el lock real contra una
Postgres descartable — nunca apuntarlo a la Supabase real.

Lint gate en CI (`.github/workflows/test.yml`): `ruff check .`, config en
`ruff.toml` (no `pyproject.toml` — Vercel auto-detecta `pyproject.toml` e
intenta `uv lock`, que falla sin tabla `[project]`). Reglas activas: `E4, E7,
E9, F`. CI instala desde `requirements-lock.txt` (versiones exactas), no
`requirements.txt`.

---

## 10. Fuentes de datos externas

| Fuente | Qué da | Auth | Librería |
|---|---|---|---|
| Open-Meteo | Meteo diaria + histórico desde 1940 | ninguna | `openmeteo-requests` |
| NASA/NOAA ERDDAP | SST 1km diario, clorofila | ninguna | `erddapy` |
| NOAA NHC (RSS) | Alertas de ciclones | ninguna | `feedparser` |
| IDEAM (Socrata) | Estaciones meteo, Magdalena | ninguna | `sodapy` |
| Copernicus Marine | SST/clorofila NRT — backup, no activo | registro gratuito | `copernicusmarine` |
| GBIF | Histórico de ocurrencias (ML futuro) | ninguna | `httpx` |
| ESP32 propios | pH, conductividad, temperatura, nivel de agua | API key propia | — |

Umbrales del semáforo, cálculo del IPP y detalle por fuente:
[`KNOWLEDGE_BASE.md`](./KNOWLEDGE_BASE.md).

---

## 11. Pendiente / fuera del flujo activo

- Templates de WhatsApp aprobados por Meta para alertas proactivas fuera de
  la ventana de 24h.
- Copernicus Marine integrado pero no usado (clorofila migró a NOAA
  CoastWatch, ver [`RESOLUCION_FUENTES.md`](./RESOLUCION_FUENTES.md)).
- Expansión de sensores a fase 2/3 ([`IOT_SENSORES.md`](./IOT_SENSORES.md)).
- Modelo de ML sobre históricos de pesca — features sin definir (`TAREAS_EQUIPO.md` DG-04).
- 3 de 6 zonas del IPP con coordenadas estimadas, no medidas — pendiente DG-05.

---

## 12. Índice de documentación

| Documento | Para qué leerlo |
|---|---|
| [`CONTEXT.md`](./CONTEXT.md) | Proyecto, usuarios, problema, equipo |
| [`ARCHITECTURE.md`](./ARCHITECTURE.md) | Diagrama del sistema, flujos, schema de DB completo |
| [`ADR-001-arquitectura-backend.md`](./ADR-001-arquitectura-backend.md) | Por qué esta estructura de carpetas |
| [`STACK.md`](./STACK.md) | Decisiones técnicas, versiones, variables de entorno |
| [`GUARDRAILS.md`](./GUARDRAILS.md) | Reglas obligatorias para código generado por IA |
| [`VIBECODING.md`](./VIBECODING.md) | Cómo prompear y trabajar con IA en este repo |
| [`WHATSAPP_API.md`](./WHATSAPP_API.md) | Integración Meta (webhook, envío, plantillas, debugging) |
| [`IOT_SENSORES.md`](./IOT_SENSORES.md) | Hardware ESP32, protocolo, calibración, plan de despliegue |
| [`DEPLOYMENT.md`](./DEPLOYMENT.md) | Runbook de despliegue dual, checklist de provisioning |
| [`KNOWLEDGE_BASE.md`](./KNOWLEDGE_BASE.md) | Fuentes de datos, semáforo, IPP, coordenadas |
| [`RESOLUCION_FUENTES.md`](./RESOLUCION_FUENTES.md) | Por qué se descartaron/cambiaron fuentes satelitales |
| [`IDEAM_GBIF_VALIDACION.md`](./IDEAM_GBIF_VALIDACION.md) | Validación de fuentes IDEAM/GBIF |
| [`COPERNICUS_ERDDAP.md`](./COPERNICUS_ERDDAP.md) | Detalle de fuentes satelitales |
| [`PROTOTIPO.md`](./PROTOTIPO.md) | Lógica del prototipo previo al MVP actual |
| [`TAREAS_EQUIPO.md`](./TAREAS_EQUIPO.md) / [`PLAN_DANIEL.md`](./PLAN_DANIEL.md) | Planificación histórica del sprint 1 |

Punto de entrada para cualquier IA o dev nuevo: [`CLAUDE.md`](../CLAUDE.md) en
la raíz del repo.
