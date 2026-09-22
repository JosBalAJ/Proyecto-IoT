#include "DHT.h"

#define MQ135_PIN 34
#define DHTPIN 4
#define DHTTYPE DHT22

DHT dht(DHTPIN, DHTTYPE);

unsigned long previousMillis = 0;
const long interval = 2000;

void setup() {
  Serial.begin(115200);
  Serial.println("=================================================");
  Serial.println("   Fase 1: Lectura de Datos Crudos (ESP32)      ");
  Serial.println("   Monitoreo Ambiental: MQ-135 + DHT22          ");
  Serial.println("=================================================");

  pinMode(MQ135_PIN, INPUT);
  dht.begin();

  Serial.println("Sensores inicializados...");
  delay(1000);
}

void loop(){
  unsigned long currentMillis = millis();
  if (currentMillis - previousMillis >= interval){
    previousMillis = currentMillis;

    int gasCrudo = analogRead(MQ135_PIN);
    float gasVoltaje = (gasCrudo * 3.3) / 4095;

    float humedad = dht.readHumidity();
    float temperatura = dht.readTemperature();

    if(isnan(humedad) || isnan(temperatura)){
      Serial.println("[ERROR] No se pudo leer el sensor DHT22");
      return;
    }

    Serial.println("-------------------------------------------------");
    Serial.print("Timestamp: ");
    Serial.print(currentMillis);
    Serial.println(" ms");

    Serial.print("[MQ-135] Valor ADC Crudo: ");
    Serial.print(rawGasADC);
    Serial.print(" | Voltaje Estimado: ");
    Serial.print(gasVoltage, 3);
    Serial.println(" V");

    Serial.print("[DHT22]  Temperatura: ");
    Serial.print(temperature, 1);
    Serial.print(" °C | Humedad Relativa: ");
    Serial.print(humidity, 1);
    Serial.println(" %");
  }
}