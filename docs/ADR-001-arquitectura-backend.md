# ADR-001: Arquitectura del Backend — CienaNet Bot

**Status:** Accepted  
**Date:** 2026-06-26  
**Deciders:** Daniel (Tech Lead), Valentina (Dev)

---

## Context

Somos un equipo de 2 desarrolladores junior en un MVP con 3 dominios bien delimitados: mensajes WhatsApp, ingesta de sensores IoT y alertas. El sistema corre en Vercel como funciones serverless con FastAPI + Mangum.

Necesitamos una arquitectura que:
- Sea legible por desarrolladores junior sin experiencia previa en proyectos grandes
- Tenga documentación oficial de referencia (no patrones inventados)
- Separe responsabilidades sin duplicar conceptos ni crear abstracciones prematuras
- Quepa en archivos de máximo 300 líneas (regla del proyecto)

---

## Decision

Adoptamos **FastAPI Bigger Applications** (patrón oficial de FastAPI docs) con una variación: los routers se organizan por **dominio de negocio** en lugar de por tipo de archivo.

---

## Estructura de Carpetas

```
app/
├── core/
│   ├── config.py          # Settings con pydantic-settings, leer .env
│   ├── database.py        # SQLAlchemy engine + get_db() dependency
│   └── security.py        # Validación HMAC Meta, hash de API keys
│
├── api/
│   └── v1/
│       ├── __init__.py
│       ├── routers/
│       │   ├── whatsapp.py    # GET+POST /webhook/whatsapp
│       │   ├── sensors.py     # POST /sensors/ingest
│       │   └── admin.py       # GET /admin/* (datos internos)
│       └── dependencies.py    # FastAPI Depends() compartidos
│
├── services/
│   ├── whatsapp_service.py    # Lógica mensajes: parsear, responder
│   ├── sensor_service.py      # Lógica ingesta: validar, guardar, alertar
│   ├── alert_service.py       # Evaluación de umbrales + dispatch
│   └── ai_service.py          # AIProvider Protocol + get_ai_provider() (proveedor agnóstico)
│
├── models/
│   ├── user.py                # ORM: users
│   ├── conversation.py        # ORM: conversations
│   ├── sensor.py              # ORM: sensors + sensor_readings
│   └── alert.py               # ORM: alerts
│
├── schemas/
│   ├── whatsapp.py            # Pydantic: payload Meta webhook
│   ├── sensor.py              # Pydantic: payload IoT ingest
│   └── common.py              # Tipos compartidos (APIResponse, etc.)
│
└── main.py                    # FastAPI app, incluye routers, middleware

api/
└── index.py                   # Entry point Vercel (Mangum wrapper)
```

---

## Reglas de Dependencias

```
routers  →  services  →  models
routers  →  schemas   (solo para validar input/output)
services →  core/     (config, db, security)
services →  schemas   (construir respuestas)

PROHIBIDO:
routers  →  models    (directo, sin pasar por service)
models   →  services  (dependencia circular)
services →  routers   (dependencia circular)
```

---

## Responsabilidad de Cada Capa

| Archivo | Hace | No hace |
|---|---|---|
| `routers/*.py` | Recibe HTTP, valida auth, llama service, retorna response | Lógica de negocio, queries a DB |
| `services/*.py` | Toda la lógica de negocio | Construir respuestas HTTP, acceder a `request` |
| `models/*.py` | Define tablas ORM | Lógica de negocio |
| `schemas/*.py` | Valida y serializa data externa | Acceder a DB |
| `core/security.py` | HMAC, hashing, API key check | Lógica de dominio |

---

## Flujo Típico: Mensaje WhatsApp Entrante

```
POST /webhook/whatsapp
  → routers/whatsapp.py
      1. core/security.py: valida HMAC (obligatorio, antes de todo)
      2. schemas/whatsapp.py: parsea payload Meta → Pydantic model
      3. whatsapp_service.py: procesa mensaje
          ├── ai_service.py: clasifica intención (si texto libre)
          ├── sensor_service.py: consulta última lectura
          └── retorna texto de respuesta
      4. router arma HTTPResponse 200
```

---

## Flujo Típico: Ingesta de Sensor IoT

```
POST /sensors/ingest
  → routers/sensors.py
      1. dependencies.py: valida API key del sensor (Depends)
      2. schemas/sensor.py: valida payload → SensorReadingCreate
      3. sensor_service.py:
          ├── guarda lectura en DB
          └── alert_service.py: evalúa umbrales
              └── whatsapp_service.py: notifica si hay alerta
      4. router retorna 201
```

---

## Options Considered

### Opción A: FastAPI Bigger Applications (elegida)
| Dimensión | Evaluación |
|---|---|
| Complejidad | Baja — es el tutorial oficial |
| Documentación | Alta — docs.fastapi.tiangolo.com/tutorial/bigger-applications |
| Familiaridad del equipo | Alta — Valentina conoce Python; patrón enseñado en cursos |
| Escalabilidad | Media — suficiente para MVP y siguiente fase |

**Pros:** documentación oficial exhaustiva, ejemplos en abundancia, cualquier dev Python lo entiende en 10 minutos.  
**Cons:** carpetas por tipo (models/, schemas/) separan archivos relacionados — para encontrar todo lo de "sensores" hay que mirar 4 carpetas.

### Opción B: Vertical Slice Architecture (descartada)
| Dimensión | Evaluación |
|---|---|
| Complejidad | Media |
| Documentación | Baja — patrón agnóstico, sin guía FastAPI oficial |
| Familiaridad del equipo | Baja — poco conocido en Python |

**Descartada porque:** no tiene documentación oficial de FastAPI, requiere que el equipo junior aprenda el patrón antes de escribir código.

---

## Consequences

**Se vuelve más fácil:**
- Onboarding de nuevos devs (apuntar a docs.fastapi.tiangolo.com)
- Encontrar dónde va código nuevo: ¿es lógica? → services/. ¿es HTTP? → routers/.
- Code review: cualquier lógica en routers/ es un error inmediato

**Se vuelve más difícil:**
- Entender un dominio completo requiere navegar 4 carpetas (models/ + schemas/ + services/ + routers/)
- Si el proyecto crece a 10+ dominios, la estructura se vuelve confusa

**Revisar cuando:**
- Más de 6 archivos en services/ → considerar Vertical Slice
- Archivos de más de 200 líneas → dividir por subdominio (ej: `sensor_ingest_service.py`, `sensor_query_service.py`)

---

## Action Items

- [x] Definir estructura de carpetas (este ADR)
- [ ] Crear `app/core/config.py` con pydantic-settings
- [ ] Crear `app/core/database.py` con `get_db()` dependency
- [ ] Crear `app/core/security.py` con validación HMAC Meta
- [ ] Crear `app/api/v1/routers/whatsapp.py` (webhook handler)
- [ ] Crear `app/services/whatsapp_service.py`
- [ ] Crear `app/schemas/whatsapp.py` con modelos Meta API

---

## References

- [FastAPI — Bigger Applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/)
- [FastAPI — Dependencies](https://fastapi.tiangolo.com/tutorial/dependencies/)
- [docs/ARCHITECTURE.md](./ARCHITECTURE.md) — diagrama de sistema
- [docs/GUARDRAILS.md](./GUARDRAILS.md) — reglas de código
