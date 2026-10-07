# Architecture Document 07: Safety, Emergency & Self-Recovery Subsystems

> **Component:** Autonomous House OS — Life Safety, Security Modes & Fault Recovery  
> **Subsystem Target:** `backend/safety/`, `backend/security/`, `backend/recovery/`  
> **Target Implementer:** CODEX  

---

## 1. Safety Paradigm: Determinism Over Probabilism

The cardinal rule of the Autonomous House OS is:

> **CRITICAL INVARIANT:**  
> AI and machine learning models are **strictly advisory and analytical**.  
> Under zero circumstances may an AI model, LLM, or probabilistic heuristic have sole authority over life-safety trips, emergency shutdowns, or security disarming.  
> All emergency actions execute through hardcoded, deterministic finite state machines with hardware-level fail-safes.

```
       HAZARD SENSORS (Smoke, Gas, Flood, Pressure, Thermal)
                                 │
                                 ▼
       +─────────────────────────────────────────────────────────+
       |         DETERMINISTIC SAFETY RUNTIME (< 10ms)           |
       |               (Zero-AI / Hard Failsafe)                 |
       +─────────────────────────┬───────────────────────────────+
                                 │
                ┌────────────────┴────────────────┐
                ▼                                 ▼
      [CRITICAL LEVEL 0 TRIP]            [DATABASE AUDIT & NOTIF]
      - Hardware relay cutoffs           - High-priority SMS / Push
      - Gas solenoid spring-close        - Black Box recording
      - Water main valve seal            - Siren / strobe activation
      - HVAC smoke shutdown              
```

---

## 2. Emergency Workflows & Execution Matrix

CODEX must implement deterministic safety handlers for the following hazards:

### 2.1 Gas Leak Detection (LPG / Methane / CO)
- **Sensor Trigger:** Gas sensor PPM exceeds emergency threshold (e.g., MQ-4 / MQ-9 / Figaro sensor $\ge 1500\text{ PPM}$).
- **Action Sequence (within 250ms):**
  1. **Immediate Fuel Cutoff:** De-energize Normally-Closed (NC) 12V gas shutoff solenoid valve.
  2. **Anti-Sparking Electrical Lockdown:** Inhibit all electrical relay switching in the hazard zone to prevent mechanical contact arcs.
  3. **Ventilation:** Engage intrinsically safe / brushless explosion-proof exhaust fans at 100%.
  4. **Emergency Broadcast:** Emits Level 0 emergency alert across all UI screens and audible edge sirens.

### 2.2 Smoke & Fire Indicators
- **Sensor Trigger:** Photoelectric smoke detector trip or rate-of-rise thermal sensor ($> 65\text{°C}$ or $> 5\text{°C/min}$ delta).
- **Action Sequence:**
  1. **HVAC Air Circulation Kill:** Instantly command all HVAC blowers and dampers to `OFF` to prevent smoke propagation through ducting.
  2. **Egress Lighting:** Force all hallway and exit corridor lighting to 100% white illumination.
  3. **Access Unlocking:** Unlock all motorized exterior entry doors to allow emergency egress and first-responder entry.
  4. **Notification:** Broadcast fire alert with exact room origin.

### 2.3 Catastrophic Water Line Burst / Flood
- **Sensor Trigger:** Conductive floor probe water leak sensor trips OR main flow meter reports continuous $> 50\text{ L/min}$ for $> 3\text{ minutes}$ without corresponding faucet valve commands.
- **Action Sequence:**
  1. **Main Isolation Valve:** Drive motorized ball valve or solenoid on the primary water incoming line to `CLOSED`.
  2. **Booster Pump Trip:** Kill power to water booster pumps to prevent continuous pressure building behind leaks.
  3. **Appliance Protection:** Cut power to washing machines, dishwashers, and water heaters located in the flood zone.

### 2.4 Electrical Overload & Arc Fault
- **Sensor Trigger:** Panel CT clamp reports total household load $> 95\%$ of main circuit breaker rating for $> 10\text{ seconds}$.
- **Action Sequence:**
  - Automated **Progressive Load Shedding** (sheds in order of lowest priority):
    1. Tier 1 Shed: Electric vehicle charger / pool pumps.
    2. Tier 2 Shed: Secondary bedroom AC units.
    3. Tier 3 Shed: Water heaters / laundry dryers.
    *(Life-safety, network, refrigeration, and security circuits are exempt from shedding).*

---

## 3. Security Modes Specification

The house maintains one active **Security Mode** at all times:

```
  +--------+     PIN     +---------+     PIN     +--------+
  |  HOME  | ----------> |  SLEEP  | ----------> |  AWAY  |
  +--------+             +---------+             +--------+
      ^                       ^                       ^
      |                       |                       |
      +-----------------------+-----------------------+
                              |
                     [EMERGENCY TRIPPED]
                              |
                              v
                        +-----------+
                        | EMERGENCY |
                        +-----------+
```

