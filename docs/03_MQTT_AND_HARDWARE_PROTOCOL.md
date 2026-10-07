# Architecture Document 03: MQTT & Hardware Communication Protocol

> **Component:** Autonomous House OS — Device Transport & Microcontroller Protocol  
> **Broker Target:** Eclipse Mosquitto 2.0+ (TLS 1.3)  
> **Client Target:** ESP32 Microcontrollers (FreeRTOS / C++) & FastAPI `aiomqtt`  
> **Target Implementer:** CODEX  
> **Source Topic Registry:** [`contracts/mqtt_topics.json`](file:///d:/house%20control/contracts/mqtt_topics.json)  

---

## 1. Network & Broker Topology

### 1.1 Broker Configuration (`mosquitto.conf`)
- **Port 1883:** Plaintext MQTT **strictly restricted** to internal isolated VLAN `192.168.107.0/24`. No external or WAN binding.
- **Port 8883:** Mutual TLS (mTLS) with TLS 1.3 cipher suites (`TLS_AES_256_GCM_SHA384`, `TLS_CHACHA20_POLY1305_SHA256`).
- **Persistence:** Enabled (`autosave_interval 1800`, `persistence_file mosquitto.db`).
- **Max Inflight Messages:** 50.
- **Max Queued Messages:** 10,000.
- **Message Expiry Interval:** 300 seconds (ensures stale commands are discarded if a node stays offline).

### 1.2 Access Control List (ACL) Strategy
Every device authenticates via client certificate or provisioned device credentials:
- **FastAPI Core Worker:** Superuser access to `house/#`.
- **ESP32 Edge Nodes:** Constrained publish/subscribe permissions:
  - Can publish ONLY to: `house/{house_id}/telemetry/...`, `house/{house_id}/state/...`, `house/{house_id}/ack/...`, `house/{house_id}/heartbeat/{client_id}`.
  - Can subscribe ONLY to: `house/{house_id}/command/{client_id}/#`, `house/{house_id}/emergency/#`, `house/{house_id}/ota/{client_id}`.

---

## 2. Topic Taxonomy & Hierarchy

All topics strictly observe the structured canonical namespace:

```
house/{house_id}/{channel}/{context_path}
```

```
                          house/{house_id}
                                 │
     ┌──────────────┬────────────┼────────────┬─────────────┬─────────────┐
     ▼              ▼            ▼            ▼             ▼             ▼
 telemetry/      command/      state/        ack/       heartbeat/    emergency/
     │              │            │            │             │             │
{floor}/{room}/ {device_id}/ {device_id}/ {device_id}/ {device_id}   broadcast
{device_id}/    {endpoint}   {endpoint}   {command_id}
{sensor_id}
```

### 2.1 Complete Topic Catalog

| Purpose | Topic Pattern | Direction | QoS | Retain |
| :--- | :--- | :--- | :--- | :--- |
| **Sensor Telemetry** | `house/{house_id}/telemetry/{floor}/{room}/{device_id}/{sensor_id}` | ESP32 $\to$ Broker | 1 | `false` |
| **Device Command** | `house/{house_id}/command/{device_id}/{endpoint}` | Core $\to$ ESP32 | 2 | `false` |
| **Device State Feedback** | `house/{house_id}/state/{device_id}/{endpoint}` | ESP32 $\to$ Core | 1 | `true` |
| **Command Acknowledgment** | `house/{house_id}/ack/{device_id}/{command_id}` | ESP32 $\to$ Core | 2 | `false` |
| **LWT / Heartbeat** | `house/{house_id}/heartbeat/{device_id}` | ESP32 $\leftrightarrow$ Core | 1 | `true` |
| **Emergency Broadcast** | `house/{house_id}/emergency/broadcast` | Core $\to$ All ESP32s | 2 | `false` |
| **Firmware OTA Notification**| `house/{house_id}/ota/{device_id}` | Core $\to$ ESP32 | 1 | `false` |

---

## 3. Strict Payload JSON Schemas

### 3.1 Sensor Telemetry Payload
Published periodically or on meaningful delta trigger:
```json
{
  "timestamp": 1772968800123,
  "sensor_id": "temp_lr_bme280",
  "device_id": "esp32_lr_hvac_01",
  "metric_type": "temperature",
  "value": 24.35,
  "unit": "C",
  "read_seq": 48102,
  "status": "VALID",
  "battery_pct": null
}
```

### 3.2 Device Command Dispatch Payload
Sent from FastAPI Priority Conflict Engine to ESP32:
```json
{
  "command_id": "cmd_8a2d10ef-1d54-4638-b769-cfad479f64bf",
  "timestamp": 1772968800200,
  "device_id": "esp32_lr_hvac_01",
  "endpoint": "climate",
  "action": "SET_PARAMETERS",
  "parameters": {
    "power": "ON",
    "mode": "COOL",
    "setpoint_c": 23.5,
    "fan_speed": 3
  },
  "priority_tier": 4,
  "timeout_ms": 2500
}
```

### 3.3 Command Acknowledgment (ACK) Payload
Returned by ESP32 immediately upon physical GPIO execution:
```json
{
  "command_id": "cmd_8a2d10ef-1d54-4638-b769-cfad479f64bf",
  "device_id": "esp32_lr_hvac_01",
  "endpoint": "climate",
  "status": "APPLIED",
  "execution_duration_ms": 38.2,
  "current_state": {
    "power": "ON",
    "mode": "COOL",
    "setpoint_c": 23.5,
    "fan_speed": 3
  },
  "error_code": null
}
```

### 3.4 Last Will & Testament (LWT) and Heartbeat
Registered with Mosquitto on initial connection:
```json
{
  "device_id": "esp32_lr_hvac_01",
  "status": "ONLINE",
  "ip_address": "192.168.107.45",
  "rssi_dbm": -58,
  "uptime_seconds": 184902,
  "free_heap_bytes": 198420,
  "firmware_version": "1.4.2"
}
```
*LWT Payload:* When connection drops ungracefully, broker publishes with retained flag:
```json
{
  "device_id": "esp32_lr_hvac_01",
  "status": "OFFLINE_UNEXPECTED",
  "timestamp": 1772968805000
}
```

### 3.5 Emergency Broadcast Payload
Pushed to `house/{house_id}/emergency/broadcast` with QoS 2:
```json
{
  "emergency_id": "emg_739ab1e0-3942-4f01",
  "timestamp": 1772968800000,
  "severity": "CRITICAL_LEVEL_0",
  "hazard_type": "GAS_LEAK_CONFIRMED",
  "source_room": "Kitchen",
  "actions_required": [
    {"target_device_type": "gas_solenoid", "command": "FORCE_SHUTOFF"},
    {"target_device_type": "exhaust_fan", "command": "FORCE_MAX_EXHAUST"},
    {"target_device_type": "all_relays", "command": "PREVENT_SPARKING_SWITCH"}
  ]
}
```

---

## 4. ESP32 Microcontroller Architecture & Firmware Protocol

### 4.1 FreeRTOS Dual-Core Task Allocation
CODEX must implement ESP32 firmware adhering to strict task separation:

- **Core 0 (Networking & Protocol Task):**
  - Wi-Fi station event handler with exponential reconnect backoff.
  - MQTT loop (subscribe/publish, keepalive pings every 10s).
  - Dynamic JSON serialization using `ArduinoJson` (or `cJSON`).
  - OTA update agent.

- **Core 1 (Real-Time Control & Safety Watchdog Task):**
  - High-frequency I2C / SPI / ADC sensor sampling (BME280, PIR, CT clamps, Flow meters).
  - Software hysteresis and debounce filter (minimum 50ms button debounce).
  - Actuator relay switching with zero-crossing triac or interlock guards.
  - **Hardware Deadman Safety Watchdog:** A local timer resetting on every received MQTT packet. If no packet is received for $> 15.0\text{ s}$, Core 1 triggers `EnterSafeFallbackState()`.

```
  ESP32 DUAL CORE ARCHITECTURE
  ┌─────────────────────────────────────┐  ┌─────────────────────────────────────┐
  │         CORE 0: PROTOCOL            │  │          CORE 1: REAL-TIME          │
  │                                     │  │                                     │
  │  [Wi-Fi / 802.11 Stack]             │  │  [ADC / I2C / SPI Sensor Polling]   │
  │               │                     │  │               │                     │
  │  [MQTT Client Loop (aiomqtt/pubsub)]│  │  [Hysteresis & Debounce Filters]    │
  │               │                     │  │               │                     │
  │  [JSON Serializer / Parser]         │  │  [Relay / Actuator GPIO Drivers]    │
  │               │                     │  │               │                     │
  │  [OTA Firmware Manager]             │  │  [15s Hardware Deadman Watchdog]   │
  └───────────────────┬─────────────────┘  └───────────────────┬─────────────────┘
                      │                                        │
                      └───────────── FreeRTOS Queue ───────────┘
                                  (Thread-Safe FIFO)
```

### 4.2 Deadman Safe Fallback States

When disconnected from the central server, the ESP32 must not freeze or leave high-power actuators floating:

| Device Category | Normal Offline Fallback Action |
| :--- | :--- |
| **Water Booster Pump** | `FORCE_OFF` (Prevents dry run and high-pressure burst). |
| **Gas Solenoid Valve** | `DE-ENERGIZE / CLOSE` (Normally-closed safety spring). |
| **Water Main Solenoid**| Hold last state, close if pressure drops rapidly. |
| **HVAC Compressor** | `FORCE_OFF` with 3-minute anti-cycling lockout. |
| **Lighting Relays** | Maintain last physical state; allow local wall switch toggle. |
| **Motorized Windows** | Hold current mechanical position; lock manual motors. |

### 4.3 Network Reconnection Algorithm (Exponential Backoff with Jitter)
```
T_retry = min(T_max, T_base * 2^attempt) + uniform_random(-0.2, 0.2) * T_base
Where:
T_base = 1.0 second
T_max = 60.0 seconds
```
Prevents "thundering herd" reconnection storms against Mosquitto when power is restored to the house.

---

## 5. CODEX Implementation Directives

1. Implement firmware drivers with **strict non-blocking I/O** (zero `delay()` calls; rely solely on FreeRTOS `vTaskDelayUntil`).
2. ESP32 devices must store Wi-Fi and MQTT credentials in encrypted NVS (Non-Volatile Storage).
3. The central backend MQTT ingestion worker in `backend/transport/mqtt_client.py` must maintain a persistent connection pool using `aiomqtt` and push events directly onto the Redis stream `stream:telemetry`.
