# IDEAM y GBIF — Estado de validación

**Estado:** verificación técnica de alcance completada · validación de datos pendiente (Diego)
**Contexto:** ambas fuentes están documentadas en [KNOWLEDGE_BASE.md §4.4-4.5](./KNOWLEDGE_BASE.md)
y asignadas como tareas **DG-01** y **DG-03** en [TAREAS_EQUIPO.md](./TAREAS_EQUIPO.md), pero no
aparecen en el entregable más reciente de Diego (`ENTREGABLES TECNICOS POR FUENTE CIENRAYAS.md`,
2026-07-02). No existe `notebooks/` ni `docs/ML_FEATURES.md` en el repo, así que DG-01/DG-03/DG-04
parecen no ejecutadas aún.

**Pregunta para Diego:** ¿se descartaron deliberadamente estas dos fuentes, o quedaron fuera de
esta ronda de entregables por falta de tiempo? Si fue descarte, documentarlo evita que alguien las
reintente más adelante sin contexto.

## IDEAM Datos Abiertos (Socrata, dataset `sbwg-7ju4`)

- **Reachable:** sí, HTTP 200, sin autenticación (`https://www.datos.gov.co/resource/sbwg-7ju4.json`).
- **Cobertura real cerca de la CGSM:** una sola estación dentro del bounding box del proyecto
  (LAT 10.5–11.2, LON -74.85 a -73.9): **Aeropuerto Simón Bolívar**, Santa Marta
  (`codigoestacion=0015015050`, lat 11.1147 / lon -74.2310). Sin estaciones en los municipios
  ribereños (Ciénaga, Sitionuevo, Pueblo Viejo, Remolino, El Piñón).
- **Variable reportada:** únicamente temperatura del aire a 2m, con frecuencia ~2 min (dato de hoy
  disponible en tiempo casi real).
- **Conclusión técnica:** esta estación es **redundante con Open-Meteo**, que ya provee
  temperatura del aire para la misma zona. No aporta viento, precipitación ni humedad — las
  variables que sí serían un complemento útil.
- **Actualización (2026-07-06):** sí existen. El catálogo completo de estaciones IDEAM (`CNE_IDEAM.pdf`,
  descarga manual desde el portal de estaciones — no es el mismo dataset Socrata `sbwg-7ju4` usado
  arriba) sí tiene cobertura real en la cuenca de la CGSM. Filtrando por
  `SUBZONA_HIDROGRAFICA = "Cga Grande de Santa Marta"` aparecen **31 estaciones activas**:
  - **8 limnimétricas/limnigráficas** sobre los ríos tributarios que desembocan en la Ciénaga —
    esto es justo el dato de nivel de agua que `sbwg-7ju4` no tenía:
    `29067010` El Trébol (río Tucurinca), `29067050` Canal Florida (río Sevilla), `29067040`
    Santa Rosalía (río Orihueca), `29067070` Río Frío (río Frío), `29067060` Puerto Rico Hacienda
    y `29067120` Fundación (ambas río Fundación), `29067130` Puente Ferrocarril y `29067150`
    Ganadería Caribe (ambas río Aracataca).
  - **23 pluviométricas/climáticas** en los municipios ribereños que sí estaban ausentes en
    `sbwg-7ju4` (Ciénaga, Zona Bananera, Aracataca, Fundación, El Retén, Puebloviejo, Sitionuevo,
    Remolino, Salamina, El Piñón, Pivijay).
  - Ninguna estación mide directamente el espejo de agua de la Ciénaga (no hay limnígrafo *in situ*
    en la laguna) — las 8 de río son la mejor proxy indirecta de aporte de agua dulce.
  - Se descartaron por pertenecer a otra cuenca: las estaciones de la Sierra Nevada norte
    (Guachaca, Buritaca, Don Diego, Palomino — drenan directo al Caribe) y otras ciénagas
    homónimas (Ciénaga Chilloa, Ciénaga Zapatoza, ambas en el Bajo Magdalena/Cesar).
