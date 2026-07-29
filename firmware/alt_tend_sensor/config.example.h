#pragma once

// Copiar este archivo a config.h y llenar con valores reales.
// config.h NO se commitea (ver .gitignore) -- contiene la API key del sensor.

// WIFI_SSID / WIFI_PASSWORD: credenciales de CUALQUIER red WiFi 2.4GHz que dé
// acceso a internet -- el firmware es agnostico al origen. Dos escenarios
// posibles, mismo codigo, mismo #define, sin rama distinta (ver
// conectarWiFi() en el .ino):
//   - Router domestico/institucional (ej. WiFi del pueblo palafito o de la
//     universidad).
//   - Hotspot compartido desde celular/PC (ej. el celular del pescador).
// Se descarto un modo "bridge por PC/USB" (relay serial) como via de
// produccion: exige un PC permanentemente encendido junto a la boya (rompe
// el diseño de boya autonoma a bateria con deep sleep) y obliga a que ese PC
// termine/reorigine la conexion TLS, viendo la API key y el payload en texto
// plano en esa etapa -- cosa que hoy NO pasa, porque el ESP32 habla TLS
// end-to-end directo contra el backend. Ver docs/IOT_SENSORES.md, seccion
// "Metodologias de Conectividad Evaluadas".
#define WIFI_SSID "TU_RED_WIFI"
#define WIFI_PASSWORD "TU_PASSWORD_WIFI"

// Backend: IP LAN + puerto para pruebas locales (API_USE_TLS 0).
// En produccion: API_HOST "api.<dominio>", API_PORT 443, API_USE_TLS 1 --
// una vez que la universidad asigne el dominio real (ver docs/DEPLOYMENT.md,
// hoy "api.<dominio>" es un placeholder literal, no existe todavia).
#define API_HOST "192.168.1.100"
#define API_PORT 8000
#define API_USE_TLS 0
#define API_INGEST_PATH "/api/v1/sensors/ingest"

// De POST /api/v1/admin/sensors -- el campo raw_api_key de la respuesta
// (se muestra una sola vez al registrar el sensor, no es recuperable despues).
#define DEVICE_API_KEY "PEGAR_RAW_API_KEY_AQUI"
#define DEVICE_ID "CGSM-TEST-BENCH-01"

#define TX_INTERVAL_SECONDS 5   // cadencia de prueba; despliegue real: 5-15 min (docs/IOT_SENSORES.md)
#define RTC_BUFFER_SIZE 4       // lecturas pendientes que sobreviven deep sleep en memoria RTC

#define WIFI_CONNECT_TIMEOUT_MS 8000
#define HTTP_TIMEOUT_MS 4000

#define NTP_SERVER "pool.ntp.org"
#define GMT_OFFSET_SEC 0
#define DAYLIGHT_OFFSET_SEC 0  // todo en UTC (timestamp con sufijo "Z"), sin horario de verano
