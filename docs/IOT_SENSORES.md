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
Authorization: Bearer {SENSOR_API_KEY}
Content-Type: application/json
```

### Payload
```json
{
  "sensor_id": "CGSM-001",
  "readings": [
    {
      "ph": 7.4,
      "conductivity_ms": 12.5,
      "temperature_c": 28.3,
      "timestamp": "2025-06-20T14:30:00Z",
      "battery_mv": 3700,
      "signal_rssi": -65
    }
  ]
}
```

El array `readings` permite enviar múltiples lecturas acumuladas de una vez (buffer local).

### Respuesta esperada
```json
{
  "status": "ok",
  "stored": 1,
  "alerts_triggered": []
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

---

## Identificación de Sensores

Formato de ID: `CGSM-{zona}-{número}`
- `CGSM-001` — Zona norte
- `CGSM-002` — Zona sur
- `CGSM-003` — Boca de la Barra
- etc.

Las coordenadas y zona de cada sensor se registran en la tabla `sensors` de la DB al activarlo por primera vez.

---

## Seguridad del Firmware

- **API key única por dispositivo** — si un sensor es comprometido, revocar solo esa key
- **API key en EEPROM cifrada** del ESP32, no en código fuente
- **HTTPS obligatorio** — ESP32 soporta TLS con la librería WiFiClientSecure
- **Verificar certificado del servidor** — no usar `setInsecure()` en producción

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
