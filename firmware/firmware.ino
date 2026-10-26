#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include "DHT.h"

const char* ssid = "INFINITUMD6AE";
const char* password = "P4gli4cci";
const char* mqtt_server = "192.168.1.195";

const char* topic_telemetria = "sensores/aire/telemetria";
const char* topic_control = "dispositivos/esp32/control";

#define MQ135_PIN 34
#define DHTPIN 4
#define DHTTYPE DHT22
#define RELAY_PIN 26
#define BUZZER_PIN 25

#define LED_VERDE 33
#define LED_AMARILLO 32
#define LED_ROJO 27

DHT dht(DHTPIN, DHTTYPE);
WiFiClient espClient;
PubSubClient client(espClient);

unsigned long sequence_id = 0;
const int WINDOW_SIZE = 10;
int windowBuffer[WINDOW_SIZE];
int bufferIndex = 0;
long windowSum = 0;
unsigned long previousMillis = 0;
const long interval = 2000;

const int UMBRAL_GAS_CRITICO = 2500;
const float UMBRAL_TEMP_CRITICA = 30.0;

float applyMovingAverageFilter(int rawValue) {
  windowSum -= windowBuffer[bufferIndex];
  windowBuffer[bufferIndex] = rawValue;
  windowSum += rawValue;
  bufferIndex = (bufferIndex + 1) % WINDOW_SIZE;
  return (float)windowSum / WINDOW_SIZE;
}

void callback(char* topic, byte* payload, unsigned int length) {
  String message = "";
  for (unsigned int i = 0; i < length; i++) message += (char)payload[i];
  
  if (String(topic) == topic_control) {
    if (message.indexOf("VENT_ON") >= 0) digitalWrite(RELAY_PIN, HIGH);
    else if (message.indexOf("VENT_OFF") >= 0) digitalWrite(RELAY_PIN, LOW);
  }
}

void setup_wifi() {
  Serial.print("Conectando WiFi");
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) { 
    delay(500); 
    Serial.print("."); 
  }
  Serial.println("\nWiFi OK!");
}

void reconnect() {
  while (!client.connected()) {
    if (client.connect("ESP32_AIR_01")) {
      client.subscribe(topic_control);
    } else {
      delay(2000);
    }
  }
}

void actualizarLEDs(String estado) {
  digitalWrite(LED_VERDE, LOW);
  digitalWrite(LED_AMARILLO, LOW);
  digitalWrite(LED_ROJO, LOW);

  if (estado == "SAFE") digitalWrite(LED_VERDE, HIGH);
  else if (estado == "WARNING") digitalWrite(LED_AMARILLO, HIGH);
  else if (estado == "DANGER") digitalWrite(LED_ROJO, HIGH);
}

void setup() {
  Serial.begin(115200);
  pinMode(RELAY_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(LED_VERDE, OUTPUT);
  pinMode(LED_AMARILLO, OUTPUT);
  pinMode(LED_ROJO, OUTPUT);
  
  digitalWrite(RELAY_PIN, LOW);
  digitalWrite(BUZZER_PIN, LOW);
  actualizarLEDs("SAFE");

  dht.begin();
  for (int i = 0; i < WINDOW_SIZE; i++) windowBuffer[i] = 0;
  
  setup_wifi();
  client.setServer(mqtt_server, 1883);
  client.setCallback(callback);
}

void loop() {
  if (!client.connected()) reconnect();
  client.loop();

  unsigned long currentMillis = millis();
  if (currentMillis - previousMillis >= interval) {
    previousMillis = currentMillis;
    sequence_id++;

    int rawGasADC = analogRead(MQ135_PIN);
    float filteredGas = applyMovingAverageFilter(rawGasADC);
    float h = dht.readHumidity();
    float t = dht.readTemperature();
    if (isnan(h) || isnan(t)) { h = 0; t = 0; }

    String edge_state = "SAFE";
    
    if (filteredGas > UMBRAL_GAS_CRITICO || t > UMBRAL_TEMP_CRITICA) {
      edge_state = "DANGER";
      digitalWrite(RELAY_PIN, HIGH);
      tone(BUZZER_PIN, 1000, 500);
    } else if (filteredGas > (UMBRAL_GAS_CRITICO * 0.7)) {
      edge_state = "WARNING";
      digitalWrite(RELAY_PIN, HIGH);
    } else {
      digitalWrite(RELAY_PIN, LOW);
    }
    
    actualizarLEDs(edge_state);

    StaticJsonDocument<256> doc;
    doc["node_id"] = "ESP32_AIR_01";
    doc["gas_raw"] = rawGasADC;
    doc["gas_filtered"] = filteredGas;
    doc["temperature"] = t;
    doc["humidity"] = h;
    doc["risk_state_edge"] = edge_state;
    doc["sequence_id"] = sequence_id;
    doc["timestamp_ms"] = currentMillis;

    char buffer[256];
    serializeJson(doc, buffer);
    client.publish(topic_telemetria, buffer);
  }
}