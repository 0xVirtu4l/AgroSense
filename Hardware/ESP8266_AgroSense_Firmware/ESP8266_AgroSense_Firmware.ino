#include <ESP8266WiFi.h>
#include <WiFiManager.h>
#include <ESP8266HTTPClient.h>
#include <DHT.h>
#include <ArduinoJson.h>  


#define DHTPIN D4        
#define DHTTYPE DHT22    
DHT dht(DHTPIN, DHTTYPE);


// fake data until we get a gps sensor
float latitude = 29.974318;
float longitude = 31.108278;

#define SOIL_MOISTURE_PIN A0  

#define LED_PIN D2  
#define LED_ON LOW
#define LED_OFF HIGH

String deviceID;

const char* serverURL = "https://virtu4l.pythonanywhere.com/api/sensordata";  

void setup() {
  Serial.begin(115200);

  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LED_OFF); 

  dht.begin();

  WiFiManager wifiManager;
  wifiManager.setTimeout(180);  // Set timeout to 3 minutes
  if (!wifiManager.autoConnect("AgroSenseAP")) {
    Serial.println("Failed to connect to Wi-Fi and hit timeout");
    ESP.restart();
    delay(1000);
  }

  Serial.println("Connected to Wi-Fi");

  deviceID = String(ESP.getChipId());
  Serial.print("Device ID: ");
  Serial.println(deviceID);
}

void loop() {
  // Read and send sensor data every 15 sec
  static unsigned long lastSendTime = 0;
  if (millis() - lastSendTime > 15000) {
    lastSendTime = millis();
    readAndSendSensorData();
  }
}

void readAndSendSensorData() {
  float temperature = dht.readTemperature();
  float humidity = dht.readHumidity();

  int soilMoistureRaw = analogRead(SOIL_MOISTURE_PIN);
  float soilMoisturePercent = map(soilMoistureRaw, 1023, 0, 0, 100);

  if (isnan(temperature) || isnan(humidity)) {
    Serial.println("Failed to read from DHT sensor!");
    return;
  }

  Serial.print("Temperature: ");
  Serial.print(temperature);
  Serial.print(" °C, Humidity: ");
  Serial.print(humidity);
  Serial.print(" %, Soil Moisture: ");
  Serial.print(soilMoisturePercent);
  Serial.println(" %");

  sendData(temperature, humidity, soilMoisturePercent ,latitude,longitude);
}

void sendData(float temperature, float humidity, float soilMoisture , float latitude , float longitude ) {
  if (WiFi.status() == WL_CONNECTED) {
    WiFiClientSecure client;
    client.setInsecure();  

    HTTPClient http;
    http.begin(client, serverURL);
    http.addHeader("Content-Type", "application/json");

    // Create JSON payload
    DynamicJsonDocument doc(256);
    doc["device_id"] = deviceID;
    doc["temperature"] = temperature;
    doc["humidity"] = humidity;
    doc["soil_moisture"] = soilMoisture;
    doc["latitude"] = latitude;
    doc["longitude"] = longitude;

    String payload;
    serializeJson(doc, payload);


    int httpResponseCode = http.POST(payload);

    if (httpResponseCode > 0) {
      String response = http.getString();
      Serial.print("HTTP Response code: ");
      Serial.println(httpResponseCode);
      Serial.println("Server response: " + response);

      processServerResponse(response);

    } else {
      Serial.print("Error on sending POST: ");
      Serial.println(httpResponseCode);
    }

    http.end();
  } else {
    Serial.println("Wi-Fi Disconnected");
  }
}

void processServerResponse(String response) {

  DynamicJsonDocument doc(512);
  DeserializationError error = deserializeJson(doc, response);

  if (error) {
    Serial.print(F("deserializeJson() failed: "));
    Serial.println(error.f_str());
    return;
  }

  const char* message = doc["message"];
  const char* command = doc["command"];

  Serial.println("Message from server: " + String(message));

  if (command && strlen(command) > 0 && String(command) != "null") {
    String cmd = String(command);
    Serial.print("Received command: ");
    Serial.println(cmd);

    if (cmd == "led_on") {
      digitalWrite(LED_PIN, LED_ON); 
      Serial.println("LED turned ON");
    } else if (cmd == "led_off") {
      digitalWrite(LED_PIN, LED_OFF); 
      Serial.println("LED turned OFF");
    }

  } else {
    Serial.println("No command received");
  }
}
