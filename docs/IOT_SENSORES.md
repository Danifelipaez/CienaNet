# Red de Sensores IoT — Arduino + ESP32

## Descripción General

Red de nodos sensores de bajo costo desplegados en la Ciénaga Grande de Santa Marta para medir parámetros de calidad del agua en tiempo real.

## Hardware por Nodo

| Componente | Modelo recomendado | Costo aprox. |
|------------|-------------------|--------------|
| Microcontrolador | ESP32 (WROOM-32) | ~$5 USD |
| Sensor pH | Electrodo SEN0169 + módulo amplificador | ~$20 USD |
| Sensor conductividad | DFRobot EC Sensor V2.0 | ~$25 USD |
| Sensor temperatura | DS18B20 waterproof | ~$5 USD |
| Módulo celular (zonas sin WiFi) | SIM7600 4G LTE | ~$30 USD |
| Enclosure | Caja IP67 | ~$10 USD |
| Alimentación | Panel solar 5W + batería LiPo | ~$15 USD |
| **Total por nodo** | | **~$110 USD** |

## Diagrama de Conexión ESP32

```
ESP32
├── GPIO 34 (ADC) ──── Sensor pH (señal analógica 0-3.3V)
├── GPIO 35 (ADC) ──── Sensor EC (señal analógica)
├── GPIO 4 (1-Wire) ── DS18B20 temperatura + resistencia 4.7kΩ pull-up
├── TX/RX (UART2) ──── Módulo SIM7600 (si se usa celular)
└── 3.3V / GND ──────── Alimentación sensores
```

## Firmware — Flujo Principal

```cpp
// Pseudocódigo del ciclo de medición
void loop() {
    if (millis() - lastReading > READING_INTERVAL_MS) {
        SensorReading reading = {
            .ph = readPH(),
            .conductivity_ms = readEC(),
            .temperature_c = readTemperature(),
            .timestamp = getEpochTime(),
            .sensor_id = SENSOR_ID
        };
        
        if (sendToAPI(reading)) {
            lastReading = millis();
            blink(LED_GREEN, 1);
        } else {
            // Guardar en memoria local hasta tener conexión
            storeInBuffer(reading);
            blink(LED_RED, 3);
        }
    }
    
    // Enviar buffer acumulado si hay conexión
    if (WiFi.isConnected() && bufferSize() > 0) {
        flushBuffer();
    }
    
    deepSleep(SLEEP_SECONDS);  // ahorrar batería entre lecturas
}
```

## Protocolo de Comunicación con API

### Endpoint de Ingesta
```
POST /api/v1/sensors/ingest
X-Api-Key: {SENSOR_API_KEY}
Content-Type: application/json
```

> **Nota (actualizada a la implementación real, `app/schemas/sensor.py` + `app/api/v1/routers/sensors.py`):**
> el endpoint acepta **una sola lectura por request** (no un array `readings[]`). El firmware que
> acumula buffer local debe hacer un POST por lectura al reconectar, no un único POST con varias.
> La autenticación es por header `X-Api-Key` (no `Authorization: Bearer`) — ver `get_current_sensor()`
> en `app/api/v1/dependencies.py`.

### Payload
```json
{
  "sensor_id": "CGSM-001",
  "timestamp": "2025-06-20T14:30:00Z",
  "ph": 7.4,
  "conductivity_mscm": 12.5,
  "temperature_c": 28.3,
  "water_level_cm": 45.2
}
```

Campos opcionales (`ph`, `conductivity_mscm`, `temperature_c`, `water_level_cm`) — enviar `null` u omitir los que el sensor no mida. `battery_mv`/`signal_rssi` aún no están en el schema; si se necesitan, agregar campos a `SensorReadingIn`.

