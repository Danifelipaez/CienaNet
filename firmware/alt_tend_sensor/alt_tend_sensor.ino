#include <SPI.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SH110X.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <time.h>
#include <math.h>
#include <string.h>
#include <esp_sleep.h>
#include <esp_system.h>
#include "config.h"

// ===== OLED =====
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64

#define OLED_MOSI 23
#define OLED_CLK  18
#define OLED_DC   16
#define OLED_CS   5
#define OLED_RST  17

Adafruit_SH1106G display = Adafruit_SH1106G(SCREEN_WIDTH, SCREEN_HEIGHT, &SPI, OLED_DC, OLED_RST, OLED_CS);

// ===== SENSORES =====
int pinPH = 34;
int pinTDS = 35;

// ===== TEMPERATURA =====
#define ONE_WIRE_BUS 22
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);

// ===== VARIABLES =====
float ph = 0;
float tds = 0;
float temp = 0;
float mV_PH = 0;

// lecturas crudas, guardadas solo para el stream de debug (ver streamDebugJSON)
float lastAdcPH = 0;
float lastAdcTDS = 0;

// ===== CALIBRACION =====
float Vneutral = 0;
float pendiente = 0.18;

// ===== DEBUG STREAM (USB) =====
// Stream JSON por Serial (115200) para diagnostico via
// .claude/skills/run-esp32-sensor/driver.py. "Temporal": un solo #define para
// apagarlo cuando ya no haga falta banco de pruebas.
#define DEBUG_STREAM_ENABLED 1

// ===== MODO DEBUG: PANTALLA SIEMPRE ENCENDIDA =====
// El deep sleep deja flotando los pines no-RTC (OLED_RST entre ellos), lo que
// puede apagar/resetear el OLED durante el sueno -- justo cuando mas hace
// falta ver la pantalla mientras se depura el fallo de reconexion WiFi (ver
// config.h). Con esto en 1, el ciclo termina en delay() en vez de deep sleep,
// asi la pantalla nunca pierde la imagen entre lecturas. Volver a 0 (deep
// sleep real) antes de desplegar en campo -- ahi si importa la bateria.
#define KEEP_DISPLAY_ON_DEBUG 1

bool wifiConnected = false;
int lastHttpStatus = 0;  // 0 = sin intento este ciclo; negativo = error de transporte

// ===== BUFFER DE REINTENTO (memoria RTC -- sobrevive deep sleep, la RAM normal no) =====
typedef struct {
  time_t timestamp;         // momento real de captura, no el de reenvio
  float ph;
  float conductivity_mscm;  // NAN = null (sin sonda EC calibrada todavia)
  float temperature_c;      // NAN = null (DS18B20 desconectado)
  float water_level_cm;     // NAN = null (no existe ese sensor en esta tarjeta)
} PendingReading;

RTC_DATA_ATTR bool rtc_ntp_synced = false;
RTC_DATA_ATTR PendingReading rtcBuffer[RTC_BUFFER_SIZE];
RTC_DATA_ATTR uint8_t rtcBufferCount = 0;

// Declarado antes de cualquier funcion: el generador de prototipos del IDE de
// Arduino inserta sus forward-declarations justo antes de la primera funcion
// del archivo, y no entiende tipos custom declarados despues de ese punto.
enum PostOutcome { POST_SUCCESS, POST_PERMANENT_FAIL, POST_TRANSIENT_FAIL };