| Security Mode | Perimeter Sensors (Doors/Windows) | Interior Motion (PIR/Radar) | Exterior Surveillance | Actuator Posture |
| :--- | :--- | :--- | :--- | :--- |
| **HOME** | Monitored (Chime on open) | Disarmed | Active | Normal autonomous comfort operation. |
| **SLEEP** | **Armed Instant** | Disarmed in bedrooms; Armed in perimeter & ground corridors | Active + floodlights on motion | Doors locked; garage deadbolted; night lighting protocol active. |
| **AWAY** | **Armed Instant** | **Armed Instant** | Active + Full AI threat analysis | All doors locked; blinds closed; water main closed after 15 min idle; eco HVAC mode ($26\text{°C}$/$18\text{°C}$). |
| **VACATION**| **Armed Instant** | **Armed Instant** | Active | Periodic randomized lighting simulation; water main locked; water heater vacation standby. |
| **EMERGENCY**| Informs incident log | Informs occupancy tracking for rescue | Full recording | Failsafe open/closed as governed by hazard matrix. |

---

## 4. Self-Recovery & Fault Resilience Engine

CODEX must implement automated self-healing workers in `backend/recovery/reconciler.py`:

```
                                 FAILURE DETECTED
                                        │
           ┌────────────────────────────┼────────────────────────────┐
           ▼                            ▼                            ▼
  [MQTT BROKER DROP]           [ESP32 DISCONNECT]           [DATABASE TIMEOUT]
           │                            │                            │
           ▼                            ▼                            ▼
  Backoff reconnect            Mark node OFFLINE            Fallback to in-memory
  Buffer in Redis streams      Set stale state flags        Redis buffer queue
  Max retry backoff 60s        Trigger watchdog alert       Flush WAL on restore
```

### 4.1 MQTT Broker Outage Recovery
- The FastAPI client uses an `aiomqtt` connection wrapper with exponential reconnect jitter.
- Outbound device commands during broker downtime are queued in a persistent Redis FIFO list (`queue:mqtt:pending_commands`, capped at 5,000 items).
- Upon broker reconnection, pending commands with TTL $< 60\text{ seconds}$ are drained and dispatched; expired commands are discarded with log.

### 4.2 ESP32 Node Disconnection & State Resynchronization
- If an ESP32 misses its heartbeat for $> 30\text{ seconds}$, the Digital Twin flags the node as `OFFLINE_STALE`.
- When the ESP32 reconnects, the backend executes a **Bi-Directional State Reconciliation**:
  1. Backend queries ESP32 for current physical GPIO pin states (`GET_STATE`).
  2. Compares physical state against the Digital Twin desired state.
  3. If discrepancies exist (e.g., someone toggled a wall switch during server reboot), the physical state wins for Tier 3 manual switches; the Twin state updates accordingly.

### 4.3 Database Connection Pool Recovery
- FastAPI database sessions use SQLAlchemy `pool_pre_ping=True` and `pool_recycle=3600`.
- If TimescaleDB restarts, active worker threads catch `OperationalError`, retry with linear backoff (1s, 2s, 4s), and buffer critical telemetry in Redis until DB recovery.

---

## 5. Device Health & Telemetry Drift Radar

The `backend/safety/device_health.py` service continuously monitors all connected nodes:

### 5.1 Telemetry Drift & Sensor Sticking
- If an analog sensor (e.g., temperature) reports the exact same floating-point value to 3 decimal places for $> 4\text{ hours}$ despite ambient room variations, it is flagged as `SENSOR_POSSIBLE_FROZEN`.
- If sensor values jump by $> 15\text{°C}$ within a single 1-second sample, the reading is rejected as `OUT_OF_BOUNDS_NOISE` and logged.

### 5.2 Device Health Scoring Formula
Each physical node has a live score $H_{\text{device}} \in [0, 100]$:

$$H_{\text{device}} = 100 - \left( W_{\text{wifi}} \cdot \text{DropPenalty} + W_{\text{latency}} \cdot \text{PingPenalty} + W_{\text{errors}} \cdot \text{RejectPenalty} \right)$$

- If $H_{\text{device}} < 50$, the UI flags a warning badge and schedules a diagnostic ping.

---

## 6. Privacy & Security Architecture

1. **Local Edge Processing First:** Voice processing, intent parsing, camera object detection, and house memory embeddings must run entirely on the local Edge Server (via local models or on-premises vector stores). Zero private telemetry leaves the local network unless the user explicitly configures an external notification webhook.
2. **Secrets & Credential Management:** All database passwords, MQTT credentials, JWT secret keys, and PIN hashes must reside in `.env` or system environment variables. Never commit plaintext secrets to Git.
3. **Audit Log Immutability:** House Black Box records in `house_blackbox` are append-only. No API endpoint exists to update or delete individual event records.
