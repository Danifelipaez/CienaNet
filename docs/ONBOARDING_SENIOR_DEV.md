# Onboarding — CienaNet Bot

> Documento de bienvenida para un desarrollador senior que se une al proyecto.
> Objetivo: dar en una sola lectura el contexto de negocio, el estado real del
> código y los detalles técnicos que no son obvios mirando el repo por encima.
> Todo lo demás (referencia detallada) vive en `docs/` y se enlaza desde aquí.

---

## 1. Qué es esto en una frase

**CienaNet Bot** es el backend que le da a pescadores artesanales de la
**Ciénaga Grande de Santa Marta** (Colombia) información ambiental en tiempo
real — vía **WhatsApp**, porque es el canal que ya usan — combinando una red
propia de sensores IoT de bajo costo con datos meteorológicos y satelitales
públicos. El mismo backend también alimenta un **dashboard web** para el
equipo científico/universitario que monitorea la Ciénaga.

Es un proyecto universitario (no una startup ni un producto comercial
todavía), en fase **MVP**, construido por un equipo pequeño de estudiantes de
ingeniería con ayuda intensiva de IA generativa para escribir código.

---

## 2. El problema real (por qué existe esto)

La Ciénaga Grande de Santa Marta es un ecosistema de manglar y agua salobre
del que dependen miles de familias de pescadores artesanales. El ecosistema
sufre contaminación, cambios de salinidad y degradación ambiental que afectan
directamente dónde y cuándo se puede pescar con seguridad y con buena
captura. Los pescadores no tienen hoy acceso a datos ambientales en tiempo
real para decidir esto — deciden por intuición y tradición oral.

**Usuarios primarios:** pescadores artesanales de la Ciénaga.
Alfabetización digital baja-media, canal preferido WhatsApp (no instalarían
una app nativa), español con influencia de lenguaje local/palafito.

