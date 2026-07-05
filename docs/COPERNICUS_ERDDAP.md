# Copernicus Marine — Validación de hipótesis ERDDAP

**Estado:** investigación completada · **bloqueado por resolución espacial** (ver abajo)
**Contexto:** Diego (§3 de los entregables) pidió validar si existe un endpoint ERDDAP
alternativo para los datasets de clorofila / oxígeno disuelto de CMEMS, antes de
construir el adaptador `copernicusmarine` (toolbox + conversión NetCDF→JSON).

## ⚠️ Actualización: problema de resolución (mismo hallazgo que con NMME/NOAA)

Daniel detectó en un dataset climático de NOAA (NMME CCSM4, resolución de grado completo)
que el tamaño del píxel superaba varias veces el área de la Ciénaga — invalidando el dato
para uso local. **El mismo problema aplica a los dos datasets BGC de Copernicus listados
abajo como candidatos:**

| Fuente | Resolución nativa | Tamaño del píxel | vs. Ciénaga (~450 km²) |
|---|---|---|---|
| NASA MUR SST (`jplMURSST41`, ya en uso) | 0.01° | ~1 km × 1 km ≈ 1 km² | ✅ ~450 píxeles sobre la laguna |
| NASA MODIS clorofila (`erdMH1chla8day`, ya en uso) | ~0.042° (4 km nativo) | ~4.6 km × 4.6 km ≈ 21 km² | ✅ ~21 píxeles, aceptable |
| Open-Meteo (ECMWF IFS / GFS) | ~0.08°–0.11° | ~9–12 km × 9–12 km ≈ 85–150 km² | ⚠️ solo 3–5 píxeles; aceptable para viento/lluvia (variable regional), no para variables oceánicas puntuales |
| **CMEMS BGC** (`GLOBAL_ANALYSISFORECAST_BGC_001_028` y `GLOBAL_MULTIYEAR_BGC_001_029`) | **0.25°** | **~27.8 km × 27.8 km ≈ 770 km²** | ❌ **el píxel es MÁS GRANDE que toda la Ciénaga** — mismo problema que el NMME de la captura |
| CMEMS physics global (`GLOBAL_ANALYSISFORECAST_PHY_001_024`) | 1/12° (~0.083°) | ~9.2 km × 9.2 km ≈ 85 km² | ⚠️ borderline, ~5 píxeles sobre la laguna |

**No existe un producto BGC costero de mayor resolución listo para usar** en el Caribe/CGSM —
Copernicus solo ofrece un servicio de downscaling a medida (COASTSERV) que requiere
configuración propia, no un dataset descargable directo.

**Conclusión:** los datasets BGC globales de Copernicus (oxígeno disuelto, clorofila de
respaldo) **no deben presentarse como representativos de la CGSM específicamente** — un
solo píxel mezclaría la laguna con el Caribe abierto circundante. Esto refuerza la decisión
ya tomada de no calcular/mostrar el OD teórico en el dashboard (§10 del entregable de Diego
ya lo marcaba como confianza baja; ahora hay una razón adicional, puramente geométrica, para
esa cautela). La salinidad/corrientes de CMEMS physics (1/12°) es más usable, pero sigue
siendo coherente con calcular la salinidad real desde el instrumento propio ([derived.py](../app/services/derived.py))
en vez de depender del modelo.

## Hallazgo

**La hipótesis se confirma, con un matiz importante.**

- CMEMS **sí** ofrece acceso vía OPeNDAP/ERDDAP a sus productos (anuncio oficial de
  Copernicus Marine), incluyendo biogeoquímica (o2, clorofila) y física (salinidad,
  corrientes).
- **Pero** ese ERDDAP es el **servidor propio de Copernicus** (bajo el dominio
  `marine.copernicus.eu` / `data.marine.copernicus.eu`), **con cuenta gratuita**
  requerida — no es anónimo.
- El servidor **NOAA CoastWatch que ya usamos** (`coastwatch.pfeg.noaa.gov/erddap`,
  ver [satellite.py](../app/services/ingestion/satellite.py)) **no** hospeda los
  datasets BGC de CMEMS. Sí tiene otros productos de física oceánica (SODA, GTSPP y
  salinidad superficial SMOS, rango 25–40 PSU) que podrían servir como respaldo
  parcial pero no cubren o2/clorofila del modelo CMEMS.

## Implicación para la implementación (revisada)

El camino ERDDAP hacia Copernicus técnicamente existe, pero **ya no se recomienda para
oxígeno/clorofila BGC** — el problema no es de conectividad sino de que el dato en sí no
representa la CGSM a 25 km de resolución. Implementarlo daría una falsa sensación de dato
"en vivo" cuando en realidad describe el Caribe abierto circundante, no la laguna.

- **BGC (o2, clorofila de respaldo): diferir indefinidamente**, salvo que aparezca un
  producto regional/costero de mayor resolución (revisar catálogo Copernicus
  periódicamente, o evaluar COASTSERV si el equipo tiene tiempo para downscaling a medida).
- **Physics (salinidad modelo, corrientes) a 1/12° (~9 km):** sigue siendo un candidato
  razonable si en el futuro se necesitan corrientes marinas (variable que hoy no se mide
  con el instrumento propio) — reusar el patrón `erddapy` de
  [satellite.py](../app/services/ingestion/satellite.py) apuntando al ERDDAP de Copernicus
  + credenciales, evitando el toolbox `copernicusmarine` y la conversión NetCDF→JSON.

## Pendientes si se retoma la parte de physics (corrientes)

1. Crear cuenta gratuita en https://data.marine.copernicus.eu/register.
2. Confirmar la **URL exacta del endpoint ERDDAP** de Copernicus y el mecanismo de
   auth (token vs basic auth) — la página de anuncio dio 403 al fetch automatizado;
   verificar manualmente logueado.
3. Localizar el `dataset_id` de `GLOBAL_ANALYSISFORECAST_PHY_001_024` (1/12°) en el
   catálogo ERDDAP para el área CGSM.
4. Guardar credenciales en `.env` (nunca en código) y versionar el `dataset_id` en
   `settings` (mismo patrón que `erddap_sst_dataset` en [config.py](../app/core/config.py)).

## Fuentes

- https://marine.copernicus.eu/news/access-data-opendap-erddap-api
- https://data.marine.copernicus.eu/product/GLOBAL_MULTIYEAR_BGC_001_029/description (0.25°)
- https://data.marine.copernicus.eu/product/GLOBAL_ANALYSISFORECAST_BGC_001_028/description (0.25°)
- https://data.marine.copernicus.eu/product/GLOBAL_ANALYSISFORECAST_PHY_001_024/description (1/12°)
- https://marine.copernicus.eu/services/use-cases/coastserv-downscaled-cmems-products-high-resolution-coastal-models
- https://coastwatch.pfeg.noaa.gov/erddap/