#if API_USE_TLS
// Roots publicos (no secretos) para validar el certificado del backend en
// produccion (docs/IOT_SENSORES.md prohibe setInsecure()). Dos roots
// concatenados en un solo buffer -- WiFiClientSecure::setCACert() delega en
// mbedtls_x509_crt_parse(), que acepta multiples bloques PEM en un mismo
// string y los agrega todos al almacen de confianza. Con esto la misma
// build sirve para cualquiera de los dos backends reales de este proyecto:
//   - Servidor universitario (Caddy + Let's Encrypt) -> ISRG Root X1
//   - ciena-net.vercel.app (Vercel, mientras siga vivo -- ver
//     docs/DEPLOYMENT.md "Deuda: doble despliegue") -> Google Trust
//     Services, root extraido en vivo de una conexion real a
//     ciena-net.vercel.app:443 (2026-07-29), variante cross-firmada por
//     GlobalSign Root CA (vence 2028-01-28; si Vercel rota de root antes de
//     esa fecha, hay que repetir la extraccion).
static const char TRUSTED_ROOTS_PEM[] =
R"EOF(
-----BEGIN CERTIFICATE-----
MIIFazCCA1OgAwIBAgIRAIIQz7DSQONZRGPgu2OCiwAwDQYJKoZIhvcNAQELBQAw
TzELMAkGA1UEBhMCVVMxKTAnBgNVBAoTIEludGVybmV0IFNlY3VyaXR5IFJlc2Vh
cmNoIEdyb3VwMRUwEwYDVQQDEwxJU1JHIFJvb3QgWDEwHhcNMTUwNjA0MTEwNDM4
WhcNMzUwNjA0MTEwNDM4WjBPMQswCQYDVQQGEwJVUzEpMCcGA1UEChMgSW50ZXJu
ZXQgU2VjdXJpdHkgUmVzZWFyY2ggR3JvdXAxFTATBgNVBAMTDElTUkcgUm9vdCBY
MTCCAiIwDQYJKoZIhvcNAQEBBQADggIPADCCAgoCggIBAK3oJHP0FDfzm54rVygc
h77ct984kIxuPOZXoHj3dcKi/vVqbvYATyjb3miGbESTtrFj/RQSa78f0uoxmyF+
0TM8ukj13Xnfs7j/EvEhmkvBioZxaUpmZmyPfjxwv60pIgbz5MDmgK7iS4+3mX6U
A5/TR5d8mUgjU+g4rk8Kb4Mu0UlXjIB0ttov0DiNewNwIRt18jA8+o+u3dpjq+sW
T8KOEUt+zwvo/7V3LvSye0rgTBIlDHCNAymg4VMk7BPZ7hm/ELNKjD+Jo2FR3qyH
B5T0Y3HsLuJvW5iB4YlcNHlsdu87kGJ55tukmi8mxdAQ4Q7e2RCOFvu396j3x+UC
B5iPNgiV5+I3lg02dZ77DnKxHZu8A/lJBdiB3QW0KtZB6awBdpUKD9jf1b0SHzUv
KBds0pjBqAlkd25HN7rOrFleaJ1/ctaJxQZBKT5ZPt0m9STJEadao0xAH0ahmbWn
OlFuhjuefXKnEgV4We0+UXgVCwOPjdAvBbI+e0ocS3MFEvzG6uBQE3xDk3SzynTn
jh8BCNAw1FtxNrQHusEwMFxIt4I7mKZ9YIqioymCzLq9gwQbooMDQaHWBfEbwrbw
qHyGO0aoSCqI3Haadr8faqU9GY/rOPNk3sgrDQoo//fb4hVC1CLQJ13hef4Y53CI
rU7m2Ys6xt0nUW7/vGT1M0NPAgMBAAGjQjBAMA4GA1UdDwEB/wQEAwIBBjAPBgNV
HRMBAf8EBTADAQH/MB0GA1UdDgQWBBR5tFnme7bl5AFzgAiIyBpY9umbbjANBgkq
hkiG9w0BAQsFAAOCAgEAVR9YqbyyqFDQDLHYGmkgJykIrGF1XIpu+ILlaS/V9lZL
ubhzEFnTIZd+50xx+7LSYK05qAvqFyFWhfFQDlnrzuBZ6brJFe+GnY+EgPbk6ZGQ
3BebYhtF8GaV0nxvwuo77x/Py9auJ/GpsMiu/X1+mvoiBOv/2X/qkSsisRcOj/KK
NFtY2PwByVS5uCbMiogziUwthDyC3+6WVwW6LLv3xLfHTjuCvjHIInNzktHCgKQ5
ORAzI4JMPJ+GslWYHb4phowim57iaztXOoJwTdwJx4nLCgdNbOhdjsnvzqvHu7Ur
TkXWStAmzOVyyghqpZXjFaH3pO3JLF+l+/+sKAIuvtd7u+Nxe5AW0wdeRlN8NwdC
jNPElpzVmbUq4JUagEiuTDkHzsxHpFKVK7q4+63SM1N95R1NbdWhscdCb+ZAJzVc
oyi3B43njTOQ5yOf+1CceWxG1bQVs5ZufpsMljq4Ui0/1lvh+wjChP4kqKOJ2qxq
4RgqsahDYVvTH9w7jXbyLeiNdd8XM2w9U/t7y0Ff/9yi0GE44Za4rF2LN9d11TPA
mRGunUHBcnWEvgJBQl9nJEiU0Zsnvgc/ubhPgXRR4Xq37Z0j4r7g1SgEEzwxA57d
emyPxgcYxn/eR44/KJ4EBs+lVDR3veyJm+kXQ99b21/+jh5Xos1AnX5iItreGCc=
-----END CERTIFICATE-----
)EOF"
R"EOF(
-----BEGIN CERTIFICATE-----
MIIFYjCCBEqgAwIBAgIQd70NbNs2+RrqIQ/E8FjTDTANBgkqhkiG9w0BAQsFADBX
MQswCQYDVQQGEwJCRTEZMBcGA1UEChMQR2xvYmFsU2lnbiBudi1zYTEQMA4GA1UE
CxMHUm9vdCBDQTEbMBkGA1UEAxMSR2xvYmFsU2lnbiBSb290IENBMB4XDTIwMDYx
OTAwMDA0MloXDTI4MDEyODAwMDA0MlowRzELMAkGA1UEBhMCVVMxIjAgBgNVBAoT
GUdvb2dsZSBUcnVzdCBTZXJ2aWNlcyBMTEMxFDASBgNVBAMTC0dUUyBSb290IFIx
MIICIjANBgkqhkiG9w0BAQEFAAOCAg8AMIICCgKCAgEAthECix7joXebO9y/lD63
ladAPKH9gvl9MgaCcfb2jH/76Nu8ai6Xl6OMS/kr9rH5zoQdsfnFl97vufKj6bwS
iV6nqlKr+CMny6SxnGPb15l+8Ape62im9MZaRw1NEDPjTrETo8gYbEvs/AmQ351k
KSUjB6G00j0uYODP0gmHu81I8E3CwnqIiru6z1kZ1q+PsAewnjHxgsHA3y6mbWwZ
DrXYfiYaRQM9sHmklCitD38m5agI/pboPGiUU+6DOogrFZYJsuB6jC511pzrp1Zk
j5ZPaK49l8KEj8C8QMALXL32h7M1bKwYUH+E4EzNktMg6TO8UpmvMrUpsyUqtEj5
cuHKZPfmghCN6J3Cioj6OGaK/GP5Afl4/Xtcd/p2h/rs37EOeZVXtL0m79YB0esW
CruOC7XFxYpVq9Os6pFLKcwZpDIlTirxZUTQAs6qzkm06p98g7BAe+dDq6dso499
iYH6TKX/1Y7DzkvgtdizjkXPdsDtQCv9Uw+wp9U7DbGKogPeMa3Md+pvez7W35Ei
Eua++tgy/BBjFFFy3l3WFpO9KWgz7zpm7AeKJt8T11dleCfeXkkUAKIAf5qoIbap
sZWwpbkNFhHax2xIPEDgfg1azVY80ZcFuctL7TlLnMQ/0lUTbiSw1nH69MG6zO0b
9f6BQdgAmD06yK56mDcYBZUCAwEAAaOCATgwggE0MA4GA1UdDwEB/wQEAwIBhjAP
BgNVHRMBAf8EBTADAQH/MB0GA1UdDgQWBBTkrysmcRorSCeFL1JmLO/wiRNxPjAf
BgNVHSMEGDAWgBRge2YaRQ2XyolQL30EzTSo//z9SzBgBggrBgEFBQcBAQRUMFIw
JQYIKwYBBQUHMAGGGWh0dHA6Ly9vY3NwLnBraS5nb29nL2dzcjEwKQYIKwYBBQUH
MAKGHWh0dHA6Ly9wa2kuZ29vZy9nc3IxL2dzcjEuY3J0MDIGA1UdHwQrMCkwJ6Al
oCOGIWh0dHA6Ly9jcmwucGtpLmdvb2cvZ3NyMS9nc3IxLmNybDA7BgNVHSAENDAy
MAgGBmeBDAECATAIBgZngQwBAgIwDQYLKwYBBAHWeQIFAwIwDQYLKwYBBAHWeQIF
AwMwDQYJKoZIhvcNAQELBQADggEBADSkHrEoo9C0dhemMXoh6dFSPsjbdBZBiLg9
NR3t5P+T4Vxfq7vqfM/b5A3Ri1fyJm9bvhdGaJQ3b2t6yMAYN/olUazsaL+yyEn9
WprKASOshIArAoyZl+tJaox118fessmXn1hIVw41oeQa1v1vg4Fv74zPl6/AhSrw
9U5pCZEt4Wi4wStz6dTZ/CLANx8LZh1J7QJVj2fhMtfTJr9w4z30Z209fOU0iOMy
+qduBmpvvYuR7hZL6Dupszfnw0Skfths18dG9ZKb59UhvmaSGZRVbNQpsg3BZlvi
d0lIKO2d1xozclOzgjXPYovJJIultzkMu34qQb9Sz/yilrbCgj8=
-----END CERTIFICATE-----
)EOF";
#endif