**Implicación técnica directa:** cada respuesta que el bot manda a un
pescador tiene que ser corta (3-4 oraciones), sin jerga técnica ("el agua
está salada", no "la conductividad eléctrica supera 35 mS/cm"), y siempre
con una recomendación de acción concreta. Esto es una regla de producto que
sí afecta cómo se escribe el código de generación de respuestas (ver
`app/services/message_router.py`, `app/services/whatsapp_service.py`).

**Valores no negociables del proyecto** (afectan decisiones de producto, no
solo de código):
- Co-diseño comunitario: las decisiones se validan con pescadores reales.
- Pertinencia cultural en el lenguaje y los flujos de WhatsApp.
- Bajo costo: hardware y servicios cloud tienen que ser sostenibles para un
  equipo estudiantil (de ahí el uso de free tiers, ESP32 de ~$5, etc.).
- Privacidad: los números de teléfono y el contenido de mensajes son de
  personas reales, no "datos" — nunca se loggean (ver §8).

Contexto completo: [`docs/CONTEXT.md`](./CONTEXT.md).

---

## 3. Equipo y cómo se gestiona el trabajo

| Persona | Rol | Área |
|---|---|---|
| Daniel | Tech Lead / PM | Ing. Sistemas |
| Valentina | Desarrollo y datos | Ing. Sistemas |
| Diego | Análisis territorial | Ing. Civil |
| Soe | Investigación comunitaria | Historia |
| Luis | Vínculo con comunidad | Etnoeducación |

Gestión en **Microsoft Planner**, metodología ágil de sprints cortos,
historias de usuario en formato INVEST. La división de tareas del sprint 1
(ya completado) está documentada como referencia histórica en
[`docs/TAREAS_EQUIPO.md`](./TAREAS_EQUIPO.md) y
[`docs/PLAN_DANIEL.md`](./PLAN_DANIEL.md) — útil para entender *por qué* el
código quedó estructurado así, no como TODO list activo.

**Detalle importante para un dev nuevo:** buena parte del código de este
repo fue escrito con asistencia intensiva de IA (Claude, principalmente). El
proyecto tiene guardrails explícitos para eso en
[`docs/GUARDRAILS.md`](./GUARDRAILS.md) y una guía de flujo de trabajo en
[`docs/VIBECODING.md`](./VIBECODING.md). Si vas a seguir usando IA para
generar código en este repo, léelos — son vinculantes, no sugerencias.

---

## 4. Estado real del proyecto (verificado contra el código, no solo los docs)

El **Sprint 1** (dashboard backend: ingesta de sensores + fuentes externas +
API del dashboard) está **completo e implementado**. Esto ya no es un plan,
es código corriendo:

- Ingesta de sensores ESP32 (`POST /api/v1/sensors/ingest`) — funcional.
- Webhook de WhatsApp con validación HMAC — funcional.
- Dashboard científico (Next.js) con mapa, gráficas, chat con IA y estado de
  fuentes — funcional, desplegado.
- Fuentes externas integradas: Open-Meteo (clima), NASA/NOAA ERDDAP
  (temperatura superficial del mar + clorofila), NOAA NHC (alertas de
  ciclones), IDEAM (estaciones hidrometeorológicas de Colombia).
- Semáforo de condiciones (verde/amarillo/rojo) e Índice de Potencial
  Pesquero (IPP) por zona — calculados y cacheados diariamente.
- Sistema de alertas por WhatsApp con lock de base de datos para evitar
  duplicados (`pg_advisory_xact_lock`).
- Despliegue: backend pensado para el servidor universitario (producción
  real) únicamente; frontend en repo separado (`CienaRed-Frontend`), deploy
  Vercel. Ambos contra la misma Supabase.
  **Deuda conocida (2026-07-29):** el proyecto Vercel `ciena-net` de este
  mismo repo backend sigue linkeado (`.vercel/repo.json`, gitignored) y hace
  auto-deploy en cada push — hoy sirve tráfico real en paralelo al servidor
  universitario, no es solo un artefacto muerto. Ver "Deuda: doble
  despliegue" en [`docs/DEPLOYMENT.md`](./DEPLOYMENT.md) antes de asumir que
  el servidor universitario es el único backend corriendo.

**Trabajo reciente / en curso** (commits más recientes en `Developing`):
soporte para múltiples estaciones meteorológicas visibles en el mapa, una
función de indicación de fase/salida de la luna en el servicio de dashboard
(relevante porque la fase lunar influye en el comportamiento de pesca
tradicional), ajustes de UI del dashboard para móvil, y una ronda grande de
mejoras de precisión/valor sobre datos ya existentes (sin fuentes nuevas):

- **IPP recalibrado** (`app/services/ipp.py`): curvas trapezoidales
  continuas en vez de escalones, clorofila unimodal (penaliza floración en
  vez de premiarla siempre), pesos renormalizados sobre solo las señales con
  dato real (+`ipp_cobertura()`), y desglose de SST/clorofila por zona (antes
  las 6 zonas compartían el mismo valor satelital global).
- **Ráfagas reales de Open-Meteo** (`wind_gusts_10m` → `wind_gust_kmh`)
  reemplazan el `viento × 1.4` estimado en `semaphore.py`.
- **El bot ya no llama APIs externas por mensaje**: `snapshot_service.py`
  (nuevo) lee solo lo ya persistido; `dashboard_service.get_latest_snapshot()`
  queda como el camino de escritura, exclusivo del scheduler y `GET /data/latest`.
- **Procedencia de datos**: cada snapshot declara si un valor es "medido",
  "cache", "baseline" o "sin_dato" (`origen`); los baselines de respaldo ya no
  se persisten en `satellite_data` como si fueran mediciones reales.
- **Tendencias y señales nuevas** (`app/services/trends.py`,
  `app/services/signals.py`): deltas 24h/7d de salinidad/nivel/SST/clorofila,
  riesgo de anoxia y pulso de agua dulce — todas calculadas al vuelo sobre
  datos ya persistidos, marcadas explícitamente como estimación.
- **Bot con más valor**: intención "dónde pesco" (top zonas/puntos por IPP),
  contexto ambiental real en el fallback de Gemini (antes respondía sin datos),
  y los reportes de captura ahora capturan la cantidad si el pescador la menciona.
- **Trust boundary de sensores**: validación de rango en conductividad/nivel
  de agua (rechaza con 422 valores imposibles), y `get_latest_readings` ya
  filtra por sensor activo y por antigüedad (máx. 6h).

Detalle completo por archivo en [`docs/KNOWLEDGE_BASE.md`](./KNOWLEDGE_BASE.md)
§5-§6. Si vas a tocar `dashboard_service.py`, `snapshot_service.py`,
`ipp.py`, `semaphore.py` o `ingestion/*`, revisa el `git log` de esos
archivos primero — es la fuente de verdad más actualizada, más que este
documento.

**Lo que falta / fase futura:**
- Integración de datos satelitales ampliada (Copernicus Marine) — hoy es
  opcional/no usada en el flujo activo (clorofila migró a NOAA CoastWatch,
  ver [`docs/RESOLUCION_FUENTES.md`](./RESOLUCION_FUENTES.md)).
- Templates de WhatsApp aprobados por Meta para alertas proactivas fuera de
  la ventana de 24h (ver §9).
- Expansión de la red de sensores a fase 2/3 (ver
  [`docs/IOT_SENSORES.md`](./IOT_SENSORES.md) §"Plan de Despliegue por
  Fases").
- Modelo de ML sobre históricos de pesca (features aún por definir, tarea
  de Diego, ver `TAREAS_EQUIPO.md` DG-04) — el reporte de captura por
  WhatsApp ya guarda `cantidad_indice` cuando el pescador la menciona, así
  que la serie de captura de `/data/history` empieza a tener datos.
- Riesgo de anoxia (`signals.py`) implementado pero **apagado en el bot**
  (`condicion_message._ANOXIA_EN_BOT = False`) — los 8 umbrales no están
  validados contra un evento real todavía; visible solo en el dashboard.
- 3 de las 6 zonas del IPP tienen coordenadas estimadas, no medidas (Boca de
  la Barra, Caño Clarín, Suroccidente) — pendiente de validar vía DG-05.

---

## 5. Arquitectura técnica

### 5.1 Vista de alto nivel

```
WhatsApp User (pescador) ⇄ Meta Cloud API ⇄ POST /api/v1/webhook/whatsapp
                                                      │
ESP32 sensores ────────────────► POST /api/v1/sensors/ingest
                                                      │
                                                      ▼
                                    FASTAPI BACKEND (app/)
                     routers → services → models  (una sola dirección)
                                                      │
                                                      ▼
                                  Supabase (PostgreSQL)
                                                      │
                                                      ▼
                Dashboard Next.js — repo separado (CienaRed-Frontend), deploy Vercel
```

Diagrama completo con las 5 capas de servicios y el esquema de DB:
[`docs/ARCHITECTURE.md`](./ARCHITECTURE.md).

### 5.2 Estructura de carpetas (la que manda: `app/`, verificada contra el
repo real)

```
app/
├── api/v1/
│   ├── routers/        # webhook.py, sensors.py, data.py, admin.py, dashboard.py
│   └── dependencies.py # auth (API key sensores, admin), sesiones DB
├── services/            # TODA la lógica de negocio vive aquí
│   ├── message_router.py, condicion_message.py, whatsapp_service.py, ai_service.py
│   ├── sensor_service.py, alert_service.py, semaphore.py, ipp.py
│   ├── dashboard_service.py  # get_latest_snapshot() — orquesta el camino de ESCRITURA
│   ├── dashboard_persistence.py, dashboard_history.py, ai_context.py
│   │   # ↑ extraídos de dashboard_service.py (regla de 300 líneas, ver §13)
│   ├── snapshot_service.py   # read_persisted() — camino de LECTURA (bot, mapa)
│   ├── trends.py             # tendencias 24h/7d desde lo persistido
│   ├── signals.py            # anoxia, pulso de agua dulce (estimaciones)
│   ├── points_service.py, sedimentation_service.py
│   ├── system_status_service.py, derived.py
│   └── ingestion/       # weather.py, satellite.py, alerts_ext.py, ideam_hidro.py
├── models/               # SQLAlchemy ORM: environmental.py, messaging.py,
│                         # fishing_points.py, dashboard.py
├── schemas/              # Pydantic: sensor.py, environmental.py, dashboard.py
├── core/                 # config.py (Settings), database.py (engine/get_db),
│                         # security.py (HMAC, hash de API keys)
└── main.py               # FastAPI app, lifespan, routers, CORS, /health

tests/                    # pytest, un archivo por servicio/router crítico
alembic/versions/         # 12 migraciones aplicadas (001..012)
```

### 5.3 Regla de dependencias (no negociable, ver ADR-001)

```
routers  →  services  →  models
routers  →  schemas   (solo validar input/output)
services →  core/     (config, db, security)

PROHIBIDO: routers → models directo · models → services · services → routers
```

Si ves lógica de negocio dentro de un router, o una query directa a la DB
fuera de `services/`, es un defecto — corregirlo es prioridad sobre agregar
funcionalidad nueva. Razonamiento completo (por qué se descartó Vertical
Slice Architecture, cuándo reconsiderar):
[`docs/ADR-001-arquitectura-backend.md`](./ADR-001-arquitectura-backend.md).

### 5.4 Modelo de datos (tablas reales en `app/models/`)

| Tabla | Modelo en | Qué guarda |
|---|---|---|
| `users` | `messaging.py` | Pescador identificado por `wa_id` (WhatsApp) |
| `conversations` | `messaging.py` | Mensajes entrantes/salientes (nunca loggear `body`) |
| `catch_reports` | `messaging.py` | Reporte de captura, opcionalmente ligado a `fishing_points` |
| `alert_log` | `messaging.py` | Alertas ya enviadas (evita reenvíos) |
| `sensors` | `environmental.py` | Sensores ESP32 registrados, `api_key_hash` |
| `sensor_readings` | `environmental.py` | Lecturas puntuales: pH, conductividad, temp, nivel de agua |
| `weather_snapshots` | `environmental.py` | Snapshots de Open-Meteo |
| `satellite_data` | `environmental.py` | SST y clorofila (NASA/NOAA ERDDAP) |
| `external_alerts` | `environmental.py` | Alertas de NOAA NHC / IDEAM |
| `sedimentation_zones` | `environmental.py` | Monitoreo territorial |
| `daily_semaphore` | `environmental.py` | Semáforo + ranking IPP cacheado por día |
| `ideam_hidro_readings` | `environmental.py` | Respaldo propio de datos IDEAM en vivo |
| `fishing_points` | `fishing_points.py` | Conocimiento territorial comunitario (zonas, especies) |
| `ai_conversation` | `dashboard.py` | Historial del asistente de IA del dashboard |

Definiciones SQL completas: [`docs/ARCHITECTURE.md`](./ARCHITECTURE.md)
(sección "Base de Datos") y [`docs/KNOWLEDGE_BASE.md`](./KNOWLEDGE_BASE.md)
§7.

### 5.5 Flujos end-to-end clave

**Mensaje de WhatsApp entrante:**
```
Meta → POST /api/v1/webhook/whatsapp
  1. verify_hmac_meta() valida X-Hub-Signature-256 (app/core/security.py)
  2. MessageRouter identifica tipo (texto/audio/imagen/botón)
  3. Se procesa intención por palabra clave: saludo, condición, dónde pesco,
     alertas on/off, reporte de captura — o AIProvider si es texto libre
  4. Para condición/dónde-pesco: snapshot_service.read_persisted() lee el
     último estado YA persistido (cero llamadas de red, cero escrituras) —
     antes llamaba get_latest_snapshot() en cada mensaje: 5+ llamadas a APIs
     externas y 4 escrituras a DB para responder una oración
  5. Se arma respuesta corta en español (3-4 oraciones), se envía vía Meta API
  6. Se guarda la conversación en Supabase
```

**Ingesta de sensor IoT:**
```
ESP32 → POST /api/v1/sensors/ingest  (header X-Api-Key, UNA lectura por request)
  1. get_current_sensor() valida la API key contra el hash en DB
  2. Pydantic (SensorReadingIn) valida el payload — incluye rango de
     conductividad (0-80 mS/cm) y nivel de agua (0-500 cm), rechaza con 422
     si la sonda manda un valor imposible (desconectada, pegada en un riel)
  3. process_reading() persiste en sensor_readings
  4. (async, aparte) semaphore.py + alert_service.py evalúan el snapshot
     agregado y disparan WhatsApp si hace falta — get_latest_readings()
     filtra por sensor activo y por antigüedad (máx. 6h), una lectura vieja
     ya no sigue alimentando el snapshot indefinidamente
```

**Refresco horario (scheduler):** `app/main.py::_hourly_refresh()` corre
solo si `settings.run_scheduler` es `True` (un único deployment a la vez, ver
§7). Llama `get_latest_snapshot()` (agrega clima + satélite + sensores +
IPP + tendencias + señales de anoxia/pulso de agua dulce) y
`maybe_send_alert()`.

---

## 6. Referencia de endpoints (formatos reales de request/response)

Todos montados bajo el prefijo **`/api/v1`** (ej. `/api/v1/data/latest`),
más `GET /health` sin prefijo. Esta sección refleja el código real de
`app/api/v1/routers/*.py` y `app/schemas/*.py`, no un diseño aspiracional —
si el código cambia, esta tabla se desactualiza antes que el resto del doc.

### 6.0 Autenticación por header (resumen)

| Header | Para qué endpoints | Verificación |
|---|---|---|
| `X-Hub-Signature-256` | `POST /webhook/whatsapp` | HMAC-SHA256 contra `WHATSAPP_APP_SECRET` (`verify_hmac_meta`) |
| `X-Api-Key` | `POST /sensors/ingest` | Hash PBKDF2 contra `sensors.api_key_hash` (`get_current_sensor`) |
| `X-Admin-Key` | `/admin/*`, `/dashboard/ai/*`, `/dashboard/system-status` | Comparación directa contra `ADMIN_API_KEY` (`require_admin`) |
| `X-User-Id` | `/dashboard/ai/*` | **No es autenticación** — es un UUID que el frontend genera y guarda en `localStorage` para aislar el hilo/historial de IA por navegador (`get_dashboard_user`). No hay login de usuario todavía. |

`GET /dashboard/points`, `GET /dashboard/species` y `GET /dashboard/sedimentation`
**no requieren ningún header** — son de solo lectura y no exponen datos
sensibles (coordenadas de pesca y catálogo estático), a diferencia de
`/admin/*` que sí puede crear sensores.

---

### 6.1 Webhook WhatsApp — `app/api/v1/routers/webhook.py`

**`GET /api/v1/webhook/whatsapp`** — verificación inicial (Meta la llama una
sola vez al configurar el webhook en su dashboard).

Query params: `hub.mode`, `hub.challenge`, `hub.verify_token`.
Respuesta: `200` texto plano con el valor de `hub.challenge` si
`hub.verify_token == WHATSAPP_VERIFY_TOKEN`; si no, `403`.

**`POST /api/v1/webhook/whatsapp`** — recepción de mensajes.

Header requerido: `X-Hub-Signature-256: sha256=<hex>`.
Body: el payload JSON tal cual lo manda Meta (no hay schema Pydantic
dedicado, se lee directo del `Request` — ver §5.2). Estructura real que
importa (el resto del payload de Meta se ignora):

```json
{
  "entry": [{
    "changes": [{
      "value": {
        "contacts": [{ "profile": { "name": "Nombre Pescador" }, "wa_id": "573001234567" }],
        "messages": [{
          "from": "573001234567",
          "id": "wamid.xxx",
          "type": "text",
          "text": { "body": "cómo está el agua hoy?" }
        }]
      }
    }]
  }]
}
```

Respuesta: **siempre `{"status": "ok"}` con HTTP 200**, incluso si algo
falla procesando un mensaje individual (el error se loggea, no se
propaga — Meta reintenta agresivamente si no recibe 200 a tiempo).
Solo se procesan mensajes con `"type": "text"`; audio/imagen/botón/lista se
ignoran silenciosamente hoy (ver el `ponytail:` en el propio archivo — es
una limitación deliberada, no un bug).

---

### 6.2 Ingesta de sensores — `app/api/v1/routers/sensors.py`

**`POST /api/v1/sensors/ingest`** — una lectura por request (no batch).

Header requerido: `X-Api-Key: <api key del sensor>`.

Request body (`SensorReadingIn`, `app/schemas/sensor.py`):

```json
{
  "sensor_id": "CGSM-001",
  "timestamp": "2026-07-23T14:30:00Z",
  "ph": 7.4,
  "conductivity_mscm": 12.5,
  "temperature_c": 28.3,
  "water_level_cm": 45.2
}
```

| Campo | Tipo | Obligatorio | Validación |
|---|---|---|---|
| `sensor_id` | `str` | Sí | — |
| `timestamp` | `datetime` (ISO 8601) | Sí | — |
| `ph` | `float \| null` | No | 0–14, si no `ValueError` → `422` |
| `conductivity_mscm` | `float \| null` | No | 0–80 mS/cm, si no `422` (trust boundary: sonda desconectada) |
| `temperature_c` | `float \| null` | No | -5–45 °C, si no `422` |
| `water_level_cm` | `float \| null` | No | 0–500 cm, si no `422` |

Los campos opcionales se omiten o mandan `null` si el sensor no los mide.
`battery_mv`/`signal_rssi` **no existen** en el schema todavía.

Respuesta: `201` `{"status": "ok"}`. Errores: `403` (API key inválida vía
`get_current_sensor`), `422` (payload no valida contra el schema).

---

### 6.3 API del dashboard (datos ambientales) — `app/api/v1/routers/data.py`

**`GET /api/v1/data/latest`** → `DashboardSnapshot` (`app/schemas/environmental.py`):

```json
{
  "semaphore": { "color": "green", "reason": "Condiciones favorables", "safe": true },
  "weather": {
    "temperature_c": 28.1, "humidity_pct": 82.0, "wind_speed_kmh": 12.4,
    "wind_gust_kmh": 18.0, "wind_direction_deg": 95.0, "precipitation_mm": 0.0
  },
  "satellite": { "sst_celsius": 27.4, "chlorophyll_mgm3": 3.8, "date": "2026-07-21" },
  "water": {
    "ph": 7.8, "temperature_c": 29.1, "conductivity_mscm": 12.1,
    "water_level_cm": 44.0, "salinity_psu": 15.2, "tds_mgl": 7800.0
  },
  "sensors": [{ "zone": "Boca de la Barra", "ph": 7.8, "temperature_c": 29.1, "conductivity_mscm": 12.1, "water_level_cm": 44.0 }],
  "ipp_ranking": [{ "zone": "Caño Clarín", "ipp": 82.5, "cobertura": 1.0 }],
  "cyclone_alerts": [],
  "tendencias": {
    "variables": { "salinity_psu": { "actual": 15.2, "delta_24h": -0.3, "delta_7d": -1.8, "direccion": "bajando" } },
    "lluvia_72h_mm": 12.0
  },
  "senales": {
    "anoxia": { "score": 22.0, "nivel": "bajo", "factores": [], "n_factores": 3, "estimacion": true },
    "pulso_agua_dulce": null
  },
  "origen": {
    "weather": "medido", "tasajera_weather": "medido",
    "satellite": { "sst_celsius": "medido", "chlorophyll_mgm3": "medido" },
    "water": "medido"
  },
  "updated_at": "2026-07-23T14:30:00+00:00"
}
```

`salinity_psu` y `tds_mgl` son **derivados** (calculados en
`app/services/derived.py` a partir de conductividad/temperatura, no vienen
crudos de ningún sensor ni API externa) — cualquier `null` en `water`
significa que aún no hay lectura de sensor agregable, no un error.

`cobertura` (0.0-1.0, en cada entrada de `ipp_ranking`) es la fracción del
peso IPP que tuvo dato real — sin sensores de agua, cae a ~0.54 (solo
SST+clorofila). `origen` distingue "medido" de "cache"/"baseline"/"sin_dato"
por fuente; un valor `"baseline"` en satélite **nunca** se persiste en
`satellite_data` como si fuera medición (queda `NULL`). `tendencias` y
`senales` se calculan al vuelo desde lo persistido (`trends.py`,
`signals.py`), no tienen tabla propia — `senales.anoxia`/`pulso_agua_dulce`
son ESTIMACIONES explícitas, no mediciones (ver `docs/GUARDRAILS.md`).

**`GET /api/v1/data/history?days=30`** (`days` entre 1 y 365, default 30) →
`HistoryResponse`: series de tiempo independientes, **no alineadas por
timestamp** entre sí (cada lista tiene su propia cadencia según la fuente):

```json
{
  "weather": [{ "timestamp": "2026-07-23T12:00:00Z", "estacion": "Tasajera", "temperature_c": 28.0, "humidity_pct": 80.0, "wind_speed_kmh": 10.0, "wind_gust_kmh": 15.0, "precipitation_mm": 0.0 }],
  "semaphore": [{ "date": "2026-07-23", "color": "green", "reason": "...", "ipp_ranking": [...] }],
  "satellite": [{ "date": "2026-07-21", "sst_celsius": 27.4, "chlorophyll_mgm3": 3.8 }],
  "captura": [{ "date": "2026-07-20", "cantidad_indice": 4.2 }],
  "ideam_precipitacion": [{ "date": "2026-07-23", "estacion": "Media Luna", "precipitacion_mm": 3.1 }],
  "ideam_nivel_rio": [{ "date": "2026-07-23", "estacion": "Media Luna", "nivel_m": 1.8 }]
}
```

`estacion` aparece porque hay **múltiples estaciones meteorológicas** (ver
§4, trabajo reciente) — un mismo día puede tener varios puntos `weather` con
`estacion` distinta. `ideam_precipitacion`/`ideam_nivel_rio` pueden venir
vacíos (`[]`) si no hay datos de respaldo IDEAM para el rango pedido.

**`GET /api/v1/data/zones`** → sin schema tipado, `dict` plano:

```json
{ "ipp_ranking": [{ "zone": "Caño Clarín", "ipp": 82.5, "cobertura": 1.0 }, ...], "date": "2026-07-23" }
```

`ipp_ranking: []` y `date: null` si todavía no se ha calculado ningún
semáforo diario.

**`GET /api/v1/data/alerts`** → `dict` plano, combina una llamada en vivo
(NOAA NHC) con datos ya persistidos:

```json
{
  "cyclones": [{ "title": "...", "summary": "...", "link": "..." }],
  "external": [{ "source": "noaa_nhc", "type": "...", "title": "...", "fetched_at": "2026-07-23T10:00:00Z" }],
  "semaphore_color": "green"
}
```

---

### 6.4 Administración de sensores — `app/api/v1/routers/admin.py`

Todos requieren `X-Admin-Key`.

**`POST /api/v1/admin/sensors`** — registra un sensor nuevo.

Request: `{"device_id": "CGSM-004", "location": "Nueva Venecia"}`
(`location` opcional).

Respuesta `201`:
```json
{ "sensor_id": "uuid", "device_id": "CGSM-004", "location": "Nueva Venecia", "raw_api_key": "..." }
```

**`raw_api_key` se muestra en texto plano una única vez** — solo se guarda
el hash (`api_key_hash`) en DB, no hay endpoint para recuperarla después; si
se pierde, hay que rotarla (crear un sensor nuevo o regenerar el hash a
mano). `409` si `device_id` ya existe.

**`GET /api/v1/admin/sensors`** → `list[SensorInfo]`, sin exponer hashes:
```json
[{ "sensor_id": "uuid", "device_id": "CGSM-001", "location": "Zona norte", "active": true }]
```

---

### 6.5 Dashboard interno (mapa, IA, sistema) — `app/api/v1/routers/dashboard.py`

**`GET /api/v1/dashboard/points`** (sin auth) → `{"puntos": [...]}`, un
objeto por punto de pesca real (`fishing_points`), ya con IPP calculado.
`temp`/`clorofila` vienen del satélite de la zona IPP más cercana al punto
(centroide más cercano), no del promedio global de toda la Ciénaga:
```json
{ "puntos": [{
  "id": "uuid", "nombre": "Caño Clarín", "lat": 10.86, "lng": -74.47,
  "especies": ["camaron", "lisa"], "observacion": "texto comunitario o null",
  "temp": 27.4, "clorofila": 3.8, "viento": 12.4,
  "salinidad": 15.2, "tds": 7800.0,
  "ipp": 82.5, "cobertura": 1.0, "condicion": "verde"
}] }
```

**`GET /api/v1/dashboard/species`** (sin auth) → catálogo estático de 4
especies (`{"especies": [{"id": "camaron", "label": "Camarón"}, ...]}`),
hardcodeado a propósito (`ponytail:` en el código — no hay tabla `species`
porque 4 valores fijos no la justifican hoy).

**`GET /api/v1/dashboard/sedimentation`** (sin auth) → `{"zonas": [{"id", "nombre", "polygon", "nivel", "observacion"}]}`,
`polygon` es GeoJSON crudo tal cual se guardó en DB.

**`POST /api/v1/dashboard/ai/ask`** — headers `X-Admin-Key` + `X-User-Id`.

Request (`AskRequest`):
```json
{ "pregunta": "¿cómo está la salinidad hoy?", "contexto": {"punto_id": "uuid"}, "conversation_id": "uuid o null" }
```
`contexto` es libre (lo que el frontend tenga seleccionado en el mapa, ej.
un punto de pesca) — se le pasa a Gemini tal cual como JSON.
`conversation_id: null` = arranca un hilo nuevo (el backend mintea uno y lo
devuelve); si se manda uno existente, la respuesta se agrega a ese hilo con
memoria de los últimos `AI_HISTORY_TURNS` turnos.

Respuesta (`AskResponse`):
```json
{
  "parrafos": [
    { "tipo": "texto", "titulo": null, "html": "El agua está en buen estado hoy.", "items": null },
    { "tipo": "datos", "titulo": "Datos usados", "html": null, "items": [
        { "v": "27.4°C", "d": "Temperatura superficial", "fuente": "NASA ERDDAP" }
    ]}
  ],
  "sugerencia": "Buen momento para pescar en Caño Clarín",
  "conversation_id": "uuid"
}
```
`tipo` es uno de `"texto" | "datos" | "limitaciones"` — el frontend renderiza
cada uno con un componente distinto (texto libre, fichas de dato con fuente,
o aviso de limitación). El modelo está instruido a **no inventar valores**
fuera del contexto ambiental real que se le inyecta (`build_ai_context`).

**`GET /api/v1/dashboard/ai/history?limit=20`** — headers `X-Admin-Key` +
`X-User-Id`. Devuelve el historial **del usuario que manda ese `X-User-Id`**,
agrupado por conversación (no por turno individual):
```json
{ "historial": [{
  "id": "uuid-conversacion", "titulo": "primera pregunta del hilo",
  "created_at": "...", "updated_at": "...",
  "turnos": [{ "id": "uuid-turno", "pregunta": "...", "respuesta": [ /* AIParrafo[] */ ], "sugerencia": "...", "created_at": "..." }]
}] }
```

**`DELETE /api/v1/dashboard/ai/history/{conversation_id}`** — headers
`X-Admin-Key` + `X-User-Id`. Borra todos los turnos de esa conversación,
acotado al `user_id` del header (un usuario no puede borrar el hilo de
otro aunque adivine el UUID). Respuesta: `{"ok": true}`.

**`GET /api/v1/dashboard/system-status`** — header `X-Admin-Key`:
```json
{
  "apis": [{ "id": "openmeteo", "nombre": "Open-Meteo", "desc": "Viento, temperatura aire", "estado": "ok", "actualizado": "..." }],
  "bot_metricas": [{ "id": "msgs", "label": "Mensajes enviados", "valor": 42, "sub": "últimos 30 días" }],
  "log_alertas": [{ "hora": "...", "tipo": "red", "canal": "whatsapp", "zonas": ["..."], "texto": "...", "destinatarios": 12 }]
}
```
`estado` es `"ok" | "degradado" | "caido"`, calculado por antigüedad del
último dato (umbrales distintos por fuente: clima se degrada a las 1.5h,
satélite tolera hasta 2 días de lag porque así procesa NASA). No hay
métrica de latencia real — el código deliberadamente no la inventa (ver el
`ponytail:` al inicio de `system_status_service.py`).

---

### 6.6 Salud del servicio

**`GET /health`** (sin prefijo `/api/v1`, sin auth) → `{"status": "ok", "version": "0.1.0", "deploy": "..."}`.
Usado por Docker/systemd para healthchecks y por el checklist de deploy
manual de [`docs/DEPLOYMENT.md`](./DEPLOYMENT.md).

---

## 7. Stack y por qué (decisiones ya tomadas — no reabrir sin buena razón)

| Pieza | Elegido | Por qué (resumen) |
|---|---|---|
| Backend | **Python 3.11 + FastAPI** | Tipado con Pydantic, docs automáticas (Swagger), el equipo ya conoce Python |
| DB | **Supabase (PostgreSQL)** | SQL real (mejor que NoSQL para series temporales), free tier, dashboard visual para el equipo no-dev |
| ORM | **SQLAlchemy 2.0 (async) + Alembic** | — |
| WhatsApp | **Meta Cloud API oficial** | Sin costo por intermediario (vs. Twilio), acceso completo a botones/listas/templates |
| IA/NLU | **Google Gemini** vía REST directo (`httpx`, sin SDK) | `app/services/ai_service.py` define un `Protocol` (`AIProvider`) — cambiar de proveedor no debería tocar el resto del código. Fallback a respuestas predefinidas si `AI_API_KEY` está vacío |
| Frontend dashboard | **Next.js 16 (App Router) + TypeScript + React 19 + Leaflet** | Repo separado (`CienaRed-Frontend`), deploy Vercel |
| Deploy backend | **Servidor universitario** (Docker o systemd+uvicorn) | Proceso persistente, sin timeout de función, recibe el webhook real y las lecturas ESP32 |
| IoT | **ESP32 + pH/EC/DS18B20** | ~$110 USD por nodo, bajo costo sostenible para un proyecto estudiantil |

Detalle completo con versiones exactas y variables de entorno:
[`docs/STACK.md`](./STACK.md). Tabla de "lo que NO usamos y por qué"
(Twilio, Firebase, MongoDB, Django, Vercel serverless para backend) también
está ahí — útil para no repetir una discusión ya cerrada.

### 7.1 `RUN_SCHEDULER`: prod vs. local dev, no un toggle entre deployments

El backend corre en un único proceso persistente (servidor universitario en
producción). `RUN_SCHEDULER=true` ahí activa el loop horario que refresca el
snapshot ambiental y evalúa/envía alertas de WhatsApp; en local dev queda en
`false` por defecto (ponelo en `true` solo para probar el loop en tu
máquina). Un `pg_advisory_xact_lock` en
`alert_service.py::maybe_send_alert()` protege igual contra duplicados si
dos instancias locales llegaran a correr a la vez. Runbook completo de
despliegue y checklist de provisioning:
[`docs/DEPLOYMENT.md`](./DEPLOYMENT.md).

---

## 8. Seguridad — no negociable

1. **HMAC-SHA256 obligatorio** en cada request al webhook de Meta, validado
   *antes* de tocar el body (`verify_hmac_meta()` en `app/core/security.py`).
2. **Nunca loggear** contenido de mensajes de usuarios, ni números de
   teléfono completos, ni tokens/API keys.
3. **API key por sensor**, hasheada con PBKDF2 antes de guardar en DB — si
   un sensor se compromete, se revoca solo esa key.
4. Variables sensibles **solo en `.env`**, nunca hardcodeadas ni en
   comentarios.
5. Toda data externa (payload de Meta, lecturas de sensores) se valida con
   Pydantic **en el borde**, antes de llegar a la lógica de negocio.
6. `ADMIN_API_KEY` protege `/admin/*` (registro de sensores) y los proxies
   del dashboard — mismo valor en `.env` del backend y `.env.local` del repo
   `CienaRed-Frontend` (`lib/api.ts` ahí nunca expone esto al navegador; las
   llamadas dashboard → backend son siempre servidor-a-servidor).

Checklist completa de revisión antes de commitear código generado por IA:
[`docs/GUARDRAILS.md`](./GUARDRAILS.md).

---

## 9. Cosas no obvias que cuestan caro si no se saben (gotchas reales)

- **pgBouncer + asyncpg:** el runtime usa el pooler de Supabase en modo
  *transaction* (puerto 6543). Sin `connect_args={"statement_cache_size": 0}`
  en el engine de SQLAlchemy, las queries fallan intermitentemente en
  producción — no es teórico, ya pasó. Las migraciones de Alembic van por el
  puerto directo (5432, `POSTGRES_URL_NON_POOLING`), nunca por el pooler.
- **Ventana de 24 horas de WhatsApp:** Meta solo permite mensajes libres
  (`text`/`interactive`) dentro de las 24h después del último mensaje del
  usuario. Las alertas proactivas de sensores fuera de esa ventana necesitan
  **templates pre-aprobados por Meta** (`alerta_ph_alto`, `alerta_salinidad`,
  etc. — ver [`docs/WHATSAPP_API.md`](./WHATSAPP_API.md)). Esto todavía no
  está resuelto del todo (ver §4, "lo que falta").
  El endpoint de ingesta acepta **una lectura por request**, no un array —
  un firmware con buffer local debe hacer un POST por lectura al reconectar.
- **`.env` en el servidor universitario:** históricamente ha tenido keys
  duplicadas (`ADMIN_API_KEY`, `SENSOR_API_KEY_SECRET`) donde
  `python-dotenv` toma la última ocurrencia sin avisar. Reconstruir línea por
  línea desde `.env.example`, no copiar el `.env` local tal cual.
- **Coordenadas:** `CIENAGA_LAT`/`CIENAGA_LON` son el centroide real medido
  en campo (`10.859056, -74.460611`), no un aproximado. Los puntos de pesca
  seed en `alembic/versions/003_fishing_points.py` (incluyendo uno llamado
  "Tasajera") **no coinciden** con las coordenadas medidas reales — son
  datos comunitarios ilustrativos, pendientes de validar con el equipo
  territorial. Las 6 zonas del IPP (`app/services/ipp.py::ZONES`) sí tienen
  `lat`/`lng` propios (usados para el satélite por zona) — 3 medidas en
  campo, 3 estimadas y marcadas como tal, pendientes de DG-05. No confundir
  las coordenadas de zona con las de `fishing_points`: son dos cosas
  distintas con distinto nivel de confianza. Ver
  [`docs/KNOWLEDGE_BASE.md`](./KNOWLEDGE_BASE.md) §12 antes de asumir que un
  punto en el mapa es geográficamente exacto.
- **Calidad de agua no viene de satélite:** pH, oxígeno disuelto, salinidad
  y turbidez no tienen fuente satelital con resolución útil para la
  Ciénaga — los sensores ESP32 propios son la única fuente en tiempo real
  (confirmado por Diego, ing. civil del equipo). No intentar "resolver" esto
  con una API externa nueva sin validarlo con él primero.
- **`AI_API_KEY` vacío = stub sin IA**, no un error. El `Protocol`
  `AIProvider` en `ai_service.py` permite cambiar de proveedor sin tocar el
  resto del código, pero hoy solo existe la implementación de Gemini.
- **Un valor `"baseline"` nunca se persiste como si fuera medición:** si
  ERDDAP falla o el valor cae fuera de rango, `satellite_data.sst_celsius`/
  `chlorophyll_mgm3` quedan `NULL`, no el número de respaldo (28.0°C /
  4.5 mg/m³). Cada snapshot trae un bloque `origen` (`"medido"` | `"cache"` |
  `"baseline"` | `"sin_dato"`) para que el consumidor sepa qué tan confiable
  es cada valor — ver `app/services/dashboard_service.py::_save_satellite`.
- **El bot lee, no escribe:** `message_router.py` solo llama
  `snapshot_service.read_persisted()` (cero red, cero escrituras). Si un
  cambio necesita que el bot dispare una llamada nueva a una API externa,
  probablemente está en el archivo equivocado — eso va en
  `dashboard_service.get_latest_snapshot()`, que solo llaman el scheduler y
  `GET /data/latest`.
- **El texto de "condición del agua" vive en `condicion_message.py`**, no en
  `message_router.py` — se extrajo para no pasar las 300 líneas. Si buscas
  `_mensaje_condicion` o `_ANOXIA_EN_BOT` y no está en `message_router.py`,
  es ahí.

---

## 10. Frontend / Dashboard

Repo separado: `CienaRed-Frontend` — Next.js 16 (App Router), deploy Vercel:

```
app/dashboard/
  ├── mapa/      → Leaflet, puntos de pesca / zonas IPP / estaciones
  ├── graficas/  → histórico ambiental (charts propios, sin librería pesada)
  ├── ia/        → chat contra /api/v1/dashboard/ai/ask (Gemini)
  └── sistema/   → estado de las fuentes de datos externas

app/api/{admin,data}/*  → route handlers Next.js que proxean al backend
                           FastAPI vía BACKEND_URL (así el navegador nunca ve
                           ADMIN_API_KEY directamente)
```

---

## 11. Fuentes de datos externas

| Fuente | Qué da | Auth | Librería |
|---|---|---|---|
| Open-Meteo | Meteo diaria + histórico desde 1940 | Ninguna | `openmeteo-requests` |
| NASA/NOAA ERDDAP | SST 1km diario, clorofila | Ninguna | `erddapy` |
| NOAA NHC (RSS) | Alertas de ciclones tropicales | Ninguna | `feedparser` |
| IDEAM (Socrata) | Estaciones meteo en tierra, Magdalena | Ninguna | `sodapy` |
| Copernicus Marine | SST/clorofila NRT (backup, no activo hoy) | Registro gratuito | `copernicusmarine` |
| GBIF | Histórico de ocurrencias de pesca (para ML futuro) | Ninguna | `httpx` |
| ESP32 propios | pH, conductividad, temperatura, nivel de agua | API key propia | — |

Ejemplos de código reales por fuente, umbrales del semáforo, cálculo del
Índice de Potencial Pesquero (IPP) y coordenadas georreferenciadas de la
Ciénaga: [`docs/KNOWLEDGE_BASE.md`](./KNOWLEDGE_BASE.md) (documento de
referencia rápida más denso del repo).

---

## 12. Testing

`tests/` — un archivo por servicio/router crítico (`pytest` +
`pytest-asyncio`). Cubre: config (incluyendo el fail-fast de `ADMIN_API_KEY`
fuera de development), seguridad (HMAC, hash), semáforo, IPP, alertas
(incluyendo el advisory lock y el gate de scheduler), servicios de IA y
dashboard, endpoints del dashboard, ingesta IDEAM/clima/satélite, tendencias,
señales de anoxia, **`message_router.py`** + **`condicion_message.py`** (el
cerebro del bot de WhatsApp y el armado del mensaje de condición), y —
agregado más recientemente, antes sin ningún test — `whatsapp_service.py`,
`points_service.py`, `sedimentation_service.py`, `system_status_service.py`,
y los routers `admin.py`/`sensors.py` (`TestClient` + `dependency_overrides`).
`scripts/verify_alert_lock.py` prueba la serialización real del lock entre
conexiones contra una Postgres descartable — **nunca apuntarlo a la Supabase
real** (instrucciones en el propio script).

Regla del proyecto: todo lo que toque el path de seguridad (HMAC, hashing)
o el envío de alertas necesita test — no es opcional.

**Lint gate:** `ruff check .` corre en CI (`.github/workflows/test.yml`)
junto a `pytest`, configurado en `ruff.toml` (no `pyproject.toml` — Vercel
auto-detecta `pyproject.toml` e intenta resolver dependencias con `uv lock`,
que falla sin una tabla `[project]`; `ruff.toml` evita ese problema). Reglas
activas: `E4, E7, E9, F` (Pyflakes + errores reales de pycodestyle, sin
bikeshedding de estilo). CI instala desde `requirements-lock.txt` (versiones
exactas via `pip freeze`), no `requirements.txt` (floors humanos) — Dependabot
(`.github/dependabot.yml`) abre PRs semanales para ambos ecosistemas
(pip y github-actions).

---

## 13. Cómo se trabaja aquí (convenciones)

- Un archivo = una responsabilidad. Archivos de más de ~300 líneas se
  refactorizan en módulos.
- Type hints en todo. Pydantic para todo input externo.
- Nunca `print()` para debug — `logging` con niveles.
- Nunca lógica de negocio en routers, nunca queries directas a DB fuera de
  `services/`.
- Código y comentarios técnicos en inglés; los mensajes que ve el pescador,
  siempre en español simple.
- PRs pequeños (~200 líneas de diff), commits frecuentes.
- Antes de generar migraciones nuevas, revisar el schema existente
  (`alembic/versions/001..012`) — ya hay 12 migraciones aplicadas.

Guía completa de cómo estructurar prompts de IA para este repo (con
ejemplos de "malo" vs. "bueno"), flujo recomendado por feature y señales de
que algo salió mal: [`docs/VIBECODING.md`](./VIBECODING.md).

---

## 14. Índice de toda la documentación

| Documento | Para qué leerlo |
|---|---|
| [`CONTEXT.md`](./CONTEXT.md) | Proyecto, usuarios, problema, equipo |
| [`ARCHITECTURE.md`](./ARCHITECTURE.md) | Diagrama del sistema, flujos, schema de DB completo |
| [`ADR-001-arquitectura-backend.md`](./ADR-001-arquitectura-backend.md) | Por qué esta estructura de carpetas y no otra |
| [`STACK.md`](./STACK.md) | Decisiones técnicas, versiones exactas, variables de entorno |
| [`GUARDRAILS.md`](./GUARDRAILS.md) | Reglas obligatorias para código generado por IA |
| [`VIBECODING.md`](./VIBECODING.md) | Cómo prompear y trabajar con IA en este repo |
| [`WHATSAPP_API.md`](./WHATSAPP_API.md) | Integración Meta (webhook, envío, plantillas, debugging) |
| [`IOT_SENSORES.md`](./IOT_SENSORES.md) | Hardware ESP32, protocolo, calibración, plan de despliegue |
| [`DEPLOYMENT.md`](./DEPLOYMENT.md) | Runbook de despliegue dual, checklist de provisioning |
| [`KNOWLEDGE_BASE.md`](./KNOWLEDGE_BASE.md) | Referencia técnica más densa: fuentes de datos, semáforo, IPP, coordenadas |
| [`RESOLUCION_FUENTES.md`](./RESOLUCION_FUENTES.md) | Por qué se descartaron/cambiaron ciertas fuentes satelitales |
| [`IDEAM_GBIF_VALIDACION.md`](./IDEAM_GBIF_VALIDACION.md) | Validación de fuentes IDEAM/GBIF (trabajo de Diego) |
| [`COPERNICUS_ERDDAP.md`](./COPERNICUS_ERDDAP.md) | Detalle de las fuentes satelitales |
| [`PROTOTIPO.md`](./PROTOTIPO.md) | Lógica validada del prototipo original (previo al MVP actual) |
| [`TAREAS_EQUIPO.md`](./TAREAS_EQUIPO.md) / [`PLAN_DANIEL.md`](./PLAN_DANIEL.md) | Planificación histórica del sprint 1 — contexto de por qué el código quedó así |

**Punto de entrada para cualquier IA o dev nuevo:** siempre empezar por
[`CLAUDE.md`](../CLAUDE.md) en la raíz del repo — enlaza a todo lo anterior
y define las reglas que siempre aplican.
