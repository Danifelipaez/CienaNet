# Alerta de vendaval — fuentes investigadas e implementación

**Estado:** implementado (umbral sobre pronóstico Open-Meteo) · fuente oficial IDEAM
pendiente de verificación de endpoint con red real (ver "Pendiente" abajo).
**Origen:** vendaval real del 29-30 de agosto de 2026 en el Magdalena (Chibolo,
Concordia, Plato, San Zenón, Santa Ana, Sabanas de San Ángel, Cerro de San Antonio,
Pivijay, Pijiño del Carmen, Ariguaní, Tenerife — caída de árboles, cortes de energía,
~30 viviendas y un colegio afectados en Tenerife), reportado por medios horas antes
de que tocara tierra. Pregunta original: ¿de dónde se puede sacar esa alerta para
avisar a los pescadores con anticipación, igual que hicieron los medios?

## Fuentes investigadas

| Fuente | Qué ofrece | Formato | Estado |
|---|---|---|---|
| [IDEAM — Datos abiertos de alertas](http://www.pronosticosyalertas.gov.co/en/datos-de-alertas) | Alertas por municipio: fenómeno (incluye vendaval), nivel, municipio, departamento, región, fecha/hora inicio-fin, sinopsis | Descarga CSV/TXT (portal con selector, no confirmado como endpoint REST/JSON) | Reachable: **no verificado** — dominio bloqueado por el proxy de egress de este entorno de investigación |
| [IDEAM — Boletines, avisos y alertas](http://www.pronosticosyalertas.gov.co/en/boletines-avisos-y-alertas) | Boletines técnicos diarios (BADT deslizamientos, BAH hidrológico, etc.) | Boletines PDF/web, no dataset estructurado | No verificado (mismo dominio bloqueado) |
| [IDEAM — Datos abiertos de pronóstico del tiempo](http://www.pronosticosyalertas.gov.co/en/datos-abiertos-ideam) | Pronóstico por municipio: viento (velocidad/dirección), presión, precipitación, 3h a 8 días | CSV/TXT | No verificado (mismo dominio) |
| IDEAM Socrata (`datos.gov.co`) — mismo backend que ya usa `ideam_hidro.py` | Estaciones/variables hidrometeorológicas (lluvia, nivel de río, temperatura) | JSON, sin auth, ya verificado en este proyecto (`docs/IDEAM_GBIF_VALIDACION.md`) | **No tiene** dataset de avisos/alertas por fenómeno — se buscó explícitamente, no aparece en el catálogo Socrata |
| **Open-Meteo** (`api.open-meteo.com`) | Pronóstico horario de ráfaga de viento (`wind_gusts_10m`), hasta 16 días | JSON, sin auth | ✅ Ya integrado en el proyecto (`app/services/ingestion/weather.py`) para clima actual — **esta es la fuente que se usó para implementar la alerta** |
| DIMAR/CIOH (Capitanía de Puerto Santa Marta) — avisos marítimos | Viento/oleaje específico para navegación | No investigado | Candidato a futuro, ver "Pendiente" |

## Por qué se implementó con Open-Meteo y no con el CSV de IDEAM

El servicio de "Datos abiertos de alertas" de IDEAM es, según toda la documentación
pública encontrada, un **portal de descarga CSV/TXT con selector** (fenómeno,
municipio, departamento, rango de fechas) — no se encontró un endpoint JSON/REST
documentado, a diferencia de:
- el RSS de NOAA NHC que ya usa `alerts_ext.py::get_cyclone_alerts()`, o
- el propio backend Socrata de IDEAM (`s54a-sgyg`, `bdmn-sqnh`) que ya usa
  `ideam_hidro.py`, verificado con `curl` real (`docs/IDEAM_GBIF_VALIDACION.md`).

Desde este entorno de investigación, tanto `ideam.gov.co` como
`pronosticosyalertas.gov.co` están bloqueados por el proxy de egress — no fue
posible confirmar con `curl`/`WebFetch` la URL exacta de descarga ni sus parámetros.
Siguiendo la misma disciplina que ya usa este repo (nunca integrar una URL sin
verificarla primero — ver el propio `IDEAM_GBIF_VALIDACION.md`), no se hardcodeó
un scraper contra una URL adivinada.

En cambio, se implementó una alerta **igual de real y con anticipación real**
usando una fuente que este mismo proyecto ya integró y verificó: el pronóstico
horario de ráfaga de Open-Meteo. Como el pronóstico mira hacia adelante (hasta 48h,
configurable), el scheduler horario (`app/main.py::_hourly_refresh`) puede detectar
una ráfaga por encima del umbral **antes** de que ocurra — el mismo efecto de
"avisaron horas antes" que lograron los medios el 29 de agosto, sin depender de un
scraper no verificado.

## Qué se implementó

1. **`app/services/ingestion/weather.py::get_wind_gust_forecast()`** — pronóstico
   horario de `wind_gusts_10m` para las próximas N horas (`settings.vendaval_forecast_hours`,
   default 48h). Mismo patrón que el resto de `ingestion/`: cache en memoria, reintentos
   con backoff, fallback a la última respuesta buena, nunca inventa un valor si la
   fuente falla (`origen: "sin_dato"`).
2. **`app/services/signals.py::vendaval_risk()`** — función pura: primera hora del
   pronóstico que cruza `settings.vendaval_gust_threshold_kmh` (default 62 km/h,
   piso de "vendaval" en escala Beaufort grado 8 — **no es un número oficial de
   IDEAM**, no se encontró uno publicado; queda configurable por env var para que el
   equipo lo ajuste si consigue uno). A diferencia de `anoxia_risk`/`pulso_agua_dulce`,
   no es una estimación compuesta — es un umbral directo sobre un dato real.
3. **`app/models/environmental.py::ExternalAlert`** — la tabla `external_alerts` existe
   desde la migración 001 (pensada para "NOAA NHC, IDEAM" según `ARCHITECTURE.md`) pero
   nunca tuvo modelo ORM ni se escribía; ahora persiste cada alerta de vendaval
   disparada (auditoría — no la lee el bot, cero red desde el bot).
4. **`app/models/messaging.py::AlertLog.alert_type`** (migración 013) — hasta ahora
   `alert_log` solo tenía alertas de semáforo; se agregó esta columna para que
   `maybe_send_wind_alert()` pueda compartir la misma tabla de auditoría sin romper
   el dedup existente de `maybe_send_alert()` (que ahora filtra `alert_type='semaforo'`).
5. **`app/services/alert_service.py::maybe_send_wind_alert()`** — mismo patrón que
   `maybe_send_alert`: advisory lock propio, dedup (no reenvía si la hora pronosticada
   no cambió desde la última alerta), envía WhatsApp a `users.alertas_activas=True`
   vía template `alerta_vendaval` (⚠️ **falta crear y aprobar este template en Meta
   Business Manager**, mismo pendiente operativo que ya tenía `alerta_condicion`).
6. Enganchado en `app/main.py::_hourly_refresh()`, después de la alerta de semáforo.
7. Expuesto en el dashboard como `senales.vendaval` (`GET /data/latest`), igual que
   `senales.anoxia`/`senales.pulso_agua_dulce`.

## Mensaje que recibe el pescador

> ⚠️ Viento fuerte anunciado para el 30/08 14:00, con ráfagas de hasta 65 km/h.
> Evita salir a pescar en ese horario y asegura bien tu embarcación.

Corto, sin jerga, con acción concreta — según `docs/GUARDRAILS.md`.

## Pendiente

- **Verificar el endpoint real de IDEAM** desde una red sin el bloqueo de este
  entorno (`curl -v` a `pronosticosyalertas.gov.co/en/datos-de-alertas` y observar
  la petición que dispara su selector de descarga, o escribir a IDEAM pidiendo
  documentación de API — ambos casos igual que se hizo para GBIF/Socrata en
  `IDEAM_GBIF_VALIDACION.md`). Si aparece un endpoint estructurado (JSON o CSV con
  URL fija y parámetros), agregar `get_ideam_avisos()` a `app/services/ingestion/alerts_ext.py`
  siguiendo exactamente el patrón de `get_cyclone_alerts()` — la persistencia
  (`ExternalAlert`) y el envío (`maybe_send_wind_alert`) ya están listos para recibir
  una segunda fuente sin cambios adicionales; solo faltaría sumar sus resultados
  antes de decidir si avisar.
- **Crear y aprobar `alerta_vendaval` en Meta Business Manager** — sin esto, el envío
  real de WhatsApp falla en producción (`whatsapp_service.send_template_message`
  retorna `None`, se loggea el error, no se cae el proceso).
- **Validar el umbral de 62 km/h con el equipo** (Diego/Daniel) — es un valor de
  literatura meteorológica general, no un umbral oficial de IDEAM ni ajustado a la
  CGSM específicamente.
- **DIMAR/CIOH** (avisos marítimos de la Capitanía de Puerto Santa Marta) como
  fuente complementaria específica para navegación — no investigado en esta ronda,
  candidato natural si se quiere una alerta más específica que el vendaval terrestre.