// ===== SENSORES =====
void leerSensores() {
  float sumaPH = 0;
  for (int i = 0; i < 10; i++) {
    sumaPH += analogRead(pinPH);
    delay(10);
  }
  float adcPH = sumaPH / 10.0;
  float voltPH = adcPH * (3.3 / 4095.0);
  lastAdcPH = adcPH;

  ph = 7 + ((Vneutral - voltPH) / pendiente);
  mV_PH = voltPH * 1000;

  float sumaTDS = 0;
  for (int i = 0; i < 10; i++) {
    sumaTDS += analogRead(pinTDS);
    delay(10);
  }
  float adcTDS = sumaTDS / 10.0;
  float voltTDS = adcTDS * (3.3 / 4095.0);
  lastAdcTDS = adcTDS;

  tds = (133.42 * pow(voltTDS, 3)
        - 255.86 * pow(voltTDS, 2)
        + 857.39 * voltTDS) * 0.5;

  sensors.requestTemperatures();
  temp = sensors.getTempCByIndex(0);
}

// ===== WIFI / NTP =====
// WiFi STA generico: router u hotspot son el mismo modo, solo cambia el
// SSID/password en config.h (ver comentario ahi). Sin rama de codigo.
bool conectarWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  unsigned long start = millis();
  int lastFrame = -1;
  while (WiFi.status() != WL_CONNECTED && millis() - start < WIFI_CONNECT_TIMEOUT_MS) {
    // el poll de status corre rapido (30ms) para no perder tiempo de conexion real;
    // el redibujado del spinner se throttlea a ~200ms para no saturar el bus SPI
    int frame = ((millis() - start) / 200) % 8;
    if (frame != lastFrame) {
#if DISPLAY_ENABLED
      showWifiConnectingScreen(frame);  // pantalla siempre encendida: mostrar tambien el spinner de conexion
#endif
      lastFrame = frame;
    }
    delay(30);
  }
  return WiFi.status() == WL_CONNECTED;
}

