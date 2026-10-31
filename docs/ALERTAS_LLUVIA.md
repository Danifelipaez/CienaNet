# Alertas de lluvia — tres antelaciones, backtest real 27-sep..26-oct-2026

**Estado:** implementado. Nowcast con backtest propio (GOES-19, 34 episodios);
outlook y sinóptico son contexto de dashboard, sin push.
**Origen:** lluvia intensa del 24-oct-2026 en el Caribe colombiano (vaguada y bajas
en el Caribe occidental/central bajo un frente estacionario al norte; segunda
temporada de lluvias oct-nov). El satélite vio los primeros píxeles en la caja a las
14:20Z y el anillo 60 min antes.

## Tres niveles

| Antelación | Fuente | Función | Salida | Push |
|---|---|---|---|---|
| 10-60 min | GOES-19 ABI-L2-RRQPEF (S3 `noaa-goes19`, scan cada 10 min, ~10 min de latencia) | `ingestion/rain_nowcast.py` + `signals.lluvia_nowcast` | `senales.lluvia.nowcast` | **Sí**, solo "inminente" |
| 6 / 24 h | GEFS 0.25 (31 miembros) vía Open-Meteo Ensemble | `weather.get_rain_ensemble` + `signals.lluvia_outlook` | `senales.lluvia.outlook` | No |
| Días (estacional) | Texto del Tropical Weather Discussion del NHC | `alerts_ext.get_sistemas_sinopticos` | `senales.lluvia.sinoptico` | No |

El nowcast corre dentro de `app/main.py::_nowcast_refresh` (cada 10 min, junto al
nowcast de rayos), y el último resultado queda en memoria
(`rain_nowcast.get_ultimo_lluvia`) para `GET /data/latest`.

### Nowcast (RRQPE)
- **Caja** de la CGSM: lat 10.54-11.01, lon -74.69 a -74.32 (520 píxeles de 2 km).
  **Anillo**: 20-60 km del punto (10.85, -74.50) sin la caja (2204 píxeles). El centro
  es el del backtest, no `cienaga_lat/lon` (difieren ~4 km), para que POD/FAR apliquen tal cual.
- `lloviendo`: >=5 % de la caja con >=1 mm/h. Ya se mojó: sin push.
- `inminente`: caja seca y >=2 % del anillo con >=5 mm/h. ETA `[30, 60]` min.
- `sin_lluvia`; `sin_dato` si no hay scan, tiene >25 min o >10 % de NaN en caja+anillo.
- `tormenta_electrica`: >=3 destellos GLM en 30 min a <=100 km (conteo acumulado en
  `_nowcast_refresh`; cada ciclo de 10 min aporta ~1 min de muestra, similar al
  muestreo del backtest). Es severidad: no cambia el estado.
- Push (`alert_service.maybe_send_rain_alert`, template `alerta_lluvia` **por crear y
  aprobar en Meta**, `alert_type="lluvia"`): solo "inminente", histéresis de 60 min
  contra el último `AlertLog` "lluvia".

### Outlook (GEFS)
`prob_6h` = fracción de miembros con >=5 mm en las próximas 6 h. `prob_24h` = máximo de
esa probabilidad en los bloques +6..+12, +12..+18 y +18..+24 h. `nivel`: <0.3 bajo,
<0.5 medio, >=0.5 alto (sobre el mayor de los dos). Open-Meteo etiqueta cada hora con su
fin, así que el bloque toma las etiquetas en (t0, t0+6h].

### Sinóptico (TWD)
Texto crudo `tgftp.nws.noaa.gov/.../axnt20.knhc.twd.at.txt` (fallback `MIATWDAT.shtml`),
cache 1 h. Se leen las secciones CARIBBEAN SEA, TROPICAL WAVES y MONSOON TROUGH, por
oración. Detecta `frente_frio`, `onda_tropical` (eje 70-80W o Colombia), `vaguada` y
`baja_presion`. `afecta_cgsm` exige que la misma oración ubique el sistema en Colombia /
SW o centro-sur del Caribe / Magdalena / Santa Marta, o un eje entre 73.5W y 75.5W; en
vaguada y baja además debe haber convección en esa oración o la siguiente (la vaguada
monzónica de Colombia/Panamá sale casi a diario).

## Métricas reales del backtest (RRQPE, 29.3 días, 4220 scans, 34 episodios)

