# Resolución espacial de las fuentes satelitales — auditoría y upgrade de clorofila

**Estado:** implementado
**Origen:** Daniel detectó en un dataset climático de NOAA (NMME CCSM4, grado completo) que
el píxel superaba varias veces el tamaño de la Ciénaga Grande, invalidando el dato para uso
local. Esto llevó a auditar la resolución real de cada fuente del proyecto.

## Resolución medida de cada fuente

| Fuente | Resolución nativa | Píxel | Cobertura de la Ciénaga (~450 km²) |
|---|---|---|---|
| Sentinel-3 OLCI 300m (implementado hoy) | 0.0025° ≈ 278 m | 0.077 km² | ~5.800 píxeles |
| NASA MUR SST (sin cambios) | 0.01° ≈ 1.1 km | 1.2 km² | ~370 píxeles |
| NASA MODIS clorofila (reemplazado) | 0.042° ≈ 4.6 km | 21 km² | ~21 píxeles |
| CMEMS physics (candidato, no implementado) | 1/12° ≈ 9.2 km | 85 km² | ~5 píxeles |
| Open-Meteo (viento/lluvia) | ~0.08-0.11° ≈ 9-12 km | 85-150 km² | 3-5 píxeles |
| CMEMS BGC (descartado, ver [COPERNICUS_ERDDAP.md](./COPERNICUS_ERDDAP.md)) | 0.25° ≈ 28 km | 770 km² | píxel más grande que toda la laguna |

## Cambio implementado: clorofila NASA MODIS → Copernicus OLCI

El producto que usábamos (`erdMH1chla8day`, NASA MODIS-Aqua, 4km/8días) mezclaba en cada
píxel la laguna con el Caribe abierto circundante, diluyendo el valor real. Verificado con
datos en vivo: el producto de 278m devuelve **8-80 mg/m³** en la CGSM (laguna hipereutrófica),
muy por encima del baseline histórico usado hasta ahora (4.5 mg/m³) — consistente con que el
producto de 4km subestimaba la clorofila real de la ciénaga.

**Fuente nueva:** Sentinel-3 OLCI vía NOAA CoastWatch (no requiere cuenta de Copernicus, es
el mismo dato republicado por NOAA en su propio ERDDAP público).
- Servidor: `https://coastwatch.noaa.gov/erddap` (distinto del que ya usábamos para SST,
  `coastwatch.pfeg.noaa.gov` — mismo protocolo ERDDAP, sin credenciales).
- Dataset: `noaacwS3AOLCIchlaSectorFGDaily` — sector geográfico "FG" de los 216 en que NOAA
  divide la cobertura global; se calculó geométricamente que "FG" cubre la CGSM
  (lon banda -80/-60, lat banda -0.4/15.0) y se confirmó consultando datos reales.
- Retención: solo ~90 días (NRT). **No reemplaza el archivo histórico de NASA** (2003-presente)
  que Diego usa para el baseline de ML — ese sigue siendo `erdMH1chla8day` para históricos.
- Implementado en [satellite.py](../app/services/ingestion/satellite.py): ventana de 7 días
  (tolera nubes — en pruebas, ~7 de 17 días tenían píxel válido) y `stride=10` (~2.8km de
  muestreo efectivo) para promediar sin descargar ~2M filas/semana a resolución nativa.

## Gotcha: NOAA CoastWatch bloquea el User-Agent por defecto

El servidor `coastwatch.noaa.gov` devuelve **403 Forbidden** a clientes con el User-Agent
genérico de `requests`/`urllib`/`httpx` (verificado: `curl` y cualquier UA *personalizado*
pasan sin problema — no exige simular un navegador, solo rechaza las firmas por defecto de
librerías). Además, `erddapy` no reenvía `requests_kwargs` (headers) dentro de
`griddap_initialize()` — es una limitación de la librería, no configurable desde afuera.

**Por eso la clorofila se pide con `httpx` directo** (no `erddapy`), con
`headers={"User-Agent": "CienaNetBot/1.0"}`. La SST (`coastwatch.pfeg.noaa.gov`, servidor
distinto) no tiene este bloqueo y sigue usando `erddapy` sin cambios.

## Deuda conocida

La tabla `satellite_data` guarda SST y clorofila en la misma fila con `source="nasa_mur"`.
Desde este cambio, la clorofila en realidad viene de Copernicus/NOAA CoastWatch, no de NASA
MUR — la etiqueta quedó desactualizada. No se renombró porque `source="nasa_mur"` es también
la clave que usa la estrategia DB-first en
[dashboard_service.py](../app/services/dashboard_service.py) para decidir si reutiliza el
dato cacheado; cambiarla requiere tocar esa lógica y no aporta valor funcional. Si en el
futuro se separan las fuentes en filas distintas, ajustar ambos lugares a la vez.