bool sincronizarNTP() {
  configTime(GMT_OFFSET_SEC, DAYLIGHT_OFFSET_SEC, NTP_SERVER);
  struct tm timeinfo;
  return getLocalTime(&timeinfo, 5000);
}

void formatIso8601(time_t t, char *buf, size_t bufSize) {
  struct tm timeinfo;
  gmtime_r(&t, &timeinfo);
  strftime(buf, bufSize, "%Y-%m-%dT%H:%M:%SZ", &timeinfo);
}

// ===== PAQUETE / TRANSMISION =====
PendingReading currentReading() {
  PendingReading r;
  r.timestamp = time(nullptr);
  r.ph = ph;
  r.conductivity_mscm = NAN;               // sin sonda EC calibrada (docs/IOT_SENSORES.md)
  r.temperature_c = (temp > -100.0) ? temp : NAN;  // -127 = DS18B20 desconectado
  r.water_level_cm = NAN;                  // no existe ese sensor en esta tarjeta
  return r;
}

void buildReadingJSON(const PendingReading &r, char *buf, size_t bufSize) {
  char tsBuf[25];
  formatIso8601(r.timestamp, tsBuf, sizeof(tsBuf));

  char phField[16], ecField[16], tempField[16], levelField[16];
  snprintf(phField, sizeof(phField), "%.2f", r.ph);
  if (isnan(r.conductivity_mscm)) snprintf(ecField, sizeof(ecField), "null");
  else snprintf(ecField, sizeof(ecField), "%.2f", r.conductivity_mscm);
  if (isnan(r.temperature_c)) snprintf(tempField, sizeof(tempField), "null");
  else snprintf(tempField, sizeof(tempField), "%.1f", r.temperature_c);
  if (isnan(r.water_level_cm)) snprintf(levelField, sizeof(levelField), "null");
  else snprintf(levelField, sizeof(levelField), "%.1f", r.water_level_cm);

  snprintf(buf, bufSize,
    "{\"sensor_id\":\"%s\",\"timestamp\":\"%s\",\"ph\":%s,"
    "\"conductivity_mscm\":%s,\"temperature_c\":%s,\"water_level_cm\":%s}",
    DEVICE_ID, tsBuf, phField, ecField, tempField, levelField);
}

