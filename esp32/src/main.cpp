#include <Arduino.h>
#include <ArduinoJson.h>
#include <MQTT.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <esp_system.h>
#include <secrets.h>

namespace {
constexpr uint8_t RELAY_PIN = 2;
constexpr TickType_t LOOP_TICKS = pdMS_TO_TICKS(10);
constexpr uint32_t DEADMAN_MS = 15000;
constexpr uint32_t HEALTH_MS = 10000;

struct HardwareCommand {
  char commandId[64];
  char endpoint[48];
  char action[48];
  char parameters[256];
};
struct HardwareResult {
  char commandId[64];
  char endpoint[48];
  bool applied;
  uint32_t executionMs;
  bool relayOn;
};

WiFiClientSecure secureClient;
MQTTClient mqtt(1024);
QueueHandle_t commandQueue;
QueueHandle_t resultQueue;
portMUX_TYPE stateMux = portMUX_INITIALIZER_UNLOCKED;
volatile uint32_t lastServerPacketMs = 0;
volatile bool relayOn = false;

String commandTopic() { return "house/" HOUSE_ID "/command/" DEVICE_ID "/+"; }
String stateTopic(const char *endpoint) {
  return "house/" HOUSE_ID "/state/" DEVICE_ID "/" + String(endpoint);
}
String ackTopic(const char *commandId) {
  return "house/" HOUSE_ID "/ack/" DEVICE_ID "/" + String(commandId);
}
String heartbeatTopic() { return "house/" HOUSE_ID "/heartbeat/" DEVICE_ID; }
String emergencyTopic() { return "house/" HOUSE_ID "/emergency/broadcast"; }

bool publishDocument(const String &topic, JsonDocument &document, int qos, bool retained = false) {
  char payload[768];
  const size_t length = serializeJson(document, payload, sizeof(payload));
  return length && mqtt.publish(topic, payload, retained, qos);
}

void onMqttMessage(String &topic, String &payload) {
  portENTER_CRITICAL(&stateMux);
  lastServerPacketMs = millis();
  portEXIT_CRITICAL(&stateMux);
  JsonDocument document;
  if (deserializeJson(document, payload) != DeserializationError::Ok) return;
  HardwareCommand command{};
  if (topic == emergencyTopic()) {
    strlcpy(command.commandId, document["emergency_id"] | "emergency", sizeof(command.commandId));
    strlcpy(command.endpoint, "safety", sizeof(command.endpoint));
    strlcpy(command.action, "FORCE_OFF", sizeof(command.action));
    strlcpy(command.parameters, "{}", sizeof(command.parameters));
    xQueueSend(commandQueue, &command, 0);
    return;
  }
  strlcpy(command.commandId, document["command_id"] | "", sizeof(command.commandId));
  strlcpy(command.endpoint, document["endpoint"] | "default", sizeof(command.endpoint));
  strlcpy(command.action, document["action"] | "", sizeof(command.action));
  serializeJson(document["parameters"], command.parameters, sizeof(command.parameters));
  if (command.commandId[0]) xQueueSend(commandQueue, &command, 0);
}

void publishResult(const HardwareResult &result) {
  JsonDocument ack;
  ack["command_id"] = result.commandId;
  ack["device_id"] = DEVICE_ID;
  ack["endpoint"] = result.endpoint;
  ack["status"] = result.applied ? "APPLIED" : "REJECTED_LOCAL_FAULT";
  ack["execution_duration_ms"] = result.executionMs;
  ack["current_state"]["power"] = result.relayOn ? "ON" : "OFF";
  ack["error_code"] = result.applied ? nullptr : "UNSUPPORTED_ACTION";
  publishDocument(ackTopic(result.commandId), ack, 2);

  if (result.applied) {
    JsonDocument state;
    state["device_id"] = DEVICE_ID;
    state["endpoint"] = result.endpoint;
    state["timestamp"] = static_cast<uint64_t>(millis());
    state["state"]["power"] = result.relayOn ? "ON" : "OFF";
    publishDocument(stateTopic(result.endpoint), state, 1, true);
  }
}

void publishHeartbeat() {
  JsonDocument health;
  health["device_id"] = DEVICE_ID;
  health["status"] = "ONLINE";
  health["ip_address"] = WiFi.localIP().toString();
  health["rssi_dbm"] = WiFi.RSSI();
  health["uptime_seconds"] = millis() / 1000;
  health["free_heap_bytes"] = ESP.getFreeHeap();
  health["firmware_version"] = "1.0.0";
  publishDocument(heartbeatTopic(), health, 1, true);
}

void connectNetwork() {
  static uint32_t nextAttempt = 0;
  static uint32_t backoff = 1000;
  if (millis() < nextAttempt) return;
  if (WiFi.status() != WL_CONNECTED) {
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    nextAttempt = millis() + backoff + esp_random() % 400;
    backoff = min<uint32_t>(backoff * 2, 60000U);
    return;
  }
  if (!mqtt.connected()) {
    if (mqtt.connect("house-node-" DEVICE_ID, MQTT_USERNAME, MQTT_PASSWORD)) {
      mqtt.subscribe(commandTopic(), 2);
      mqtt.subscribe(heartbeatTopic(), 1);
      mqtt.subscribe(emergencyTopic(), 2);
      backoff = 1000;
      publishHeartbeat();
    } else {
      nextAttempt = millis() + backoff + esp_random() % 400;
      backoff = min<uint32_t>(backoff * 2, 60000U);
    }
  }
}

void networkTask(void *) {
  TickType_t wake = xTaskGetTickCount();
  uint32_t lastHealth = 0;
  for (;;) {
    connectNetwork();
    if (mqtt.connected()) {
      mqtt.loop();
      HardwareResult result;
      while (xQueueReceive(resultQueue, &result, 0) == pdTRUE) publishResult(result);
      if (millis() - lastHealth >= HEALTH_MS) {
        lastHealth = millis();
        publishHeartbeat();
      }
    }
    vTaskDelayUntil(&wake, LOOP_TICKS);
  }
}

void enterSafeFallbackState() {
  // This reference node controls a high-power relay, so network loss forces OFF.
  // Lighting builds should replace this with hold-last-state plus a local wall switch.
  relayOn = false;
  digitalWrite(RELAY_PIN, LOW);
}

void controlTask(void *) {
  TickType_t wake = xTaskGetTickCount();
  bool deadmanActive = false;
  for (;;) {
    HardwareCommand command;
    if (xQueueReceive(commandQueue, &command, 0) == pdTRUE) {
      const uint32_t started = millis();
      bool applied = true;
      if (strcasecmp(command.action, "TURN_ON") == 0) relayOn = true;
      else if (strcasecmp(command.action, "TURN_OFF") == 0 ||
               strcasecmp(command.action, "FORCE_OFF") == 0) relayOn = false;
      else {
        JsonDocument parameters;
        deserializeJson(parameters, command.parameters);
        if (strcasecmp(command.action, "SET_STATE") == 0 && parameters["power"].is<const char *>())
          relayOn = strcasecmp(parameters["power"], "ON") == 0;
        else applied = false;
      }
      if (applied) digitalWrite(RELAY_PIN, relayOn ? HIGH : LOW);
      HardwareResult result{};
      strlcpy(result.commandId, command.commandId, sizeof(result.commandId));
      strlcpy(result.endpoint, command.endpoint, sizeof(result.endpoint));
      result.applied = applied;
      result.executionMs = millis() - started;
      result.relayOn = relayOn;
      xQueueSend(resultQueue, &result, 0);
      deadmanActive = false;
    }
    uint32_t lastPacket;
    portENTER_CRITICAL(&stateMux);
    lastPacket = lastServerPacketMs;
    portEXIT_CRITICAL(&stateMux);
    if (lastPacket && millis() - lastPacket > DEADMAN_MS && !deadmanActive) {
      enterSafeFallbackState();
      deadmanActive = true;
    }
    vTaskDelayUntil(&wake, LOOP_TICKS);
  }
}
}  // namespace

void setup() {
  Serial.begin(115200);
  pinMode(RELAY_PIN, OUTPUT);
  digitalWrite(RELAY_PIN, LOW);
  commandQueue = xQueueCreate(8, sizeof(HardwareCommand));
  resultQueue = xQueueCreate(8, sizeof(HardwareResult));
  secureClient.setCACert(MQTT_CA_CERT);
  mqtt.begin(MQTT_HOST, MQTT_PORT, secureClient);
  mqtt.onMessage(onMqttMessage);
  WiFi.mode(WIFI_STA);
  xTaskCreatePinnedToCore(networkTask, "network", 8192, nullptr, 2, nullptr, 0);
  xTaskCreatePinnedToCore(controlTask, "control", 6144, nullptr, 3, nullptr, 1);
}

void loop() { vTaskDelete(nullptr); }
