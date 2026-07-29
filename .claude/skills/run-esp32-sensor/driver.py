"""Diagnostico de conexion fisica de un sensor ESP32 / boya CGSM por puerto serial (USB).

Uso:
    python driver.py --list                  # lista puertos detectados y candidatos ESP32
    python driver.py                         # auto-escanea todos los puertos y diagnostica
    python driver.py --port COM5             # diagnostica un puerto especifico
    python driver.py --port loop:// --baud 115200   # smoke test sin hardware (ver SKILL.md)

El firmware real (firmware/alt_tend_sensor/alt_tend_sensor.ino) despierta de
deep sleep cada TX_INTERVAL_SECONDS, lee sensores, conecta WiFi, hace POST a
/api/v1/sensors/ingest, y antes de volver a dormir imprime por Serial sus
propios mensajes {"type": "boot"/"debug"/"error", ...} -- no el payload que le
manda al API (ese va por WiFi, no por USB). Este driver entiende ese formato
propio (ver _diagnose_firmware_message). Tambien reconoce, como fallback, el
schema real de ingesta (docs/IOT_SENSORES.md / app/schemas/sensor.py) por si
algun otro firmware imprime esa forma en vez de la propia:
    {"sensor_id": "CGSM-001", "timestamp": "...", "ph": 7.4,
     "conductivity_mscm": 12.5, "temperature_c": 28.3, "water_level_cm": 45.2}
"""

import argparse
import json
import sys
import time
from pathlib import Path

# La consola de Windows suele usar cp1252/cp437, que no puede imprimir el
# caracter de reemplazo (U+FFFD) que read_lines() produce para bytes
# corruptos -- sin esto, reportar una linea garbled (justo el trabajo de
# esta herramienta) puede crashear el propio diagnostico.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import serial
from serial.tools import list_ports

# Chips USB-serial mas comunes en placas ESP32 (VID, PID) -> nombre
ESP32_VID_PID = {
    (0x10C4, 0xEA60): "CP2102 (ESP32 DevKit generico)",
    (0x1A86, 0x7523): "CH340 (clones baratos)",
    (0x303A, 0x1001): "ESP32-S2/S3 USB nativo",
    (0x303A, 0x0002): "ESP32-S3 USB nativo (modo 2)",
}

BAUD_RATES = [115200, 9600]  # 115200 = default typico de firmware ESP32; 9600 fallback

FIELDS = ["ph", "conductivity_mscm", "temperature_c", "water_level_cm"]
FIELD_LABELS = {
    "ph": "pH",
    "conductivity_mscm": "Conductividad",
    "temperature_c": "Temperatura",
    "water_level_cm": "Nivel de agua",
}

# esp_reset_reason() de firmware/alt_tend_sensor/alt_tend_sensor.ino
RESET_REASONS = {
    0: "UNKNOWN", 1: "POWERON", 2: "EXT", 3: "SW", 4: "PANIC",
    5: "INT_WDT", 6: "TASK_WDT", 7: "WDT", 8: "DEEPSLEEP",
    9: "BROWNOUT", 10: "SDIO",
}
CRASH_RESET_REASONS = {4, 5, 6, 7, 9}  # PANIC/WDT/BROWNOUT -> la tarjeta se estaba cayendo
LOW_HEAP_WARN_BYTES = 20_000  # heuristica: WebServer + Strings en handleRoot() fragmentan heap


def _find_repo_root(start: Path) -> Path:
    for d in (start, *start.parents):
        if (d / "app" / "schemas" / "sensor.py").exists():
            return d
    raise RuntimeError(
        "No se encontro la raiz del repo (buscando app/schemas/sensor.py). "
        "Corre este script dentro del repo CienaNet Bot."
    )


sys.path.insert(0, str(_find_repo_root(Path(__file__).resolve())))
from app.schemas.sensor import SensorReadingIn  # noqa: E402  (reusa la validacion real del API)
from pydantic import ValidationError  # noqa: E402


def guess_chip(port):
    if port.vid is not None and port.pid is not None:
        return ESP32_VID_PID.get((port.vid, port.pid))
    return None


def list_candidate_ports():
    return [(p, guess_chip(p)) for p in list_ports.comports()]


def read_lines(ser, seconds, max_lines=40):
    """Lee lineas terminadas en \\n de un puerto ya abierto, hasta `seconds` o `max_lines`."""
    end = time.time() + seconds
    lines = []
    buf = b""
    while time.time() < end and len(lines) < max_lines:
        chunk = ser.read(256)
        if not chunk:
            continue
        buf += chunk
        while b"\n" in buf and len(lines) < max_lines:
            line, buf = buf.split(b"\n", 1)
            line = line.strip()
            if line:
                lines.append(line.decode(errors="replace"))
    return lines