int postReading(const char *jsonBody) {
  HTTPClient http;
  int statusCode;

#if API_USE_TLS
  WiFiClientSecure client;
  client.setCACert(TRUSTED_ROOTS_PEM);
  String url = String("https://") + API_HOST + API_INGEST_PATH;
  http.begin(client, url);
#else
  WiFiClient client;
  http.begin(client, API_HOST, API_PORT, API_INGEST_PATH);
#endif

  http.setTimeout(HTTP_TIMEOUT_MS);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Api-Key", DEVICE_API_KEY);

  statusCode = http.POST((uint8_t *)jsonBody, strlen(jsonBody));
  http.end();
  return statusCode;  // negativo = error de transporte (HTTPClient), positivo = status HTTP real
}

PostOutcome classifyHttpStatus(int statusCode) {
  if (statusCode >= 200 && statusCode < 300) return POST_SUCCESS;        // 201 esperado, pero cualquier 2xx cuenta
  if (statusCode >= 400 && statusCode < 500) return POST_PERMANENT_FAIL; // error del cliente (key mala, payload invalido): reintentar es inutil
  return POST_TRANSIENT_FAIL;  // timeout, sin respuesta, 5xx
}

// Reintenta solo fallos transitorios (timeout/5xx) -- exito o fallo permanente
// cortan el loop de inmediato. UPLOAD_MAX_RETRIES/UPLOAD_RETRY_DELAY_MS en config.h.
int postReadingWithRetries(const char *jsonBody) {
  int status;
  for (int attempt = 1; attempt <= UPLOAD_MAX_RETRIES; attempt++) {
    status = postReading(jsonBody);
    if (classifyHttpStatus(status) != POST_TRANSIENT_FAIL) break;
    if (attempt < UPLOAD_MAX_RETRIES) delay(UPLOAD_RETRY_DELAY_MS);
  }
  return status;
}

// ===== BUFFER RTC =====
void rtcBufferPush(const PendingReading &r) {
  if (rtcBufferCount >= RTC_BUFFER_SIZE) {
    // buffer lleno: se descarta la mas vieja, la recencia importa mas que la completitud
    for (int i = 0; i < RTC_BUFFER_SIZE - 1; i++) rtcBuffer[i] = rtcBuffer[i + 1];
    rtcBufferCount = RTC_BUFFER_SIZE - 1;
  }
  rtcBuffer[rtcBufferCount] = r;
  rtcBufferCount++;
}

void rtcBufferRemoveFront() {
  for (int i = 0; i < rtcBufferCount - 1; i++) rtcBuffer[i] = rtcBuffer[i + 1];
  rtcBufferCount--;
}

void flushRtcBuffer() {
  char json[256];
  while (rtcBufferCount > 0) {
    buildReadingJSON(rtcBuffer[0], json, sizeof(json));
    int status = postReadingWithRetries(json);
    lastHttpStatus = status;
    if (classifyHttpStatus(status) == POST_TRANSIENT_FAIL) {
      break;  // servidor sigue sin responder bien: no seguir golpeando el resto del buffer
    }
    rtcBufferRemoveFront();  // exito o fallo permanente -> ya no hay nada que hacer con esta entrada
  }
}

