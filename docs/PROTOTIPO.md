# Prototipo Funcional — Extracción de Conocimiento

> Fuente: https://github.com/Danifelipaez/cienrayas-bot  
> Fecha de análisis: 2026-06-26

Este documento extrae todo lo útil del prototipo para informar el desarrollo del nuevo backend. No es un fork — es una destilación de decisiones ya validadas.

---

## Qué hace el prototipo (resumen ejecutivo)

El bot recibe un mensaje de WhatsApp de un pescador, recopila datos de 3 fuentes externas en paralelo, calcula un semáforo de seguridad (verde/amarillo/rojo), genera texto en dialecto caribeño con Groq/Llama, y opcionalmente envía un mapa. Luego pide feedback al pescador para mejora continua.

---

## Fuentes de Datos Externas (ya validadas)

### 1. Calidad del agua — IDEAM DHIME
- **Qué:** oxígeno disuelto, pH, salinidad (PSU), turbidez (NTU)
- **Cómo:** HTTP a estaciones DHIME, ventana de 7 días
- **Fallback:** valores históricos por mes (2015–2023), diferenciados por época de lluvia/seca del Caribe
- **Cache:** en memoria, refresh cada 24h en background task
- **3 estaciones monitoreadas** cerca de la Ciénaga

### 2. Datos satelitales — NASA ERDDAP (sin autenticación)
- **SST** (temperatura superficial): dataset `jplMURSST41`, resolución 0.01°, lag de 2 días
- **Clorofila-a**: dataset `erdMH1chla8day`, compuesto 8 días, lag de 4 días
- **Bounding box:** lat 10.5–11.2, lon -74.85 a -73.9 (con buffer de 0.15°)
- **Validación:** SST entre 15–40°C, clorofila entre 0–100 mg/m³
- **Cache:** 6 horas en memoria
- **Fallback:** baselines mensuales (ej: 26.5°C para enero)

### 3. Clima — wttr.in (sin autenticación)
- **URL:** `https://wttr.in/{lat},{lon}?format=j1`
- **Parámetros:** temperatura, velocidad viento (km/h), dirección (grados), precipitación (mm)
- **Nota importante:** wttr.in no entrega ráfagas — el prototipo las estima como `wind_speed * 1.4`
- **Dirección:** convierte grados a rosa de vientos de 16 puntos (pasos de 22.5°)
- **Cache:** 10 minutos
- **Coordenadas:** lat 10.8, lon -74.4 (centro de la Ciénaga Grande)

---

## Lógica del Semáforo (core/semaphore.py)

Esta es la lógica más valiosa del prototipo — ya validada con contexto local.

### ROJO (no salir)
- Viento > 30 km/h
- Ráfagas > 45 km/h
- "Viento peligroso" local + velocidad > 25 km/h
- Precipitación > 10 mm
- Combinación viento + lluvia moderada
- Oxígeno disuelto < 3.0 mg/L (mortandad de peces)

### AMARILLO (precaución)
- "Viento peligroso" a velocidad moderada
- Temperatura SST fuera de 25–32°C
- Clorofila baja (baja productividad)
- Oxígeno disuelto 3.0–4.5 mg/L (estrés)
- pH anómalo
- Salinidad > 32 PSU
- Turbidez > 120 NTU

### VERDE (favorable)
- Sin factores de riesgo
- Bonos: alta productividad, temperatura ideal, mar calma, buena oxigenación, agua dulce en época de lluvia, fase lunar activa para camarón

---

## Índice de Potencial Pesquero (IPP) — core/zone_analysis.py

Modelo multivariable 0–100 puntos, ponderado:

| Parámetro | Peso | Nota |
|---|---|---|
| Oxígeno disuelto | 25% | Crítico: sin O₂ no hay peces |
| Temperatura SST | 20% | Metabolismo y migración |
| Salinidad | 20% | Determina composición de especies |
| Clorofila-a | 15% | Proxy de productividad |
| Turbidez | 10% | Eficacia de redes |
| pH | 10% | Estrés ambiental |

### 6 Zonas con gradiente de salinidad

| Zona | Salinidad (PSU) | Especies objetivo | Artes de pesca |
|---|---|---|---|
| Boca de la Barra | 20–36 | Macabí, sábalo | Palangre, trasmallo |
| Nueva Venecia | 8–22 | Lisa, mojarra | Atarraya lisera, boliche |
| Buenavista | 5–18 | Lisa, mojarra lora | Nasa, trasmallo |
| Caño Clarín | 2–12 | Mojarra, camarón | Atarraya camaronera |
| Tasajera/Puebloviejo | 3–15 | Lisa, almeja | Buceo, trasmallo |
| Suroccidente | 0–8 | Mojarra lora, mapalé | Atarraya, nasa |

---

## Prompts y Lenguaje (core/prompts.py)

**Lo más valioso del prototipo para el equipo de contenido:**

