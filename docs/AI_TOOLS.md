# Tool-calling del AIProvider — consultas generales para histórico y actual

El asistente de IA interno (`app/services/ai_service.py`, hoy `GeminiProvider`) puede
invocar un catálogo fijo de "consultas generales" en vez de limitarse al texto de
contexto que ya viene en el `system prompt`. Esto le da acceso a datos **históricos**
(que antes no existían para la IA) y a detalle **actual** que el resumen de
`ai_context.py::build_ai_context()` no incluye (pH, conductividad, nivel de agua,
desglose satelital por zona, tendencias).

El catálogo vive en `app/services/ai_tools.py` — agregar un tool nuevo es agregar una
entrada a `TOOLS`, no tocar el loop de `ai_service.py`.

## Catálogo

| Tool | Parámetros | Envuelve | Para qué |
|---|---|---|---|
| `condicion_actual` | ninguno | `snapshot_service.read_persisted(db)` | Estado actual completo: semáforo, clima, agua (pH/conductividad/nivel), satélite por zona, tendencias 24h/7d |
| `historico_ambiental` | `dias` (int, 1-365) | `dashboard_history.get_history(db, dias)` | Series de tiempo: clima, agua, semáforo, capturas |
| `donde_pescar` | ninguno | `points_service.get_points(db)` | Ranking de zonas/puntos por IPP |
| `zonas_sedimentacion` | ninguno | `sedimentation_service.get_sedimentation_zones(db)` | Zonas con sedimentación reportada |
| `alertas_activas` | ninguno | `alert_service.get_alert_status(db)` | Color del semáforo, ciclones NOAA, tormenta por rayos (nowcast) |
| `calidad_agua_estaciones` | `variable` (str, opcional, ver `invemar_calidad.VARIABLES`) | `snapshot_service.get_calidad_agua_persistida(db, variable)` | Calidad del agua por estación INVEMAR/REDCAM (oxígeno disuelto, salinidad, pH, temperatura, SST) con clase de calidad, ya persistida — cero red por mensaje |

Cada tool es de solo lectura — ninguno dispara envíos de WhatsApp ni escribe en la DB.

## Cómo se activa

`AIProvider.reply_text()`/`answer_structured()` reciben un parámetro opcional `db`.
Si se pasa una sesión, `GeminiProvider` declara el catálogo como `functionDeclarations`
en la llamada a Gemini; si no se pasa `db`, el comportamiento es idéntico al de antes
(sin tools). Los dos consumidores actuales ya pasan `db`:

- `app/services/message_router.py` — fallback de WhatsApp para lo que no matchea
  ninguna intención por keyword.
- `app/api/v1/routers/dashboard.py::ask_ai` — chat del dashboard.

## El loop

Cuando el modelo responde con un `functionCall` en vez de texto, `ai_service.py`
ejecuta el handler correspondiente y reenvía el resultado como `functionResponse`
en el siguiente turno — hasta 4 idas y vueltas (`_MAX_TOOL_ROUNDS`). Si el modelo
no se detiene en ese límite, la llamada devuelve `None` (WhatsApp cae a
`_NO_ENTENDI`, el dashboard cae a la respuesta de "limitaciones").

Formato REST de Gemini (`generativelanguage.googleapis.com/v1beta`), sin SDK:

```json
// El modelo pide una función:
{"candidates": [{"content": {"parts": [
  {"functionCall": {"name": "historico_ambiental", "args": {"dias": 7}}}
]}}]}
```
```json
// Se reenvía el resultado ejecutado localmente:
{"role": "function", "parts": [
  {"functionResponse": {"name": "historico_ambiental", "response": {...}}}
]}
```

## Notas

- El camino rápido (preguntas simples sobre el presente) no cambia: `build_ai_context()`
  sigue inyectando el resumen actual en el `system prompt`, así que la mayoría de
  preguntas se resuelve en una sola llamada a Gemini. El loop de tools solo se activa
  cuando el modelo decide que lo necesita (típicamente preguntas históricas).
- `alertas_activas.tormenta_nowcast` viene de memoria de proceso
  (`lightning.get_ultimo_nowcast()`) — puede ser `null` justo después de un reinicio
  del backend, no significa que no haya tormenta.
- Procesamiento secuencial: si Gemini pide varias funciones en el mismo turno, solo se
  ejecuta la primera. Subir a manejo paralelo si esto empieza a pasar en la práctica.
