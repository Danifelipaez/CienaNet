---
name: run-esp32-sensor
description: Diagnostica la conexion fisica de un sensor ESP32 / boya CGSM conectado por USB, en cualquier puerto serial. Usar cuando se hable de sensor fisico, boya, ESP32, puerto serial/COM, o hardware IoT que no esta reportando datos. Detecta el puerto automaticamente (sin pedirlo), se conecta, y reporta que variable (pH, conductividad, temperatura, nivel de agua) falta o esta fuera de rango.
---

Herramienta de diagnostico para cuando hay un ESP32/boya CGSM conectado por
USB al equipo. El driver vive en `.claude/skills/run-esp32-sensor/driver.py`
y se corre con el Python del venv del proyecto.

`firmware/alt_tend_sensor/alt_tend_sensor.ino` (el sketch real del equipo,
Fase 2 "simulacion de campo") ya no usa AP+ESP-NOW -- despierta de deep
sleep cada `TX_INTERVAL_SECONDS` (5s en banco; 5-15 min en despliegue real,
`docs/IOT_SENSORES.md`), lee sensores, conecta WiFi STA, hace `POST
/api/v1/sensors/ingest` (con reintentos de un buffer chico en memoria RTC
si falla), actualiza el OLED, y antes de volver a dormir imprime por Serial
sus propios mensajes `{"type": "boot"/"debug"/"error", ...}` -- el driver
ya entiende ese formato (ver `_diagnose_firmware_message` en `driver.py`),
que no es el mismo schema que el payload que le manda al API por WiFi.

## Prerequisitos

```bash
.venv/Scripts/python.exe -m pip install pyserial
```

(`pyserial` es solo para este diagnostico de banco — no se agrega a
`requirements.txt` del servicio porque el servidor de produccion nunca abre
un puerto serial.)

## Run (agent path)

Desde la raiz del repo:

```bash
.venv/Scripts/python.exe .claude/skills/run-esp32-sensor/driver.py --list
```

Lista los puertos seriales de la maquina e identifica por VID:PID los chips
USB-serial tipicos de ESP32 (CP2102, CH340, USB nativo S2/S3).

```bash
.venv/Scripts/python.exe .claude/skills/run-esp32-sensor/driver.py
```

Sin argumentos: auto-escanea **todos** los puertos detectados, prueba
115200 y 9600 baud en cada uno, lee hasta 40 lineas o 8 segundos (default),
y por cada linea reporta si es un mensaje sano del firmware propio
(`type: boot/debug/error`) o, en su defecto, una lectura JSON valida contra
el schema del API real (`SensorReadingIn`, `app/schemas/sensor.py`).

```bash
.venv/Scripts/python.exe .claude/skills/run-esp32-sensor/driver.py --port COM3 --timeout 8
```

Para apuntar a un puerto especifico (`COM5` en Windows, `/dev/ttyUSB0` en
Linux) o darle mas tiempo a un sensor con `deep sleep` largo entre lecturas.

Salida real capturada en esta sesion contra un ESP32 conectado a COM3 (sin
firmware de sensor flasheado, solo el bootloader de fabrica):

```
Puertos detectados:
  COM3  [Silicon Labs CP210x USB to UART Bridge (COM3)] <- posible ESP32 (CP2102 (ESP32 DevKit generico))

-> Probando COM3 @ 115200 baud...
   11 linea(s) recibida(s):
     [FAIL] linea no es JSON valido: 'ets Jul 29 2019 12:21:46' (baud rate incorrecto o log de debug del firmware?)
     [FAIL] linea no es JSON valido: 'rst:0x1 (POWERON_RESET),boot:0x13 (SPI_FAST_FLASH_BOOT)' (...)
     ...
-> Probando COM3 @ 9600 baud...
   Puerto abierto pero SIN DATOS en 4.0s. ...

Resumen: ningun puerto entrego datos validos del sensor. Ver detalle arriba.
```

Eso es exactamente el diagnostico correcto: hay un ESP32 real ahi (chip
CP2102 identificado, boot log del ROM leido), pero no esta emitiendo
lecturas de sensor por serial — falta flashear firmware que haga
`Serial.println()` del JSON, o el que tiene no lo hace.

## Smoke test sin hardware (loopback)

`pyserial` trae un transporte de loopback (`loop://`) que no requiere placa
fisica. `selfcheck.py` lo usa para probar el pipeline completo (leer
lineas, parsear JSON, validar rangos) con casos: lectura completa, campos
opcionales ausentes, valor fuera de rango, linea corrupta:

```bash
.venv/Scripts/python.exe .claude/skills/run-esp32-sensor/selfcheck.py
```

Corre tambien `list_candidate_ports()` contra los puertos reales de la
maquina (no debe explotar aunque no haya ninguno).

## Gotchas

