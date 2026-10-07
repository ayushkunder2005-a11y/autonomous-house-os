# Architecture Document 04: API & WebSocket Streaming Contract

> **Component:** Autonomous House OS — Gateway & Interface Contracts  
> **Server Platform:** FastAPI 0.110+ (Uvicorn / ASGI)  
> **Contract References:** [`contracts/openapi.json`](file:///d:/house%20control/contracts/openapi.json), [`contracts/schemas_pydantic.py`](file:///d:/house%20control/contracts/schemas_pydantic.py)  
> **Target Implementer:** CODEX  

---

## 1. Gateway Architecture & Security Model

The FastAPI gateway serves as the single ingress point for Web, Mobile, and Voice clients.

```
  CLIENT (Browser / Mobile / Script)
       │
       │ HTTPS / WSS
       ▼
  +─────────────────────────────────────────────────────────+
  |              FASTAPI GATEWAY & ASGI WORKER              |
  |                                                         |
  |  [Auth Middleware: JWT Bearer + Role Scope + Argon2]    |
  |  [Rate Limiter: Token Bucket Redis, 120 req/min/IP]     |
  |                                                         |
  |  +──────────────────────+    +───────────────────────+  |
  |  |  REST Endpoints      |    |  WebSocket Delta Hub  |  |
  |  |  (OpenAPI 3.1)       |    |  (Multiplexed Streams)|  |
  |  +──────────┬───────────+    +───────────┬───────────+  |
  +─────────────┼────────────────────────────┼──────────────+
                │                            │
                ▼                            ▼
  +─────────────────────────────────────────────────────────+
  |     CORE LOGIC: DIGITAL TWIN, BRAIN, CONFLICT ENGINE    |
  +─────────────────────────────────────────────────────────+
```

### 1.1 Authentication & Authorization Matrix
1. **JWT Access Token:** Signed using ECDSA (`ES256`) or HMAC (`HS256`), TTL = 15 minutes.
2. **Refresh Token:** HttpOnly secure cookie, stored in Redis with revocation list, TTL = 30 days.
3. **Security Mode Elevation:** Modifying system modes (`AWAY`, `VACATION`, `EMERGENCY_RESET`) requires an elevated header: `X-House-Security-PIN`.
4. **Role Hierarchy:**
   - `owner`: Full administrative control, user creation, factory reset, experiment approval.
   - `admin`: Automation authoring, schedule adjustment, preference tuning.
   - `member`: Standard room control, scene triggering, conversational queries.
   - `guest`: Temporary spatial access (bounded by room or time window).
   - `service`: Maintenance role with read-only diagnostics and sensor calibration flags.

---

## 2. Core RESTful Endpoints Specification

### 2.1 Digital Twin State
- **`GET /api/v1/twin/state`**
  - *Description:* Retrieves complete in-memory snapshot of the living house (all floors, rooms, devices, sensors, and environmental averages).
  - *Response:* `200 OK` $\to$ `DigitalTwinSnapshotResponse` (cached in Redis, latency $< 15\text{ms}$).
- **`GET /api/v1/twin/floors`**
  - *Response:* `200 OK` $\to$ List of floor structures with SVG layouts and room mappings.
- **`GET /api/v1/twin/rooms/{room_id}`**
  - *Response:* `200 OK` $\to$ Deep spatial view of a single room, aggregated metrics, assigned devices, and active occupants.

### 2.2 Actuator Command Dispatch
- **`POST /api/v1/devices/{device_id}/command`**
  - *Description:* Proposes an actuator change. Does **not** blindly trigger hardware; immediately passes through the Priority Conflict Engine.
  - *Request Body:*
    ```json
    {
      "endpoint": "relay_light",
      "action": "SET_STATE",
      "parameters": { "power": "ON", "brightness_pct": 80 },
      "priority_tier": 3,
      "reason": "Manual user click on Web Dashboard"
    }
    ```
  - *Response:*
    - `202 Accepted`: Command passed conflict matrix and was dispatched to MQTT. Returns `command_id` and tracker URL.
    - `409 Conflict`: Command rejected by higher-priority rule or safety interlock (e.g., trying to turn on heater during thermal safety lockdown). Returns structured conflict explanation.

### 2.3 House Brain, Natural Language & Simulation
- **`POST /api/v1/brain/intent`**
  - *Description:* Analyzes natural language input (e.g., *"Make the living room comfortable for movie night"*), parses intent, extracts entities, and generates an `IntentPlan` with projected What-If simulation results.
  - *Request Body:*
    ```json
    {
      "query_text": "Prepare the house for sleeping",
      "dry_run": false
    }
    ```
  - *Response `200 OK`:*
    ```json
    {
      "intent_id": "int_4810a91-449",
      "parsed_intent": "SET_SECURITY_AND_SLEEP_COMFORT",
      "confidence": 0.98,
      "requires_confirmation": false,
      "proposed_actions": [
        {"target_device": "esp32_all_locks", "action": "LOCK_ALL", "tier": 1},
        {"target_device": "esp32_lr_lights", "action": "FADE_OFF", "tier": 4},
        {"target_device": "esp32_mbr_hvac", "action": "SET_TEMP", "parameters": {"temp_c": 21.0}, "tier": 4}
      ],
      "simulation_impact": {
        "projected_power_watts_delta": -420.0,
        "conflict_detected": false
      },
      "explanation": "Locked perimeter, dimmed active living areas, and set bedroom climate to user preferred sleep temperature (21°C)."
    }
    ```
- **`POST /api/v1/brain/simulate`**
  - *Description:* Runs a What-If simulation against an in-memory clone of the Digital Twin.
  - *Request Body:*
    ```json
    {
      "scenario_name": "Hot Day All AC Cool",
      "hypothetical_actions": [
        {"device_id": "esp32_lr_hvac_01", "parameters": {"mode": "COOL", "temp_c": 20.0}},
        {"device_id": "esp32_br1_hvac", "parameters": {"mode": "COOL", "temp_c": 20.0}},
        {"device_id": "esp32_br2_hvac", "parameters": {"mode": "COOL", "temp_c": 20.0}}
      ],
      "duration_hours": 4
    }
    ```
  - *Response `200 OK`:* Returns estimated peak load (kW), estimated electricity cost, thermal equilibrium curves, and warning flags.

### 2.4 Energy & Water Intelligence
- **`GET /api/v1/energy/live`**
  - *Response:* Current real-time load (Watts), phase balance (L1/L2/L3), solar generation (if active), battery state, and top 5 power-consuming appliances.
- **`GET /api/v1/water/live`**
  - *Response:* Main storage tank level (liters & %), overhead tank level, pump operating state, instantaneous flow rate (L/min), and acoustic leak detection index.
- **`POST /api/v1/water/pump/control`**
  - *Description:* Manual pump control. Passes through dry-run and high-tank cutoff interlocks before triggering.

### 2.5 Security Modes & Emergency Workflows
- **`GET /api/v1/security/mode`**
  - *Response:* Active mode (`HOME`, `SLEEP`, `AWAY`, `VACATION`, `EMERGENCY`).
- **`POST /api/v1/security/mode/set`**
  - *Request Body:* `{"mode": "AWAY", "pin_code": "1234"}`
- **`POST /api/v1/emergency/trigger`**
  - *Description:* Panic trip. Immediately enters Level 0 emergency cutoff state.
- **`POST /api/v1/emergency/reset`**
  - *Description:* Clears emergency state after on-site physical inspection. Requires administrative PIN.

### 2.6 House Health & Black Box Time-Machine
- **`GET /api/v1/health/score`**
  - *Response:* Real-time composite score (0-100) and 9 sub-scores: Safety, Security, Energy, Water, Devices, Sensors, Network, Environment, Maintenance.
- **`GET /api/v1/blackbox/query`**
  - *Query Params:* `start_time`, `end_time`, `entity_id`, `severity`, `limit`
  - *Description:* Returns forensic event timeline from `house_blackbox` hypertable.

---

## 3. High-Throughput WebSocket Streaming Protocol

### 3.1 Endpoint & Lifecycle
- **URL:** `ws://<edge-server-ip>:8000/api/v1/ws/live-stream`
- **Authentication:** Initiated via ticket or token query parameter: `?token=<jwt_token>`.
- **Heartbeat:** Server emits `{"type": "PING", "ts": 1772968800000}` every 15s. Client must respond with `{"type": "PONG"}` within 5s or the socket is pruned.

### 3.2 Client Subscription Frame
Upon connecting, the client subscribes to granular telemetry topics:
```json
{
  "action": "SUBSCRIBE",
  "channels": [
    "twin:rooms:living_room",
    "energy:live",
    "water:tank",
    "security:status",
    "emergency:alerts"
  ]
}
```

### 3.3 Server Delta Broadcast Frame
Instead of dumping the entire digital twin on every sensor reading, the server emits targeted differential deltas:
```json
{
  "channel": "twin:rooms:living_room",
  "event": "STATE_DELTA",
  "timestamp": 1772968800342,
  "payload": {
    "device_id": "esp32_lr_hvac_01",
    "field": "current_temp_c",
    "old_val": 24.5,
    "new_val": 24.3,
    "trigger_reason": "TELEMETRY_REFRESH"
  }
}
```

### 3.4 Emergency Priority Frame
Sent across all active WebSocket channels with zero queuing delay:
```json
{
  "channel": "emergency:alerts",
  "event": "EMERGENCY_CUTOFF_ACTIVE",
  "timestamp": 1772968800010,
  "payload": {
    "emergency_id": "emg_99a8b1",
    "hazard_type": "WATER_BURST_FLOOD",
    "location": "Utility Room",
    "action_taken": "MAIN_SOLENOID_VALVE_ISOLATED"
  }
}
```

---

## 4. CODEX Implementation Directives

1. Implement all routes inside modular routers under `backend/api/v1/` (`twin.py`, `devices.py`, `brain.py`, `energy.py`, `water.py`, `security.py`, `health.py`, `ws.py`).
2. Implement dependency injection for current authenticated user and database session (`get_db`, `get_current_user`).
3. Maintain WebSocket connection registry inside `backend/ws/manager.py` using non-blocking asyncio sets.
4. Auto-generate OpenAPI docs accessible at `/docs` and `/openapi.json`.
