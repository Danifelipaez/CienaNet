# CienaNet Bot — Contexto para IA

Este archivo es el punto de entrada para cualquier asistente de IA trabajando en este repositorio. Leer antes de generar cualquier código.

## ¿Qué es esto?
Backend FastAPI para **CienRayas**, una app que entrega información ambiental de la Ciénaga Grande de Santa Marta a pescadores artesanales vía WhatsApp. Ver `/docs/CONTEXT.md` para contexto completo.

## Stack
Python 3.11 + FastAPI + Supabase (PostgreSQL) + Meta WhatsApp Cloud API. Desplegado en servidor universitario (principal) + Vercel (respaldo/staging). Ver `/docs/STACK.md` y `/docs/DEPLOYMENT.md`.

## Estructura del proyecto
```
app/
├── api/v1/routers/   ← solo HTTP, sin lógica de negocio
├── services/         ← toda la lógica aquí
├── models/           ← SQLAlchemy ORM
├── schemas/          ← Pydantic request/response
└── core/             ← config, db, security
docs/                 ← documentación para IA y equipo
```

## Reglas que siempre aplican
1. Validar firma HMAC en TODOS los webhooks de Meta antes de procesar
2. Nunca loggear contenido de mensajes de usuarios ni números de teléfono completos
3. Lógica de negocio en `/services/`, nunca en routers
4. Type hints en todas las funciones, Pydantic para todos los inputs externos
5. Variables sensibles solo en `.env`, nunca en código

Ver `/docs/GUARDRAILS.md` para la lista completa.

## Cómo trabajar con IA en este proyecto
Ver `/docs/VIBECODING.md` — incluye plantilla de prompts y flujo de trabajo.

## Documentación disponible
- `/docs/CONTEXT.md` — Proyecto, usuarios, problema, equipo
- `/docs/ARCHITECTURE.md` — Diagrama del sistema, flujos, schema de DB
- `/docs/STACK.md` — Decisiones técnicas y por qué
- `/docs/GUARDRAILS.md` — Qué hacer y no hacer
- `/docs/VIBECODING.md` — Mejores prácticas de desarrollo con IA
- `/docs/WHATSAPP_API.md` — Integración Meta WhatsApp (webhook, envío, plantillas)
- `/docs/IOT_SENSORES.md` — Red de sensores ESP32, protocolo, calibración
- `/docs/DEPLOYMENT.md` — Despliegue (servidor universitario + Vercel), variables por deployment, runbook