- **Actualización (2026-07-06), datos crudos analizados:** se recibieron series de tiempo reales
  para 27 de las 31 estaciones (faltan `29065000`, `29065130`, `29067060`, `29067150` en este
  extracto) en la carpeta `A:\Unversidad\ALUNA_IA\20269910112644` — 1618 archivos `.data`, formato
  `ETIQUETA@CODIGO.data` con contenido `Fecha|Valor` separado por pipe. El nombre de la carpeta
  (`20269910112644`) tiene forma de **radicado/solicitud puntual al IDEAM**, no de endpoint de API
  — esto importa para la decisión de "vivo" (ver abajo). Análisis hecho con un script temporal
  (descartado tras el análisis, no vive en el repo) que parseó cada archivo y midió: rango de
  fechas, antigüedad del último dato (`stale`), paso temporal típico y sanity check de valores
  (min/max/media, negativos, ceros).

  **Decisión — datos en vivo:**
  - ✅ **Lluvia (`PTPM_CON`, precipitación diaria)** en 21 de 23 estaciones: actualizadas hasta hace
    5–186 días (varias con `stale=5d`, es decir hasta el 2026-06-30). Cubren 10 municipios
    ribereños con 40–70 años de histórico. Único vacío real de `sbwg-7ju4` que esto sí llena.
    Muertas: `29060160` El Enano (sin dato desde 2022-08) y `29060340` El Palmor (desde 2022-12).
  - ✅ **Nivel/caudal de río (`NIVEL_H`, `Q_MEDIA_D`, `NV_MEDIA_D`)** en 4 de 6 estaciones con datos:
    El Trébol/Tucurinca, Santa Rosalía/Orihueca, Río Frío y Fundación/río Fundación — todas
    `stale≤6d` (hasta 2026-06-30/07-01). Esto es exactamente lo que falta hoy en el proyecto: el
    ESP32 mide condiciones *dentro* de la Ciénaga, esto mide el **aporte de agua dulce que entra**.
    Canal Florida y Puente Ferrocarril/Aracataca están más atrasados (`stale`=51–212 días) — usables
    pero con más rezago.
  - ❌ **Sedimentos (`CM_*`, `TR_QS_*`, transporte/concentración)**: NO usar en vivo. Es muestreo de
    campo manual, no telemetría — todas las series están muertas desde hace 1 a 12 años según
    estación (la mayoría dejó de reportar entre 2014 y 2019; una detiene en 2023).
  - ❌ **Suite meteorológica completa de Padelma (`29065020`)** — temperatura, humedad relativa,
    brillo solar, temperatura de suelo, punto de rocío: todas muertas entre 2021 y 2025. Solo la
    lluvia de esa estación sigue viva.
- **Actualización (2026-07-06), canal de API en vivo confirmado:** DHIME y SIRH son portales web de
  consulta manual (sin API documentada públicamente), pero el **mismo backend Socrata de
  `datos.gov.co`** que ya usábamos para `sbwg-7ju4` publica datasets separados por variable, con
  datos crudos (sin validar) de las estaciones **automáticas con telemetría**:
  - `s54a-sgyg` "Precipitación" — cada 10 min. `https://www.datos.gov.co/resource/s54a-sgyg.json?codigoestacion=<código>`
  - `bdmn-sqnh` "Nivel Instantáneo del Rio" — horario. Mismo patrón de URL.
  - `vfth-yucv` / `pt9a-aamx` — Nivel Máximo/Mínimo del Río (no probados aún, probablemente resúmenes diarios).
  - **Ojo con el formato del código:** estos datasets usan `codigoestacion` de **10 dígitos con
    ceros a la izquierda** (`0029067060`, no `29067060`) — distinto del padding que usa `sbwg-7ju4`.
  - **Cobertura confirmada en la CGSM — y es complementaria, no redundante, con el extracto `.data`:**
    las 2 estaciones de río que **faltaban** en el extracto (`29067060` Puerto Rico Hacienda,
    `29067150` Ganadería Caribe) sí están en `bdmn-sqnh`, con dato hasta **2026-07-04** (hoy es
    2026-07-06). Y las 2 estaciones de lluvia que **faltaban** (`29065000` Media Luna,
    `29065130` La Gran Vía) sí están en `s54a-sgyg`, también hasta 2026-07-04. Verificado con
    `curl` directo, sin autenticación, HTTP 200.
  - **Por qué las otras 6 estaciones de río no están acá:** según las notas del catálogo
    (`CNE_IDEAM.pdf`), El Trébol/Santa Rosalía/Río Frío perdieron su instrumento automático en 2024
    ("instrumentos LG fueron retirados... no prestaban un servicio óptimo") y quedaron como
    "Limnimétrica Convencional" (lectura manual) — por eso solo aparecen en el extracto histórico
    `.data`, no en el feed en vivo. Los dos canales (Socrata en vivo vs. extracto `.data`) cubren
    **estaciones distintas dentro del mismo conjunto de 8** — hay que usar ambos, no elegir uno.
  - **Caudal (m³/s) NO tiene equivalente en vivo:** no existe dataset Socrata de caudal en tiempo
    real (se buscó explícitamente) — el caudal requiere una curva de calibración nivel→caudal que
    IDEAM solo publica como producto validado periódico (el `Q_MEDIA_D` del extracto `.data`). Para
    "vivo" solo se dispone de **nivel**, no de caudal.
  - **Conclusión:** ✅ desbloqueado. Para datos en vivo, integrar `s54a-sgyg` (lluvia, 2 estaciones
    AUT) y `bdmn-sqnh` (nivel de río, 2 estaciones AUT) siguiendo el patrón de
    `app/services/ingestion/` (httpx + caché + fallback), como complemento de las variables que ya
    trae el extracto `.data` para el resto de estaciones (con más rezago, vía actualización manual
    periódica del propio Diego, no vía servicio automatizado).
  - **Actualización (2026-07-07), respaldo en DB:** el cron diario (`GET /data/latest`, ver
    `vercel.json` y `app/main.py::_hourly_refresh`) ahora también persiste estas 4 estaciones en la
    tabla `ideam_hidro_readings` (`app/models/environmental.py`), con `UNIQUE(variable, estacion, date)`
    para deduplicar — si la fila del día ya existe se salta, no se reinserta ni se sobreescribe.
    Esto es un respaldo propio ante caídas/cambios de la API pública, **no** la fuente de
    `/data/history` (que sigue leyendo en vivo de Socrata, con su propio caché de 30 min).

  **Decisión — entrenamiento ML:** ✅ usar sin condiciones. 40–70 años de caudal/nivel/lluvia diario
  por estación es exactamente el tipo de feature histórico que `DG-03`/`DG-04` (correlación
  aporte-de-río × salinidad/productividad, y el propio `sedimentation_service.py`/
  `sedimentation_zones` del backend) necesitan. Advertencias de limpieza antes de usar:
  - `CM_D@29067120` (Fundación, río) tiene un outlier extremo: máximo ~239 millones vs. media
    ~58 mil — filtrar antes de usar como feature.
  - Ojo con el nombre duplicado **"Fundación"**: `29060040` es la estación de **lluvia** en el
    municipio de Fundación, `29067120` es la estación de **río** sobre el Río Fundación en
    Aracataca — son estaciones distintas, no confundir códigos en el pipeline de ingesta.

