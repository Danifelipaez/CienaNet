# Alertas de vendaval/tormenta — dos niveles, backtest real contra el 29-ago-2026

**Estado:** implementado y verificado contra datos reales de un evento real.
**Origen:** vendaval real del 29-30 de agosto de 2026 en el Magdalena (Chibolo,
Concordia, Plato, San Zenón, Santa Ana, Sabanas de San Ángel, Cerro de San Antonio,
Pivijay, Pijiño del Carmen, Ariguaní, Tenerife — caída de árboles, cortes de energía,
~30 viviendas y un colegio afectados en Tenerife), reportado por medios horas antes
de que tocara tierra.

Una primera versión de esta alerta (umbral directo sobre la ráfaga pronosticada de
Open-Meteo) se implementó sin poder correr el backtest — el entorno donde se
investigó tenía la red bloqueada. En una sesión posterior sí hubo red real, se corrió
el backtest, y el resultado fue que **esa primera versión no habría disparado el
29-ago-2026**. Este documento describe el diseño que la reemplazó.

## Por qué la versión anterior no servía (verificado con datos reales)

`vendaval_risk()` disparaba si el pronóstico horario de `wind_gusts_10m` en el
centroide CGSM cruzaba 62 km/h. Ráfaga real pronosticada ese día en ese punto:

| Corrida | Ráfaga máx pronosticada |
|---|---|
| Emitida 2 días antes | 20,5 km/h |
| Emitida 1 día antes | 21,6 km/h |
| Mejor análisis (re-análisis) | 42,5 km/h |
| **Umbral configurado** | **62,0 km/h** |

Nunca cruzó el umbral, en ningún punto del Magdalena ese día. Peor: el 30-ago (un
día sin vendaval reportado) el re-análisis dio 55,1 km/h en Tenerife — más alto que
el día que tumbó 30 casas. `wind_gusts_10m` de un modelo global no tiene destreza
para un *downburst* (corriente descendente de una tormenta): es de escala sub-malla,
la parametrización de ráfaga no lo ve.

Bajar el umbral tampoco funciona: un índice ambiental (CAPE≥1500 + CIN≤50 +
T−Td≥12°C) sobre 6 días de backtest dispara 4/6 días en Chibolo/Tenerife (temporada
de lluvias, convección diaria tierra adentro) y 0/6 en la CGSM. Es buen
discriminador geográfico — por eso sobrevive como *outlook* de dashboard — pero un
push diario tierra adentro mataría la confianza del pescador por fatiga de alerta.

## Diseño: dos niveles

```
Nivel 1 — OUTLOOK (24-48h)   → dashboard, SIN push. "condiciones favorables".
Nivel 2 — NOWCAST (≥1h)      → push WhatsApp. Sistema real detectado, en movimiento.
```

### Nivel 1 — Outlook (`signals.py::vendaval_risk`)

Índice ambiental sobre `ingestion/weather.py::get_convective_forecast()` (CAPE,
lifted index, CIN, punto de rocío, temperatura, ráfaga — mismo patrón de cache/
reintentos que el resto de `ingestion/`). Nunca dispara WhatsApp: solo alimenta
`GET /data/latest` → `senales.vendaval`, con `"nivel": "bajo"|"medio"|"alto"` y
`"estimacion": true`.

### Nivel 2 — Nowcast por rayos (`signals.py::tormenta_aproximandose`)

Fuente: **GOES-19 GLM** (mapeador de rayos), bucket público `noaa-goes19` en AWS S3,
sin auth. De las fuentes evaluadas para nowcasting es la única con cobertura real
sobre la Ciénaga y con archivos históricos disponibles para backtest:

