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
- **Pendiente real (DG-01):** confirmar si existen estaciones **hidrológicas** de IDEAM (nivel de
  río/ciénaga, no solo meteorológicas) en el mismo dataset o en otro dataset de datos.gov.co, que sí
  podrían aportar algo que hoy no se mide (nivel de agua fuera del rango de los sensores ESP32
  propios).

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

Ninguna acción de desarrollo por ahora — ambas siguen siendo trabajo de validación de datos
(Jupyter notebook), no de integración backend. Si tras DG-01 se confirma que hay estaciones
hidrológicas IDEAM útiles, o que GBIF aporta una serie limpia de abundancia/ocurrencia, ahí sí se
plantea una integración liviana siguiendo el patrón ya usado en
[app/services/ingestion/](../app/services/ingestion/) (httpx + caché + fallback).