## GBIF Occurrence API

- **Reachable:** sí, HTTP 200, sin autenticación, sin límite documentado.
- **Datos reales en la zona:** hay registros georreferenciados dentro del bounding box con
  `institutionCode` = INVEMAR — es decir, el mismo origen de datos que Diego ya procesa
  directamente para el histórico de INVEMAR/SEPEC.
- **Ojo con el conteo del bounding box:** una consulta de una sola especie (`Mugil incilis`, lisa)
  devolvió ~195,000 resultados dentro de un área pequeña — cifra que huele a filtro de
  coordenadas no aplicándose tan estricto como parece (o a un artefacto del conteo agregado de
  GBIF). **No usar el conteo tal cual sin antes inspeccionar una muestra de resultados y confirmar
  que las coordenadas realmente caen dentro de la CGSM.**
- **Pendiente real (DG-03):** el notebook exploratorio ya estaba previsto — este es el punto donde
  se debe limpiar la query antes de usarla como feature de ML.

## Recomendación

- **ML/histórico (IDEAM río + lluvia):** listo para usar ya — no requiere validación adicional,
  son archivos ya en disco. Candidato directo para el notebook de `DG-03`/`DG-04` (features de
  aporte hídrico, estacionalidad de lluvia, baseline histórico de sedimentación).
- **Vivo (IDEAM río + lluvia): ✅ implementado (2026-07-06).** `app/services/ingestion/ideam_hidro.py`
  consume `s54a-sgyg` (precipitación) y `bdmn-sqnh` (nivel de río) con agregación diaria server-side
  (SoQL `date_trunc_ymd` + `sum`/`avg`), caché de 30 min y fallback a la última respuesta buena —
  mismo patrón que `weather.py`/`satellite.py`. Expuesto en `GET /data/history` como
  `ideam_precipitacion` e `ideam_nivel_rio`, con una gráfica por API en `/dashboard/graficas`
  (Precipitación en la cuenca, Nivel de ríos tributarios — una línea por estación). Alcance real:
  **2 estaciones de río** (Puerto Rico Hacienda, Ganadería Caribe — solo nivel, no caudal) y
  **2 de lluvia** (Media Luna, La Gran Vía). Es un complemento — no un reemplazo — de las ~25
  estaciones restantes que solo están en el extracto `.data` con más rezago; esas NO están
  integradas en vivo (siguen siendo solo insumo de `ML/histórico` arriba). Sedimentos y la suite
  meteorológica de Padelma quedan fuera por estar muertas en ambos canales.
- **GBIF:** sigue siendo trabajo de validación de datos (Jupyter notebook), no de integración
  backend — pendiente `DG-03` (limpiar la query de conteo antes de usarla).