| Fuente | Estado |
|---|---|
| **GOES-19 GLM** | ✅ Elegida — sin auth, ~350 KB por archivo cada 20s, HDF5 real (confirmado con `xxd`, firma `89 48 44 46`), `h5py` los abre sin depender de `netCDF4`. |
| Radar compuesto IDEAM | Bucket accesible, pero sin cobertura de radar sobre la CGSM ni el Magdalena central (red interior: Munchique, Barrancabermeja, Tablazo...). Descartado. |
| GOES-19 ABI (`ABI-L2-MCMIPF`) | Accesible, cada 10 min, pero mucho más pesado que GLM para el mismo propósito. |
| NOAA NESDIS (JPEG geoestacionario) | El CDN solo guarda ~2 días — no permite backtest. Descartado. |
| IDEAM Socrata (viento, alertas) | Sin estaciones en el Caribe / sin dataset de vendaval. Descartado. |

`ingestion/lightning.py::get_lightning_flashes()` descarga los últimos
`settings.glm_files_per_ciclo` archivos GLM-L2-LCFA (~1 min de destellos, ~1 MB),
los filtra a la caja del corredor (`settings.corredor_lat/lon_min/max`: Cesar →
Magdalena centro) y devuelve `{lat, lon, timestamp}` por destello.

`signals.py::tormenta_aproximandose(anterior, actual, ...)` compara dos
instantáneas (~10 min aparte): calcula el centroide de cada una, ve si se está
acercando al centro de la CGSM, y si sí, proyecta un ETA lineal. Si
`eta_min <= settings.nowcast_eta_max_min` (default 90), es accionable — este SÍ
dispara WhatsApp vía `alert_service.py::maybe_send_storm_alert()`.

Corre cada 10 min (`app/main.py::_nowcast_refresh`, separado de
`_hourly_refresh` porque el cálculo de velocidad necesita instantáneas cercanas
en el tiempo, no una por hora).

## Backtest: `scripts/verify_glm_lead_29ago.py`

Descarga los ~1800 archivos GLM del 29-ago-2026 sobre el corredor (sin
submuestreo) y mide el lead real del mecanismo de centroide+ETA contra el
colapso de capa límite documentado en Tenerife (18h local / 23:00 UTC — la
huella del downburst tocando el pueblo).

**Resultado: 270 minutos de lead** (primera señal accionable a las 18:30 UTC, ETA
80 min a Tenerife; impacto documentado a las 23:00 UTC). Reproducible con:

```bash
pip install h5py
python scripts/verify_glm_lead_29ago.py
```

### Límite conocido (no es una falla de este diseño)

Un primer intento del backtest medía el lead contra **Chibolo** en vez de Tenerife
y daba solo 10-40 min — parecía un fallo. No lo es: la actividad de rayos en *todo*
el corredor apareció recién a las 18:00 UTC, exactamente cuando el colapso de capa
límite de Chibolo ya empezaba — la tormenta se formó encima de su propio objetivo.
Ningún método de monitoreo puede anticipar una tormenta que nace donde va a pegar;
es un límite físico, no algo que un nowcast distinto resolviera. Tenerife, en
cambio, fue alcanzado por un sistema que venía moviéndose desde la frontera con
Cesar durante ~4 horas — ese es el caso que sí puede (y debe) anticiparse, y es el
caso relevante para proteger la CGSM, que es un objetivo lejano al que un sistema
tendría que acercarse, no formarse encima.

Consecuencia práctica: este nowcast avisa de sistemas que se acercan por el
corredor. Una tormenta que se forma súbitamente cerca de la propia CGSM no daría
lead — igual que le pasó a Chibolo ese día.

## Mensaje que recibe el pescador

> ⚡ Tormenta fuerte acercándose desde el sur, llega en ~45 min. No salgas a pescar
> ahora y asegura tu embarcación.

Corto, con acción concreta, según `docs/GUARDRAILS.md`.

## Pendiente

- **Crear y aprobar `alerta_tormenta` en Meta Business Manager** — sin esto el
  envío real de WhatsApp falla en producción (`send_template_message` retorna
  `None`, se loggea el error, no se cae el proceso).
- **Validar con Diego** el radio de la zona de pesca y el ETA máximo de 90 min.
- **DIMAR/CIOH** (avisos marítimos de la Capitanía de Puerto Santa Marta) como
  fuente complementaria específica para navegación — no investigado en esta ronda.
