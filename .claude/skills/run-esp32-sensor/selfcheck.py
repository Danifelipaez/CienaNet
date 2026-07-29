"""Self-check del driver de diagnostico ESP32 -- sin hardware real.

Usa serial.serial_for_url("loop://"), el transporte de loopback que trae
pyserial de fabrica, para probar la ruta completa (abrir puerto, leer
lineas, parsear, validar) sin una placa fisica conectada.

    python selfcheck.py
"""

import sys

import serial

import driver


def check(label, condition):
    status = "OK  " if condition else "FAIL"
    print(f"[{status}] {label}")
    return condition


def main():
    ok = True

    # 1) Lectura completa y valida
    good_line = (
        '{"sensor_id": "CGSM-001", "timestamp": "2025-06-20T14:30:00Z", '
        '"ph": 7.4, "conductivity_mscm": 12.5, "temperature_c": 28.3, "water_level_cm": 45.2}'
    )
    passed, detail = driver.diagnose_payload(good_line)
    ok &= check("lectura completa -> ok=True", passed)
    print(f"       detalle: {detail}")

    # 2) Campos opcionales ausentes (no es un fallo, pero se debe reportar)
    partial_line = '{"sensor_id": "CGSM-002", "timestamp": "2025-06-20T14:30:00Z", "ph": 7.1}'
    passed, detail = driver.diagnose_payload(partial_line)
    ok &= check("campos ausentes -> ok=True pero los reporta", passed and "SIN DATO" in detail)
    print(f"       detalle: {detail}")

    # 3) Valor fuera de rango (sonda pegada/desconectada)
    bad_range_line = '{"sensor_id": "CGSM-003", "timestamp": "2025-06-20T14:30:00Z", "ph": 99}'
    passed, detail = driver.diagnose_payload(bad_range_line)
    ok &= check("pH fuera de rango -> ok=False", not passed)
    print(f"       detalle: {detail}")

    # 4) Linea corrupta / no-JSON (baud rate incorrecto, log de debug, etc.)
    garbage_line = "E (1234) wifi: disconnected, retrying..."
    passed, detail = driver.diagnose_payload(garbage_line)
    ok &= check("linea no-JSON -> ok=False", not passed)
    print(f"       detalle: {detail}")

    # 5) Mensajes reales de firmware/alt_tend_sensor/alt_tend_sensor.ino (type: debug/boot/error)
    debug_ok_line = (
        '{"type":"debug","uptime_ms":5000,"ph":7.1,"ph_mv":410,"ph_adc_raw":1200,'
        '"tds_ppm":300,"tds_adc_raw":900,"temp_c":27.5,"temp_sensor_ok":true,'
        '"wifi_connected":true,"wifi_rssi":-58,"ntp_synced":true,"http_status":201,'
        '"buffer_pending":0,"free_heap":180000}'
    )
    passed, detail = driver.diagnose_payload(debug_ok_line)
    ok &= check("debug firmware, todo sano -> ok=True", passed)
    print(f"       detalle: {detail}")

    debug_bad_line = debug_ok_line.replace('"temp_sensor_ok":true', '"temp_sensor_ok":false').replace(
        '"wifi_connected":true', '"wifi_connected":false'
    ).replace('"http_status":201', '"http_status":403')
    passed, detail = driver.diagnose_payload(debug_bad_line)
    ok &= check("debug firmware, DS18B20/WiFi/API key fallando -> ok=False", not passed and "DS18B20" in detail)
    print(f"       detalle: {detail}")

    debug_422_line = debug_ok_line.replace('"http_status":201', '"http_status":422')
    passed, detail = driver.diagnose_payload(debug_422_line)
    ok &= check("debug firmware, HTTP 422 (fuera de rango) -> ok=False", not passed and "422" in detail)
    print(f"       detalle: {detail}")

    boot_panic_line = '{"type":"boot","reset_reason":4}'
    passed, detail = driver.diagnose_payload(boot_panic_line)
    ok &= check("boot con reset_reason=PANIC -> ok=False", not passed)
    print(f"       detalle: {detail}")

    boot_normal_line = '{"type":"boot","reset_reason":1}'
    passed, detail = driver.diagnose_payload(boot_normal_line)
    ok &= check("boot con reset_reason=POWERON -> ok=True", passed)
    print(f"       detalle: {detail}")

    # 6) Ruta completa: abrir puerto loopback, escribir una lectura simulada, leerla, diagnosticarla
    ser = serial.serial_for_url("loop://", baudrate=115200, timeout=1)
    ser.write((good_line + "\n").encode())
    lines = driver.read_lines(ser, seconds=1)
    ser.close()
    ok &= check("read_lines() recupera la linea escrita via loop://", lines == [good_line])

    # 7) Enumeracion de puertos reales de esta maquina no debe explotar
    try:
        candidates = driver.list_candidate_ports()
        ok &= check(f"list_candidate_ports() corre sin error ({len(candidates)} puerto(s) reales)", True)
    except Exception as e:
        ok &= check(f"list_candidate_ports() corre sin error ({e})", False)

    print("\nTODO OK" if ok else "\nHAY FALLOS")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