def _diagnose_firmware_message(msg_type, data):
    """Diagnostica el JSON propio de firmware/alt_tend_sensor/alt_tend_sensor.ino
    (type: boot/debug/error), que no sigue el schema del API de ingesta."""
    if msg_type == "boot":
        reason_code = data.get("reset_reason")
        reason = RESET_REASONS.get(reason_code, f"desconocido({reason_code})")
        if reason_code in CRASH_RESET_REASONS:
            return False, f"boot con reset anomalo: {reason} -- la tarjeta se reinicio sola (panic/watchdog/brownout)"
        return True, f"boot normal: {reason}"

    if msg_type == "error":
        return False, f"firmware reporto error: {data.get('msg')}"

    if msg_type == "debug":
        failing = []
        if data.get("temp_sensor_ok") is False:
            failing.append("sensor de temperatura (DS18B20) desconectado o sin responder")
        if data.get("wifi_connected") is False:
            failing.append("sin conexion WiFi (revisar WIFI_SSID/WIFI_PASSWORD en config.h, o alcance del AP)")
        http_status = data.get("http_status")
        if isinstance(http_status, (int, float)) and http_status >= 400:
            reason = "API key invalida (config.h)" if http_status == 403 else (
                "lectura fuera de rango (probable sonda danada/desconectada)" if http_status == 422
                else "servidor rechazo/fallo la peticion"
            )
            failing.append(f"ultimo POST rechazado (HTTP {http_status}) -- {reason}")
        elif isinstance(http_status, (int, float)) and http_status < 0:
            failing.append(f"ultimo POST fallo a nivel de transporte (codigo HTTPClient {http_status})")
        heap = data.get("free_heap")
        if isinstance(heap, (int, float)) and heap < LOW_HEAP_WARN_BYTES:
            failing.append(f"free_heap bajo ({heap} bytes, posible fuga de memoria)")

        detail = (
            f"ph={data.get('ph')} tds_ppm={data.get('tds_ppm')} temp_c={data.get('temp_c')} "
            f"wifi_connected={data.get('wifi_connected')} ntp_synced={data.get('ntp_synced')} "
            f"http_status={http_status} buffer_pending={data.get('buffer_pending')} free_heap={heap}"
        )
        if failing:
            return False, f"{detail} | FALLANDO: {'; '.join(failing)}"
        return True, f"{detail} | todo OK"

    return False, f"type={msg_type!r} desconocido: {data}"


def diagnose_payload(raw_line):
    """(ok, detalle) para una linea cruda leida del puerto."""
    try:
        data = json.loads(raw_line)
    except json.JSONDecodeError:
        return False, f"linea no es JSON valido: {raw_line!r} (baud rate incorrecto o log de debug del firmware?)"

    if not isinstance(data, dict):
        return False, f"JSON valido pero no es un objeto de lectura: {raw_line!r}"

    msg_type = data.get("type")
    if msg_type is not None:
        return _diagnose_firmware_message(msg_type, data)

    try:
        reading = SensorReadingIn(**data)
    except ValidationError as e:
        errors = "; ".join(f"{err['loc'][0]}: {err['msg']}" for err in e.errors())
        return False, f"lectura fuera de rango o incompleta -> {errors}"

    missing = [f for f in FIELDS if getattr(reading, f) is None]
    detail = f"sensor_id={reading.sensor_id}"
    detail += " | SIN DATO: " + ", ".join(FIELD_LABELS[f] for f in missing) if missing else " | todas las variables presentes"
    return True, detail


def open_serial(port_path, baud):
    if "://" in port_path:
        return serial.serial_for_url(port_path, baudrate=baud, timeout=1)
    return serial.Serial(port_path, baudrate=baud, timeout=1)


def diagnose_port(port_path, baud, timeout=5.0):
    print(f"\n-> Probando {port_path} @ {baud} baud...")
    try:
        ser = open_serial(port_path, baud)
    except serial.SerialException as e:
        print(f"   FALLO al abrir el puerto: {e}")
        return False

    try:
        lines = read_lines(ser, timeout)
    finally:
        ser.close()

    if not lines:
        print(f"   Puerto abierto pero SIN DATOS en {timeout}s. Firmware detenido, baud "
              "incorrecto, deep sleep activo, o el dispositivo conectado no es el sensor.")
        return False

    print(f"   {len(lines)} linea(s) recibida(s):")
    any_ok = False
    for line in lines:
        ok, detail = diagnose_payload(line)
        marker = "OK  " if ok else "FAIL"
        print(f"     [{marker}] {detail}")
        any_ok = any_ok or ok
    return any_ok


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", help="Puerto especifico (COM5, /dev/ttyUSB0, loop://...)")
    parser.add_argument("--baud", type=int, help="Baud rate especifico (default: prueba 115200 y 9600)")
    parser.add_argument("--timeout", type=float, default=8.0, help="Segundos a esperar datos por puerto/baud (default 8 -- la tarjeta ahora solo esta despierta 1-3s por ciclo de deep sleep)")
    parser.add_argument("--list", action="store_true", help="Solo listar puertos detectados, sin conectar")
    args = parser.parse_args(argv)

    candidates = list_candidate_ports()
    if not candidates and not args.port:
        print("No se detecto ningun puerto serial. Verifica el cable USB (debe ser de datos, "
              "no solo de carga) y que el driver CP2102/CH340 este instalado.")
        return 1

    print("Puertos detectados:")
    for p, chip in candidates:
        tag = f" <- posible ESP32 ({chip})" if chip else ""
        print(f"  {p.device}  [{p.description}]{tag}")

    if args.list:
        return 0

    baud_list = [args.baud] if args.baud else BAUD_RATES
    ports_to_try = [args.port] if args.port else [p.device for p, _ in candidates]

    found_data = False
    for port_path in ports_to_try:
        for baud in baud_list:
            if diagnose_port(port_path, baud, args.timeout):
                found_data = True
                break

    if not found_data:
        print("\nResumen: ningun puerto entrego datos validos del sensor. Ver detalle arriba.")
        return 1

    print("\nResumen: conexion OK, al menos una lectura valida recibida.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
