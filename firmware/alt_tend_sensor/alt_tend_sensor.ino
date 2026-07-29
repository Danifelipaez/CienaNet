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
// Let's Encrypt ISRG Root X1 -- publico, no secreto. Necesario para que
// WiFiClientSecure valide el certificado del backend en produccion
// (docs/IOT_SENSORES.md prohibe setInsecure() en produccion).
static const char ISRG_ROOT_X1_PEM[] = R"EOF(
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
  while (WiFi.status() != WL_CONNECTED && millis() - start < WIFI_CONNECT_TIMEOUT_MS) {
    delay(100);
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
  client.setCACert(ISRG_ROOT_X1_PEM);
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
  if (statusCode == 201) return POST_SUCCESS;
  if (statusCode == 403 || statusCode == 422) return POST_PERMANENT_FAIL;  // key mala / fuera de rango: reintentar es inutil
  return POST_TRANSIENT_FAIL;  // timeout, sin respuesta, 5xx
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
    int status = postReading(json);
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

// ===== OLED =====
void updateDisplay() {
  display.clearDisplay();

  display.setTextSize(1);
  display.setCursor(0, 0);
  display.print("pH");
  display.setTextSize(2);
  display.setCursor(0, 9);
  display.print(ph, 2);

  display.setTextSize(1);
  display.setCursor(70, 0);
  display.print("mV");
  display.setTextSize(2);
  display.setCursor(70, 9);
  display.print((int)mV_PH);

  display.drawLine(0, 26, 128, 26, SH110X_WHITE);

  display.setTextSize(1);
  display.setCursor(0, 29);
  display.print("TDS:");
  display.setTextSize(2);
  display.setCursor(35, 27);
  display.print((int)tds);

  display.setTextSize(1);
  display.setCursor(0, 45);
  display.print("Tmp:");
  display.setTextSize(2);
  display.setCursor(20, 43);
  display.print(temp, 1);

  display.drawLine(0, 53, 128, 53, SH110X_WHITE);
  display.setTextSize(1);
  display.setCursor(0, 56);
  display.print(wifiConnected ? "WiFi OK" : "WiFi --");
  display.setCursor(70, 56);
  display.print("H"); display.print(lastHttpStatus);
  display.print(" B"); display.print(rtcBufferCount);

  display.display();
}

// ===== SETUP (todo el ciclo pasa aqui, una vez por despertar) =====
void setup() {
  unsigned long wakeStart = millis();

  Serial.begin(115200);
  Serial.print("{\"type\":\"boot\",\"reset_reason\":");
  Serial.print((int)esp_reset_reason());
  Serial.println("}");

  display.begin(0, true);
  display.clearDisplay();
  display.setTextColor(SH110X_WHITE);

  sensors.begin();

  leerSensores();

  wifiConnected = conectarWiFi();

  if (wifiConnected && !rtc_ntp_synced) {
    rtc_ntp_synced = sincronizarNTP();
  }

  lastHttpStatus = 0;

  if (wifiConnected) {
    flushRtcBuffer();

    PendingReading current = currentReading();
    char json[256];
    buildReadingJSON(current, json, sizeof(json));
    lastHttpStatus = postReading(json);

    if (classifyHttpStatus(lastHttpStatus) == POST_TRANSIENT_FAIL && rtc_ntp_synced) {
      rtcBufferPush(current);
    }
  } else {
    lastHttpStatus = -1;  // sin WiFi, ni se intento
    if (rtc_ntp_synced) {
      rtcBufferPush(currentReading());
    }
    // si tampoco hay hora NTP confiable todavia, no se encola nada este ciclo
    // (no hay timestamp real que ponerle) -- se reintenta fresco en el proximo ciclo
  }

  updateDisplay();
  streamDebugJSON();

  WiFi.disconnect(true);
  WiFi.mode(WIFI_OFF);

  unsigned long awakeMs = millis() - wakeStart;
  long sleepMs = (long)TX_INTERVAL_SECONDS * 1000L - (long)awakeMs;
  if (sleepMs < 500) sleepMs = 500;  // piso minimo de sueno
  esp_sleep_enable_timer_wakeup((uint64_t)sleepMs * 1000ULL);
  esp_deep_sleep_start();
}

void loop() {
  // nunca se alcanza: esp_deep_sleep_start() no retorna
}