Validación de rango (fuera de rango → `422`, no se persiste): `ph` 0–14,
`temperature_c` -5–45°C, `conductivity_mscm` 0–80 mS/cm, `water_level_cm`
0–500 cm. Es un cambio de contrato respecto a versiones previas del firmware
que mandaban valores fuera de estos rangos sin problema — un firmware con
buffer local que reintenta sobre un valor pegado ahora fallará indefinidamente
en vez de contaminar el snapshot; avisar al equipo de firmware si esto pasa.

### Respuesta esperada
```json
{
  "status": "ok"
}
```

---

## Calibración

### pH
- Calibrar con soluciones buffer pH 4.0 y pH 7.0
- Recalibrar cada 2-4 semanas (los electrodos de pH se degradan)
- Guardar coeficientes de calibración en EEPROM del ESP32

### Conductividad (EC)
- Calibrar con solución estándar de 1413 µS/cm
- La EC varía con temperatura — aplicar compensación de temperatura:
  ```
  EC_25 = EC_medida / (1 + 0.02 * (temperatura - 25))
  ```

### Temperatura
- DS18B20 tiene precisión de ±0.5°C, no requiere calibración

---

## Rangos de Alerta para la Ciénaga

Basados en estudios de la Ciénaga Grande de Santa Marta (INVEMAR):

| Parámetro | Normal | Alerta leve | Alerta crítica |
|-----------|--------|-------------|----------------|
| pH | 6.5 – 8.5 | < 6.0 o > 9.0 | < 5.5 o > 9.5 |
| Conductividad (mS/cm) | 0.5 – 30 | > 35 | > 45 |
| Temperatura (°C) | 25 – 32 | > 34 | > 36 |

**Nota:** Estos umbrales deben validarse con pescadores locales y con Diego (análisis territorial). Los valores del INVEMAR son referencia, no son absolutos.

**Nota de implementación (actualizada):** estos umbrales finos (leve/crítica)
siguen sin enforcerse en `POST /sensors/ingest` — la evaluación de alerta
ocurre después, sobre el snapshot agregado, en `app/services/semaphore.py` y
`app/services/alert_service.py`. Lo que **sí** se valida en el ingest
(`SensorReadingIn`, `app/schemas/sensor.py`) es un rango de **trust
boundary** mucho más ancho que estos umbrales de alerta — atrapa la sonda
desconectada o pegada en un riel, no control de calidad fino:
`conductivity_mscm` 0–80 mS/cm y `water_level_cm` 0–500 cm, rechazando con
`422` fuera de rango (mismo patrón que `ph` 0–14 y `temperature_c` -5–45°C,
que ya existían). No confundir este rango de ingesta con la tabla de arriba.

**Frescura de lectura:** `get_latest_readings()` (`app/services/sensor_service.py`)
filtra por `Sensor.active` y por antigüedad máxima (6h por defecto) — una
lectura vieja de un sensor desconectado ya no sigue alimentando el snapshot
agregado indefinidamente.

---

## Identificación de Sensores

Formato de ID: `CGSM-{zona}-{número}`
- `CGSM-001` — Zona norte
- `CGSM-002` — Zona sur
- `CGSM-003` — Boca de la Barra
- etc.

Las coordenadas y zona de cada sensor se registran en la tabla `sensors` de la DB al activarlo por primera vez.

---

## Metodologías de Conectividad Evaluadas

Se evaluaron tres formas de darle acceso a internet a la boya. El firmware
real (`firmware/alt_tend_sensor/alt_tend_sensor.ino`) usa WiFi STA estándar
(`conectarWiFi()`), y esa elección es **agnóstica** al origen de la red:

| Método | Estado | Modelo de confianza |
|---|---|---|
| WiFi STA (router o hotspot celular/PC — mismo modo) | **Implementado, recomendado** | El ESP32 habla TLS end-to-end directo contra el backend (`WiFiClientSecure` + certificado raíz de Let's Encrypt embebido, cuando `API_USE_TLS=1`); el punto de acceso (router o hotspot) es solo tránsito, nunca ve el payload en claro |
| Módulo celular SIM7600 | Futuro (Fase 2, sin hardware en mano todavía) | Mismo modelo que WiFi — TLS end-to-end, solo cambia la capa de acceso (UART2 en vez de radio WiFi) |
| Bridge por PC/USB (relay serial) | **Descartado** | El PC tendría que terminar/reoriginar la conexión TLS, viendo la API key y el payload en texto plano en esa etapa — algo que hoy no ocurre. Además exige un PC permanentemente encendido junto a la boya, lo que rompe el diseño de boya autónoma a batería con deep sleep |

Router doméstico/institucional y hotspot compartido desde celular/PC son
**el mismo código, sin rama distinta** — solo cambia `WIFI_SSID`/
`WIFI_PASSWORD` en `config.h` (ver comentario ahí). El bridge por PC/USB se
descartó explícitamente porque la prioridad es la máxima independencia de la
boya; queda documentado aquí para que no se vuelva a proponer sin este
contexto.

---

## Seguridad del Firmware

- **API key única por dispositivo** — vive en `config.h` (gitignored, nunca
  en el código fuente versionado), viaja en el header `X-Api-Key` de cada
  request, y el backend la verifica con PBKDF2-HMAC-SHA256 sobre un hash
  guardado en DB (`app/core/security.py::verify_sensor_api_key`) — nunca en
  texto plano. Si un sensor es comprometido, revocar solo esa key.
- **HTTPS obligatorio en producción** — el firmware soporta TLS condicional
  vía `WiFiClientSecure` (`#if API_USE_TLS`) y valida el certificado del
  servidor (nunca `setInsecure()`) contra `TRUSTED_ROOTS_PEM`, que embebe DOS
  roots concatenados en un solo buffer (`mbedtls_x509_crt_parse()` acepta
  varios bloques PEM en un mismo string): ISRG Root X1 (Let's Encrypt, para
  el servidor universitario vía Caddy) y GTS Root R1 (Google Trust Services,
  para `ciena-net.vercel.app` mientras siga vivo — ver "Deuda: doble
  despliegue" en `docs/DEPLOYMENT.md`). El root de Vercel se extrajo en vivo
  de una conexión TLS real, no de memoria — si Vercel rota de CA antes de que
  venza ese cross-cert (2028-01-28), hay que repetir la extracción y
  actualizar el `.ino`. En banco de pruebas actual está desactivado
  (`API_USE_TLS 0`, IP LAN local) — activar antes de desplegar en campo, ver
  checklist de `docs/DEPLOYMENT.md`.
- **Frescura del `timestamp`** — el backend rechaza con `422` lecturas cuyo
  `timestamp` sea más viejo que `MAX_READING_AGE_HOURS` (6h) o esté más de
  `MAX_FUTURE_SKEW_MINUTES` (5 min) en el futuro (`app/schemas/sensor.py`).
  Es defensa en profundidad contra replay de un payload capturado en una red
  hostil (ej. un hotspot público) y atrapa bugs de reloj del ESP32, sin
  rechazar los reintentos legítimos del buffer RTC (que en el peor caso real
  llegan con ~1h de atraso).
- **Identidad de sensor_id vinculada a la API key** — el backend rechaza con
  `422` si el `sensor_id` del payload no coincide con el `device_id` del
  sensor autenticado por `X-Api-Key` (`app/services/sensor_service.py`), para
  que la key de un sensor no pueda escribir lecturas bajo el `sensor_id` de
  otro.

---

## Plan de Despliegue por Fases

### Fase 1 (MVP)
- 2-3 nodos de prueba con WiFi (en la orilla)
- Conectividad: WiFi del pueblo palafito más cercano
- Lecturas cada 15 minutos

### Fase 2 (Expansión)
- Nodos en zonas sin WiFi con módulo SIM7600
- 5-8 nodos distribuidos en zonas de pesca clave
- Lecturas cada 5 minutos

### Fase 3 (Red completa)
- 15+ nodos cubriendo la Ciénaga
- Integración con datos satelitales para contextualizar
- Dashboard de monitoreo en tiempo real