- El bot habla como **"CienRayas"**, un pescador caribeño, no como un sistema técnico
- Usa **términos locales validados**:
  - "faena" = jornada de pesca
  - "cardumen" = banco de peces
  - "el Burro" = viento Norte (peligroso)
  - "Leste" = viento del Este (buenas condiciones)
  - "el agua está pesada" = oxígeno disuelto bajo
  - "el agua está verde y cargada" = alta clorofila
- Referencias geográficas locales: "Palancar", "Los Micos"
- Fase lunar integrada para predicción de camarón
- **Límite de 180 palabras** por mensaje
- **≤ 4 emojis** por mensaje
- **Cero unidades técnicas** (nunca mg/L, PSU, NTU al pescador)
- Siempre terminar con recomendación accionable

---

## Arquitectura de Procesamiento del Webhook

```
POST /webhook (Meta)
  ↓
Responder 200 inmediatamente (obligatorio, Meta reintenta si no responde)
  ↓
Background task:
  ├── Detectar duplicado (message_id, TTL 10 min)
  ├── Si es feedback → guardar + responder con empatía
  └── Si es consulta nueva:
        ├── [paralelo] weather.get() + satellite.get() + water_quality.get()
        ├── semaphore.evaluate(datos)
        ├── zone_analysis.rank_zones(datos)
        ├── llm.generate(prompt_construido)
        ├── [si verde] map_generator.create()
        └── whatsapp.send(texto + imagen opcional)
              + pedir feedback
```

---

## Gestión de Estado (core/state.py)

El prototipo usa **diccionario en memoria** con nota explícita de migrar a Redis/DB.

Funciones que necesitamos replicar:
- `is_duplicate(message_id)` — deduplicación con TTL 10 min
- `is_awaiting_feedback(phone)` — estado de conversación por número
- `record_query(phone)` — marcar que se envió respuesta
- `record_feedback(phone, text)` — guardar feedback del pescador
- `looks_like_new_query(text)` — keywords: "puedo pescar", "condiciones", etc.
- `looks_like_feedback(text)` — cualquier otro texto cuando awaiting_feedback

---

## Servicio WhatsApp (services/whatsapp.py)

- **API:** Meta Graph API v19.0
- **Texto:** `POST /messages` con `type: "text"`
- **Imagen:** mismo endpoint con `type: "image"` + URL + caption
- **Auth:** Bearer token en header
- **Timeout:** 15 segundos
- **Manejo de errores:** try/except + re-raise para upstream

---

## Concurrencia y Caching en el LLM

El prototipo resuelve el problema de 15–50 usuarios simultáneos así:
- **Semáforo de concurrencia:** máximo 3 llamadas simultáneas a Groq
- **Cache por color de semáforo:** si el resultado del día es "verde", todos los usuarios en 15 min reciben el mismo texto base (una sola llamada LLM)
- **Retry con backoff exponencial:** 5s, 10s, 15s para rate limits
- **Max tokens:** 400, temperatura: 0.7

---

## Lo que el prototipo NO tiene (y necesitamos en el nuevo backend)

| Faltante | Por qué es necesario |
|---|---|
| Validación HMAC del webhook Meta | El prototipo solo valida verify_token; la firma HMAC es obligatoria para producción |
| Base de datos (conversaciones, sensores) | Todo en memoria — se pierde al reiniciar |
| Ingesta de sensores IoT propios | El prototipo usa solo IDEAM + NASA; tenemos ESP32 propios |
| Registro de usuarios (pescadores) | No hay tabla de users |
| Alertas proactivas | El bot solo responde, no inicia mensajes |
| API key por sensor | No existe — necesitamos autenticación para sensores IoT |
| Hashing de datos sensibles | Sin protección de números de teléfono |
| Tests del webhook | `test_bot.py` simula pero no valida HMAC |

---

## Decisiones del Prototipo que SÍ conservamos

| Decisión | Razón |
|---|---|
| Responder 200 inmediatamente + background task | Meta reintenta si no responde rápido |
| Deduplicación por message_id | Meta reenvía webhooks — sin esto procesa dos veces |
| Cache en capas (memoria, API, histórico) | IDEAM y NASA son lentos; el fallback es crítico |
| Cero unidades técnicas al pescador | Validado con la comunidad |
| LLM con fallback a respuestas predefinidas | Resiliencia cuando la API no está disponible |
| Bounding box Ciénaga Grande | lat 10.5–11.2, lon -74.85 a -73.9 |
| Coordenadas centro | lat 10.8, lon -74.4 |

---

## Stack del prototipo vs Stack del nuevo backend

| Componente | Prototipo | Nuevo backend |
|---|---|---|
| LLM | Groq (Llama 3.3 70B) | Claude Haiku (Anthropic) |
| Hosting | Render | Vercel (serverless) |
| Estado conversación | Dict en memoria | Supabase (PostgreSQL) |
| ORM | Sin ORM | SQLAlchemy 2.0 |
| Sensores IoT | Solo IDEAM/NASA | ESP32 propios + IDEAM/NASA |
| Autenticación webhook | verify_token only | verify_token + HMAC-SHA256 |
| Mapas | matplotlib + contextily | Por definir (misma stack o hosted) |