// ===== DEBUG STREAM (USB) =====
void streamDebugJSON() {
#if DEBUG_STREAM_ENABLED
  bool tempOk = (temp > -100.0);

  Serial.print("{\"type\":\"debug\",");
  Serial.print("\"uptime_ms\":"); Serial.print(millis()); Serial.print(",");
  Serial.print("\"ph\":"); Serial.print(ph, 2); Serial.print(",");
  Serial.print("\"ph_mv\":"); Serial.print(mV_PH, 0); Serial.print(",");
  Serial.print("\"ph_adc_raw\":"); Serial.print(lastAdcPH, 0); Serial.print(",");
  Serial.print("\"tds_ppm\":"); Serial.print(tds, 0); Serial.print(",");
  Serial.print("\"tds_adc_raw\":"); Serial.print(lastAdcTDS, 0); Serial.print(",");
  Serial.print("\"temp_c\":"); Serial.print(temp, 1); Serial.print(",");
  Serial.print("\"temp_sensor_ok\":"); Serial.print(tempOk ? "true" : "false"); Serial.print(",");
  Serial.print("\"wifi_connected\":"); Serial.print(wifiConnected ? "true" : "false"); Serial.print(",");
  Serial.print("\"wifi_rssi\":"); Serial.print(wifiConnected ? WiFi.RSSI() : 0); Serial.print(",");
  Serial.print("\"ntp_synced\":"); Serial.print(rtc_ntp_synced ? "true" : "false"); Serial.print(",");
  Serial.print("\"http_status\":"); Serial.print(lastHttpStatus); Serial.print(",");
  Serial.print("\"buffer_pending\":"); Serial.print(rtcBufferCount); Serial.print(",");
  Serial.print("\"free_heap\":"); Serial.print(ESP.getFreeHeap());
  Serial.println("}");
#endif
}

// ===== OLED: ICONOS Y ANIMACIONES =====
// Grilla fija para que nada se solape: franja de estado y=0-9, divisoria y=11,
// tres filas de sensores de 16px (y=13/29/45), etiqueta x=0-24 / valor x=40+.
// Todo dibujado con primitivas de Adafruit_GFX -- sin bitmaps ni libs nuevas.

void drawWifiIcon(int x, int y, bool connected, int rssi) {
  int heights[3] = { 2, 4, 6 };
  int filled = 0;
  if (connected) {
    // ponytail: umbrales de RSSI heuristicos (no calibrados contra hardware real)
    if (rssi > -60) filled = 3;
    else if (rssi > -75) filled = 2;
    else filled = 1;
  }
  for (int i = 0; i < 3; i++) {
    int bx = x + i * 4;
    int h = heights[i];
    int by = y + 7 - h;
    if (i < filled) display.fillRect(bx, by, 2, h, SH110X_WHITE);
    else display.drawRect(bx, by, 2, h, SH110X_WHITE);
  }
}

void drawCloudIcon(int x, int y, bool attempted, bool success) {
  int cx = x + 4, cy = y + 4;
  display.drawCircle(cx, cy, 4, SH110X_WHITE);
  if (!attempted) return;  // hueco = sin intento de envio este ciclo
  if (success) {
    display.fillCircle(cx, cy, 2, SH110X_WHITE);
  } else {
    display.drawLine(cx - 2, cy - 2, cx + 2, cy + 2, SH110X_WHITE);
    display.drawLine(cx - 2, cy + 2, cx + 2, cy - 2, SH110X_WHITE);
  }
}

void drawNtpDot(int x, int y, bool synced) {
  int cx = x + 3, cy = y + 4;
  if (synced) display.fillCircle(cx, cy, 3, SH110X_WHITE);
  else display.drawCircle(cx, cy, 3, SH110X_WHITE);
}

