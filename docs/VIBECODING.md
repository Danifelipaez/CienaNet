# Mejores Prácticas de Vibecoding — Recomendaciones de Expertos

Vibecoding = desarrollo de software asistido por IA donde el desarrollador guía con intención y contexto, y la IA genera o completa el código. Estas prácticas están basadas en directrices de Anthropic, Google DeepMind, OpenAI, ThoughtWorks, y la comunidad de Cursor/GitHub Copilot.

---

## PRINCIPIOS FUNDAMENTALES

### 1. Contexto es todo (Anthropic / Claude)
La IA genera mejor código cuando tiene contexto rico. Siempre proveer:
- **Qué** debe hacer la función (propósito, no implementación)
- **Por qué** existe (contexto de negocio)
- **Qué NO debe hacer** (restricciones, casos edge)
- **Qué ya existe** (referencias a otros módulos del proyecto)

**Práctica:** Antes de pedir código, describir el contexto en 2-3 oraciones. La IA hace mejor trabajo con más contexto que con menos.

### 2. IA como copiloto, no como piloto (ThoughtWorks / Martin Fowler)
- El desarrollador define la arquitectura, la IA ayuda con implementación
- Revisar cada bloque de código generado como si fuera un PR de un junior
- La responsabilidad del código es del desarrollador que lo aprueba, no de la IA
- Nunca hacer commit sin entender lo que se está commiteando

### 3. Tareas pequeñas, iteraciones frecuentes (Google / Cursor best practices)
- Pedir una función/clase a la vez, no todo el módulo
- Completar y validar antes de pasar a la siguiente tarea
- Git commit frecuente: si la IA introduce un bug, poder revertir sin perder trabajo

### 4. Test primero, código después (OpenAI / GitHub Copilot)
- Escribir (o pedir a la IA que escriba) el test antes de la implementación
- Los tests son la especificación — si la IA los pasa, el código está bien
- Para este proyecto: mínimo un test por endpoint de webhook y sensor

---

## CÓMO ESTRUCTURAR PROMPTS EFECTIVOS

### Plantilla recomendada para pedir código

```
Contexto: [qué parte del sistema estamos en, qué hace este módulo]

Tarea: [qué función/clase/endpoint necesito]

Restricciones:
- [regla 1]
- [regla 2]

Entradas: [tipos de datos de entrada]
Salidas: [qué debe retornar]

Referencia: [otros archivos del proyecto relevantes]
```

### Ejemplos concretos para este proyecto

**Malo:** "Crea el webhook de WhatsApp"

**Bueno:** 
```
Contexto: backend FastAPI en /api/v1/webhook/whatsapp. Meta envía 
un POST con payload JSON firmado con HMAC-SHA256.

Tarea: crear el endpoint POST /webhook/whatsapp que valide la firma 
HMAC, extraiga el mensaje del payload y llame a MessageService.process().

Restricciones:
- Validar firma ANTES de parsear body
- Retornar 200 inmediatamente a Meta (tienen timeout de 20s)
- No loggear content de mensajes, solo wa_message_id
- Usar el modelo WhatsAppWebhookPayload de /models/whatsapp.py

Entradas: Request de FastAPI + X-Hub-Signature-256 en header
Salidas: {"status": "ok"} con HTTP 200
```

---

## FLUJO DE TRABAJO RECOMENDADO

### Para cada feature nueva

```
1. PLANEAR (humano)
   └── Escribir la historia de usuario en INVEST
   └── Definir los endpoints/funciones necesarios
   └── Identificar modelos de DB que se necesitan

2. ESQUEMA (IA + humano)
   └── Pedir a IA que proponga estructura de archivos
   └── Revisar y aprobar antes de generar código

3. MODELOS PRIMERO (IA)
   └── Generar Pydantic models y SQLAlchemy models
   └── Revisar tipos, validaciones, campos opcionales

4. TESTS (IA + humano)
   └── Generar tests del comportamiento esperado
   └── Revisar que cubran casos edge y errores

5. IMPLEMENTACIÓN (IA)
   └── Generar service → router → en ese orden
   └── Revisar cada función antes de pasar a la siguiente

6. INTEGRACIÓN (humano)
   └── Probar manualmente el flujo completo
   └── Verificar con Postman / curl antes de commit

7. COMMIT (humano)
   └── Mensaje descriptivo con contexto
   └── PR pequeño, máximo 200 líneas de diff
```

---

## ESTRUCTURA DE PROYECTO RECOMENDADA

```
app/
├── api/
│   └── v1/
│       ├── routers/          ← solo HTTP, sin lógica
│       │   ├── webhook.py
│       │   └── sensors.py
│       └── dependencies.py   ← auth, db sessions
├── services/                 ← lógica de negocio aquí
│   ├── message_service.py
│   ├── sensor_service.py
│   └── alert_service.py
├── models/                   ← SQLAlchemy ORM models
│   ├── user.py
│   ├── conversation.py
│   └── sensor_reading.py
├── schemas/                  ← Pydantic schemas (request/response)
│   ├── whatsapp.py
│   └── sensor.py
├── core/
│   ├── config.py             ← variables de entorno con pydantic-settings
│   ├── database.py           ← engine, session
│   └── security.py           ← HMAC validation, hashing
└── main.py                   ← FastAPI app + routers
```

**Regla:** Si la IA genera código en el lugar equivocado (ej: lógica en el router), pedirle que lo mueva al service correspondiente antes de aceptarlo.

---

## HERRAMIENTAS RECOMENDADAS PARA VIBECODING

| Herramienta | Uso |
|-------------|-----|
| **Claude (Anthropic)** | Diseño de arquitectura, explicaciones, código complejo |
| **GitHub Copilot** | Autocompletado en el editor, código repetitivo |
| **Cursor IDE** | Edición con IA integrada, refactoring |
| **Claude en terminal (claude.ai)** | Revisión de PRs, debugging, preguntas rápidas |

### Cuándo usar cada uno
- **Diseño y arquitectura** → Claude con contexto completo del proyecto
- **Código boilerplate** → Copilot inline
- **Debugging de errores** → Claude con stack trace completo
- **Refactoring** → Cursor con el archivo abierto
- **Revisión de seguridad** → Claude con el archivo completo

---

## SEÑALES DE QUE ALGO SALIÓ MAL

Detectar y corregir inmediatamente si la IA genera:

- Código sin manejo de errores (`try/except` vacíos o ausentes)
- Credenciales hardcodeadas (aunque sean de ejemplo)
- Funciones de más de 50 líneas sin justificación
- Imports que no existen en el proyecto
- Código que "funciona en teoría" pero no fue probado
- Comentarios que explican *qué* hace el código en vez de *por qué*
- Cualquier uso de `time.sleep()` en código de producción (usar async)

---

## FUENTES DE REFERENCIA

- [Anthropic — Building with Claude](https://docs.anthropic.com/en/docs/build-with-claude/overview)
- [Google — Responsible AI Practices](https://ai.google/responsibility/responsible-ai-practices/)
- [ThoughtWorks — AI-Augmented Development](https://www.thoughtworks.com/insights/topic/generative-ai)
- [GitHub — Copilot Best Practices](https://docs.github.com/en/copilot/using-github-copilot/best-practices-for-using-github-copilot)
- [FastAPI — Best Practices](https://fastapi.tiangolo.com/tutorial/)
- [Cursor — Documentation](https://docs.cursor.com/)