- **Abrir el puerto resetea el ESP32.** El adaptador CP2102/CH340 typico
  usa DTR/RTS para el auto-reset (igual que el Monitor Serial de
  Arduino/PlatformIO) — al conectar, vas a ver el boot log del ROM
  (`ets Jul .. `, `rst:0x1 (POWERON_RESET)...`) antes que cualquier dato de
  aplicacion. Es normal, no es un fallo de conexion.
- **Cada intento de baud reabre el puerto -> otro reset.** Si no se pasa
  `--baud`, el driver prueba 115200 y despues 9600 cuando el primero no
  entrega una linea reconocible; cada intento es un open/close nuevo, o sea
  hasta dos resets seguidos. Una vez confirmado el baud real del firmware
  (115200 en `alt_tend_sensor.ino`), pasar `--baud 115200` explicito evita
  el segundo reset innecesario.
- **El boot log NO es JSON** — el driver lo reporta como `FAIL` linea por
  linea. Eso no significa que el sensor este roto; significa que el
  firmware de aplicacion (el que de verdad manda pH/conductividad/etc.)
  todavia no corrio, no esta flasheado, o no imprime nada por Serial (el
  pseudocodigo de `docs/IOT_SENSORES.md` solo manda por WiFi, no imprime).
  Para diagnosticar con esta herramienta, el firmware debe agregar un
  `Serial.println()` del mismo JSON que le manda a `sendToAPI()`.
- **Un solo dato fuera de rango no tumba el sensor completo** — el driver
  reusa los mismos limites de `SensorReadingIn` (ph 0-14, temperatura -5 a
  45C, conductividad 0-80 mS/cm, nivel 0-500cm) para marcar esa variable
  puntual como sospechosa (sonda pegada/desconectada), sin descartar el
  resto de la lectura.
- **Campos opcionales ausentes no son un error** — `docs/IOT_SENSORES.md`
  permite omitir/null los sensores que un nodo no tenga. El driver los
  reporta como "SIN DATO: X" mas que como fallo (`ok=True`).
- **La tarjeta ahora solo esta despierta 1-3s por ciclo** (deep sleep entre
  transmisiones) — con `TX_INTERVAL_SECONDS=5` de banco, un `--timeout`
  corto puede no alcanzar a ver ni una linea `debug` completa. Usar al menos
  `--timeout 8` (default actual del driver) para cubrir un ciclo completo.

## Troubleshooting

| Sintoma | Causa / que hacer |
|---|---|
| "No se detecto ningun puerto serial" | Cable USB de solo carga (sin datos), o falta el driver CP2102/CH340 del sistema operativo. |
| Puerto abre pero 0 lineas en el timeout | Firmware en `deep sleep` (subir `--timeout`), placa sin firmware, o placa que no es el sensor. |
| Solo boot log del ROM, nunca JSON | Firmware de sensor no flasheado o sin `Serial.println()` del payload (ver Gotchas). |
| `FAIL` con "fuera de rango" en una sola variable | Esa sonda especifica esta desconectada o pegada en un riel — no revisar las demas variables, ya vinieron OK. |
| `ph` pegado cerca de -11 y `tds_ppm` en 0 | ADC de pH cerca del riel de 3.3V y ADC de TDS cerca de 0 = sondas no conectadas al header, no un fallo de firmware. Tambien puede ser que falte calibrar `Vneutral`/`pendiente` con buffers pH 4.0/7.0 (`docs/IOT_SENSORES.md`). |
| `wifi_connected: false` | Revisar `WIFI_SSID`/`WIFI_PASSWORD` en `config.h` (no `config.example.h`), o que la tarjeta este dentro del alcance de esa red. |
| `http_status: 403` | `DEVICE_API_KEY` en `config.h` no coincide con ningun `raw_api_key` registrado (`POST /api/v1/admin/sensors`) -- no es lo mismo que `SENSOR_API_KEY_SECRET` del backend. |
| `http_status: 422` | Lectura fuera de rango (ph 0-14, temp -5 a 45C, EC 0-80 mS/cm, nivel 0-500cm) -- con la sonda de pH dañada esto es esperado, no un bug del firmware nuevo. El firmware no reintenta un 422 (fallo permanente). |
| `http_status` negativo | Error de transporte de `HTTPClient` (sin respuesta, timeout, host inalcanzable) -- confirmar que `API_HOST`/`API_PORT` en `config.h` apuntan al backend real y que este corriendo. Se trata como fallo transitorio: se reintenta el proximo ciclo via el buffer RTC. |
| `buffer_pending` subiendo y no baja | El backend sigue devolviendo fallos transitorios; el firmware para de vaciar el buffer en el primer fallo transitorio de cada ciclo para no insistir contra un servidor caido. Tope 4 (`RTC_BUFFER_SIZE`), se descarta la mas vieja al llenarse. |