void drawBufferBadge(int x, int y, int count) {
  char buf[8];
  snprintf(buf, sizeof(buf), "B:%d", count);
  if (count > 0) {
    // fondo invertido: salta a la vista que hay lecturas pendientes de reenviar
    display.fillRect(x - 2, y - 1, (int)strlen(buf) * 6 + 3, 10, SH110X_WHITE);
    display.setTextColor(SH110X_BLACK);
  } else {
    display.setTextColor(SH110X_WHITE);
  }
  display.setTextSize(1);
  display.setCursor(x, y);
  display.print(buf);
  display.setTextColor(SH110X_WHITE);  // restaurar para el resto del frame
}

// Cabecera comun a las 3 pantallas del ciclo (conectando / enviando / dashboard final).
void drawStatusHeader(bool connected, int rssi, bool httpAttempted, bool httpSuccess,
                       int httpStatus, bool ntpSynced, int bufferCount) {
  drawWifiIcon(0, 0, connected, rssi);
  display.setTextSize(1);
  display.setCursor(11, 0);
  display.setTextColor(SH110X_WHITE);
  if (connected) display.print(rssi);
  else display.print("--");

  drawCloudIcon(40, 0, httpAttempted, httpSuccess);
  display.setCursor(50, 0);
  if (httpAttempted) display.print(httpStatus);
  else display.print("---");

  drawNtpDot(80, 0, ntpSynced);
  drawBufferBadge(104, 0, bufferCount);

  display.drawLine(0, 11, 128, 11, SH110X_WHITE);
}

// Spinner de 8 posiciones -- tabla fija en vez de trig, mas simple y sin depender
// de macros de Arduino.h (PI) que este .ino no incluye explicitamente.
void drawSpinner(int cx, int cy, int frame) {
  static const int8_t dx[8] = { 10, 7, 0, -7, -10, -7, 0, 7 };
  static const int8_t dy[8] = { 0, 7, 10, 7, 0, -7, -10, -7 };
  int i = frame % 8;
  display.drawCircle(cx, cy, 10, SH110X_WHITE);
  display.drawLine(cx, cy, cx + dx[i], cy + dy[i], SH110X_WHITE);
}

void showWifiConnectingScreen(int frame) {
  display.clearDisplay();
  drawStatusHeader(false, 0, false, false, 0, rtc_ntp_synced, rtcBufferCount);
  drawSpinner(64, 34, frame);
  display.setTextSize(1);
  display.setCursor(4, 50);
  display.print("Conectando WiFi...");
  display.display();
}

void showSendingScreen() {
  display.clearDisplay();
  drawStatusHeader(true, WiFi.RSSI(), false, false, 0, rtc_ntp_synced, rtcBufferCount);
  drawSpinner(64, 34, 0);
  display.setTextSize(1);
  display.setCursor(4, 50);
  display.print("Enviando datos...");
  display.display();
}

// Anillo que se expande alrededor del icono de nube en los primeros frames y
// desaparece en el ultimo -- el icono correcto (relleno/X) ya lo dibuja
// updateDisplay() en cada frame via drawCloudIcon, esto es puro adorno.
void playResultFlourish() {
  const int cx = 44, cy = 4;
  for (int i = 0; i < 3; i++) {
    updateDisplay();
    if (i < 2) {
      display.drawCircle(cx, cy, 6 + i * 3, SH110X_WHITE);
      display.display();
      delay(150);
    }
  }
}

// Apaga la pantalla (todos los pixeles en negro) -- en SH110X el consumo es
// proporcional a pixeles encendidos, asi que esto si ahorra energia real,
// a diferencia de simplemente dejar de dibujar frames nuevos.
void blankDisplay() {
  display.clearDisplay();
  display.display();
}