| Regla | POD | FAR (por episodio de alerta) | CSI | Antelación |
|---|---|---|---|---|
| Anillo 20-60 km, >=5 mm/h en >=2 % (**usada**) | 0.71 (24/34) | 0.43 (18 falsas de 42) | 0.46 | mediana 30 min (10-80) |
| Igual, >=3 % (conservadora) | 0.50 | 0.51 | 0.33 | mediana 30 |
| Anillo 30-80 km, >=1 mm/h en >=5 % | 0.59 | 0.66 | 0.27 | mediana 50 |

"FAR práctico" (sin lluvia >=5 % en la caja en los 90 min siguientes): 0.24; ~1.4
alertas/día y ~0.3 falsas/día. Partición temporal: CSI 0.44 (entrenamiento) / 0.48 (prueba).
GLM aislado o combinado con el anillo no mejoró (CSI 0.22-0.26): solo sirve de severidad.
GEFS (12-26 oct, 57 bloques): a ~12 h con P(>=5 mm)>=0.5, POD 0.70 / FAR 0.42; a ~24 h,
POD 0.60 / FAR 0.50 — muestra pequeña. GFS determinista >=1 mm/6 h no tiene destreza (CSI ≈ azar).

**Test de replay** (`tests/test_rain_nowcast.py::test_replay_*`): reproduce estas cifras con
`tests/fixtures/rrqpe_cgsm_2026-09-27_10-26.csv` (features por scan calculadas con la
función de producción; generador `scripts/gen_rrqpe_fixture.py`). Exige POD>=0.65 y
FAR(episodio)<=0.50.

## Límites
- **Sin pluviómetros**: la verdad es RRQPE, un proxy IR que sobreestima la intensidad y satura
  en 100 mm/h. Se usa como categoría ("fuerte >=5 mm/h"), nunca como lámina. La caja (~2100 km²)
  no es toda la ciénaga ni el mar donde faenan.
- **Umbrales sobreajustados** a un solo mes de temporada húmeda (barrido de ~2000 combinaciones
  sobre 34 episodios). Validar en producción antes de confiar; repetir en dic-feb.
- 10 de 34 episodios no tuvieron aviso (convección que nace dentro de la caja o crece en <10 min):
  límite físico de cualquier nowcast, igual que en `docs/ALERTAS_VENDAVAL.md`.
- El filtro del corredor de `lightning.py` (lat 9.0-11.3, lon -75.3 a -73.3) recorta algo del
  círculo de 100 km al norte y oeste: el conteo de rayos puede ser algo menor al real.
- El outlook usa el punto de Open-Meteo (CGSM), no el máximo de celdas de la caja que se
  backtesteó; Open-Meteo estuvo bloqueado y no se evaluó. Por eso es solo dashboard.
- El TWD es texto libre: si NHC cambia la redacción, `parse_twd` da lista vacía en silencio
  (queda un warning en el log si no encuentra las secciones).
- `rain_nowcast` no cae a caché vencida: un scan viejo se muestra como `sin_dato`.

## JSON para el frontend (`GET /data/latest` -> `senales.lluvia`)
Cada rama puede ser `null` (nowcast: antes del primer ciclo tras un reinicio; sinóptico: fuente caída).
`outlook` y `nowcast` traen `estimacion: true`; `outlook.nivel` es `null` sin dato.

```json
{
  "outlook": {"nivel": "alto", "prob_6h": 0.55, "prob_24h": 0.81, "umbral_mm_6h": 5.0, "n_miembros": 31, "estimacion": true},
  "nowcast": {"estado": "inminente", "eta_rango_min": [30, 60], "scan": "2026-10-24T13:20:00+00:00",
              "frac_caja_1mm": 0.0, "frac_anillo_5mm": 0.034, "tormenta_electrica": true, "n_rayos_30min": 7,
              "estimacion": true},
  "sinoptico": {"sistemas": ["vaguada", "baja_presion"], "afecta_cgsm": true,
                "extracto": "Low pressure of 1008 mb is centered over the SW Caribbean near 11N80W.",
                "emitido": "2026-10-24T12:05:00+00:00"}
}
```
`nowcast.estado`: `lloviendo | inminente | sin_lluvia | sin_dato`; `eta_rango_min` solo en
`inminente`; `scan` y `frac_*` ausentes en `sin_dato`. `sinoptico.sistemas` ⊂
`frente_frio | onda_tropical | vaguada | baja_presion`; `extracto` y `emitido` pueden ser `null`.
