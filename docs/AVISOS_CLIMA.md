# Avisos del tiempo para pescadores

**Estado:** implementado (oct-2026). Complementa los nowcast que ya existían
(`docs/ALERTAS_LLUVIA.md`, `docs/ALERTAS_VENDAVAL.md`): aquellos avisan con 10-90 min de
antelación; estos, con horas o días.

## Qué cubre y de dónde sale

| Evento | Fuente | Regla para empujar WhatsApp (nivel "alto") | Solo panel (nivel "medio") |
|---|---|---|---|
| Viento fuerte / "ventiscas" | Open-Meteo: ECMWF IFS 0.25, GFS, ICON | ≥2 modelos con viento ≥30 km/h o ráfaga ≥45 km/h en las próximas 36 h (umbrales del semáforo rojo) | 1 modelo |
| Lluvia fuerte / aguacero | Mismos 3 modelos | ≥2 modelos con ≥10 mm en un bloque de 6 h, todo dentro de las próximas 36 h | 1 modelo |
| Mar picado / mar de leva | Open-Meteo Marine: ECMWF WAM, GFS-Wave, MFWAM en 11.05, -74.45 | ≥2 modelos con ola ≥1.5 m | 1 modelo |
| Alerta oficial IDEAM | CAP 1.2 `alertascap.ideam.gov.co/ospa/xml` (registrado ante la OMM) | Mar "Caribe central": naranja o roja. Cuencas de la CGSM (Cga. Grande, Aracataca, Fundación, Sevilla, bajo Magdalena): solo roja | Amarilla, o naranja en cuencas |
| Ciclón tropical | NOAA NHC `CurrentStorms.json` | A ≤1000 km de la CGSM | 1000-2000 km |
| Frente frío | Discusión tropical (TWD) del NHC, secciones del Caribe | El NHC lo ubica sobre Colombia / SW del Caribe | Frente en el Caribe sin afectar; su viento y oleaje los avisa el consenso |
| Temporada seca / de lluvias | Calendario climatológico + estado ENSO del NOAA CPC | 15 días antes del inicio típico | Siempre visible en el panel |
| Tormenta eléctrica cercana | GOES-19 GLM (ya existía) | ver `ALERTAS_VENDAVAL.md` | — |

Código: `app/services/avisos.py` (consenso + orquestación), `avisos_oficiales.py`
(IDEAM, NHC, temporada), `temporadas.py`, `ingestion/avisos_ext.py`,
`ingestion/ideam_cap.py`, envío en `avisos_push.py`. Corre en cada refresco horario
(`app/main.py::_hourly_refresh`) y queda en `senales.avisos` de `GET /data/latest`.

### Por qué consenso
Un solo modelo global falla seguido en un punto (el 31-oct-2026 ECMWF daba 0.3 mm y GFS
6.4 mm para el mismo día). Pedir que dos modelos independientes coincidan baja las
falsas alarmas — y una alerta falsa le cuesta un día de pesca al pescador y credibilidad
al sistema (`GUARDRAILS.md`). Con un solo modelo el aviso queda como "posible" en el panel
y en la respuesta a *avisos*, sin push.

### Calibración (2 años de pronósticos archivados, 2024-2025)
Historical Forecast API de Open-Meteo, día cuenta si ≥2 de 3 modelos cumplen.

| Regla | Días en 2 años | Meses |
|---|---|---|
| Viento ≥30 o ráfaga ≥45 km/h (**usada**) | 9 | feb-mar |
| Viento ≥35 o ráfaga ≥55 km/h | 2 | feb-mar |
| Lluvia ≥20 mm/6 h | 1 | ago |
| Lluvia ≥10 mm/6 h (**usada**) | 22 | abr-jun, ago-nov |
| Lluvia ≥8 mm/6 h | 34 | abr-nov |
| Ola ≥2.0 m (best match) | 0 | — |
| Ola ≥1.5 m (**usada**) | 39 | ene-abr, jul |

Los modelos globales suavizan el aguacero puntual: 20 mm/6 h casi nunca aparece en el
punto aunque en la realidad llueva así. **No hay backtest contra lluvia/viento medidos**:
la tabla dice qué tan seguido dispararía, no cuántas veces acertaría. Pendiente: contrastar
con las estaciones IDEAM de datos.gov.co (`s54a-sgyg` precipitación, `sgfv-3yp8` viento).
ICON da vientos más bajos que los otros dos en la CGSM (máx. 21.7 km/h en 2 años), así que
en la práctica el aviso de viento exige ECMWF + GFS; la ráfaga de GFS es poco confiable
(sale menor que el viento sostenido en la mitad de las horas).