// ===== OLED =====
void updateDisplay() {
  display.clearDisplay();

  bool httpAttempted = (lastHttpStatus != 0);
  bool httpSuccess = (classifyHttpStatus(lastHttpStatus) == POST_SUCCESS);
  drawStatusHeader(wifiConnected, wifiConnected ? WiFi.RSSI() : 0, httpAttempted, httpSuccess,
                    lastHttpStatus, rtc_ntp_synced, rtcBufferCount);

  bool tempOk = (temp > -100.0);

  // pH
  display.setTextSize(1);
  display.setCursor(0, 17);
  display.print("pH");
  display.setTextSize(2);
  display.setCursor(40, 13);
  display.print(ph, 2);

  // TDS
  display.setTextSize(1);
  display.setCursor(0, 34);
  display.print("TDS");
  display.setTextSize(2);
  display.setCursor(40, 29);
  display.print((int)tds);
  display.setTextSize(1);
  display.setCursor(94, 34);
  display.print("ppm");

  // TEMP -- "--" si el DS18B20 esta desconectado (mismo criterio que streamDebugJSON)
  display.setTextSize(1);
  display.setCursor(0, 51);
  display.print("TEMP");
  display.setTextSize(2);
  display.setCursor(40, 45);
  if (tempOk) display.print(temp, 1);
  else display.print("--");
  display.setTextSize(1);
  display.setCursor(94, 51);
  if (tempOk) display.print("C");

  display.display();
}

// ===== CICLO (lectura + envio + pantalla), una vez por invocacion =====
void runCycle() {
  unsigned long wakeStart = millis();

  leerSensores();

  wifiConnected = conectarWiFi();

  if (wifiConnected && !rtc_ntp_synced) {
    rtc_ntp_synced = sincronizarNTP();
  }

  lastHttpStatus = 0;

  if (wifiConnected) {
    showSendingScreen();
    flushRtcBuffer();

    if (rtc_ntp_synced) {
      PendingReading current = currentReading();
      char json[256];
      buildReadingJSON(current, json, sizeof(json));
      lastHttpStatus = postReadingWithRetries(json);

      if (classifyHttpStatus(lastHttpStatus) == POST_TRANSIENT_FAIL) {
        rtcBufferPush(current);
      }

      playResultFlourish();  // termina dejando dibujado el dashboard final (updateDisplay())
#if !DISPLAY_ENABLED
      // modo bajo demanda: mantener el ultimo dato capturado en pantalla un
      // rato y despues apagarla -- solo se encendio para este envio
      delay(DISPLAY_ON_SECONDS * 1000UL);
      blankDisplay();
#endif
    } else {
      // wifi ok pero sin hora NTP confiable todavia (tipico del primer arranque
      // en frio, si el sync es lento o falla): no hay timestamp real que ponerle
      // a la lectura -- no se envia ni se encola nada, se reintenta fresco en el
      // proximo ciclo (mismo criterio que la rama sin wifi de abajo)
#if DISPLAY_ENABLED
      updateDisplay();
#endif
    }
  } else {
    lastHttpStatus = -1;  // sin WiFi, ni se intento
    if (rtc_ntp_synced) {
      rtcBufferPush(currentReading());
    }
    // si tampoco hay hora NTP confiable todavia, no se encola nada este ciclo
    // (no hay timestamp real que ponerle) -- se reintenta fresco en el proximo ciclo
    // modo bajo demanda (DISPLAY_ENABLED 0): la pantalla solo se enciende al
    // enviar datos, asi que en esta rama (sin wifi) se queda apagada
#if DISPLAY_ENABLED
    updateDisplay();
#endif
  }

  streamDebugJSON();

  WiFi.disconnect(true);
  WiFi.mode(WIFI_OFF);

  unsigned long awakeMs = millis() - wakeStart;
  long sleepMs = (long)TX_INTERVAL_SECONDS * 1000L - (long)awakeMs;
  if (sleepMs < 500) sleepMs = 500;  // piso minimo de sueno

#if KEEP_DISPLAY_ON_DEBUG
  delay(sleepMs);  // se queda despierto: la pantalla conserva el dashboard final
#else
  esp_sleep_enable_timer_wakeup((uint64_t)sleepMs * 1000ULL);
  esp_deep_sleep_start();
#endif
}

// ===== SETUP (init de hardware, una sola vez) =====
void setup() {
  Serial.begin(115200);
  Serial.print("{\"type\":\"boot\",\"reset_reason\":");
  Serial.print((int)esp_reset_reason());
  Serial.println("}");

  display.begin(0, true);
  display.clearDisplay();
  display.setTextColor(SH110X_WHITE);

  sensors.begin();

  runCycle();
}

void loop() {
#if KEEP_DISPLAY_ON_DEBUG
  runCycle();  // cada llamada termina en delay(); en produccion (deep sleep) nunca se alcanza
#endif
}