## Dedup y envío (`avisos_push.py`)
- Clave por aviso en `alert_log.zonas`: día local del evento (viento/lluvia/oleaje),
  `evento:día` (IDEAM, que reemite la misma alerta con otro id en cada boletín), semana ISO
  (frente frío), `id:categoría` del ciclón (sube a huracán → se reenvía) y `temporada:año`.
- Guarda extra de 12 h para los diarios (mismo tipo, y para IDEAM mismo evento): un evento
  que cruza la medianoche cambia de clave y no debe reenviarse a las pocas horas.
- Varios avisos nuevos en el mismo ciclo salen en **un** mensaje por pescador.
- Si todos los envíos fallan no se registra nada: el siguiente refresco lo reintenta.
- Template de Meta `aviso_clima` (un parámetro, sin saltos de línea) **por crear y aprobar**;
  con `WHATSAPP_PROVIDER=evolution` sale como texto plano.

## Bot
- *avisos* / *pronóstico*: avisos confirmados, los "posibles", qué fuentes no se pudieron
  revisar y la temporada con el efecto ENSO.
- Saludo y *condición* agregan solo los avisos confirmados.
- El prompt de IA recibe los avisos (reemplaza la alerta IDEAM fija de sep-2026, que seguía
  mostrándose como "vigente" en oct-2026).

## Falla clara
Cada fuente devuelve `origen` medido/cache/sin_dato (`senales.avisos.origen`). Un pronóstico
de más de 6 h no se usa como respaldo. Fuente caída → el tipo queda en `sin_revisar`, y el
panel y el bot dicen "No pude revisar: …" en vez de "sin avisos". Errores al log como
`warning` (fuente) o `error` (envío / bug del cálculo).

## Temporadas (litoral del Magdalena)
Régimen bimodal, ERA5 1991-2020 en 10.75, -74.5 (mm/mes): ene 7, feb 6, mar 16, abr 58,
may 137, jun 90, jul 69, ago 102, sep 143, oct 215, nov 151, dic 39. IDEAM: seca del Caribe
"diciembre, enero, febrero y comienzos de marzo"; lluvias frecuentes en el norte desde
mediados de mayo. Calendario usado: lluvias 1 desde 15-abr, veranillo 20-jun, lluvias 2
15-ago, seca 15-dic. Es climatología: el inicio real se corre semanas. ENSO del CPC
(`ensodisc.shtml`, sale el segundo jueves de cada mes): El Niño → temporada más seca y
caliente (ciénaga más baja y salada); La Niña → más lluviosa. Oct-2026: El Niño fuerte
(Advisory), probable hasta ene-mar 2027.

## Xweather (cuota)
- Plan Developer: **15.000 tokens por periodo**, compartidos con las teselas de radar del
  frontend (`CienaRed-Frontend/app/api/tiles/radar`). Cada respuesta trae
  `x-ratelimit-remaining-period` y `x-ratelimit-reset-period`; el backend los guarda en
  `senales.avisos.xweather_cuota`.
- Uso del backend: `/forecasts` (1 token) **solo** cuando 1 de 3 modelos ve viento o
  lluvia, cacheado 3 h, sin reintentos → máximo 8 tokens/día, típico 0-3. Se apaga solo si
  quedan menos de `XWEATHER_RESERVA_TOKENS` (1000) para no dejar el mapa sin radar.
- Medición del 31-oct-2026 08:24 UTC: quedaban 8.515 de 15.000, reinicio 23-nov-2026
  00:00 UTC (≈22,6 días). Peor caso del backend hasta el reinicio: 8 × 22,6 ≈ 181 tokens.
  El radar por diseño gasta como mucho 144/día (≈3.260 hasta el reinicio): 181 + 3.260 <
  8.515, alcanza. Pero el consumo medido del periodo (~6.485 en ~8,4 días ≈ 780/día) está
  muy por encima de ese diseño; si sigue así la cuota se acaba antes del reinicio con o sin
  los avisos. Revisar el cacheo del proxy de radar.
- `/alerts` de Xweather no cubre Colombia, `/stormcells` es solo EE. UU. y `/lightning`
  cuesta 10×: por eso no se usan.

## Fuentes evaluadas y descartadas
DIMAR/CIOH (SIPSEM detrás de Incapsula, sin API documentada), IRI ENSO (sin JSON),
WMO Alert Hub (DNS caído; el feed de IDEAM se lee directo). Open-Meteo Seasonal (SEAS5)
funciona y daba nov-2026 −90 mm de anomalía: candidato si se quiere cuantificar la
temporada además del estado ENSO.
