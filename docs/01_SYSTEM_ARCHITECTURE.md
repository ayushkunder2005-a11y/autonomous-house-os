# Architecture Document 01: System Architecture & Topology

> **Component:** Autonomous House OS — System Architecture  
> **Status:** Specification Complete  
> **Target Implementer:** CODEX  

---

## 1. System Vision & Foundational Paradigm

The **Autonomous House OS** is a cyber-physical operating system engineered to govern a residential ecosystem as an integrated, self-regulating biological organism. Unlike fragmented smart home setups that rely on isolated app silos or brittle point-to-point automations, House OS implements a unified **Dual-Loop Architecture**:

1. **The Fast Loop (Hard Determinism & Safety, < 50ms):**
   - Direct sensor-to-actuator safety interlocks.
   - Emergency hazard mitigation (gas, smoke, water burst, thermal runaway).
   - Priority-based conflict resolution and local hardware deadman fail-safes.
   - **Zero AI dependency** in the critical path of life safety and property preservation.

2. **The Cognitive Loop (Probabilistic Intelligence & Optimization, 100ms - 5000ms):**
   - Multi-modal natural language intent translation.
   - Explainable AI (XAI) continuous environmental tuning.
   - Long-term episodic memory, degradation forecasting, and What-If simulation modeling.
   - Predictive resource optimization (water hydraulics and electrical peak shaving).

```
                           +-------------------------------------+
                           |         USER INTERFACES             |
                           |  (Web / Mobile / Voice / Local)     |
                           +------------------+------------------+
                                              | HTTPS / WSS
                                              v
                           +-------------------------------------+
                           |       FASTAPI GATEWAY & WS HUB      |
                           +------------------+------------------+
                                              |
                     +------------------------+------------------------+
                     |                                                 |
                     v                                                 v
   +------------------------------------+            +------------------------------------+
   |         THE COGNITIVE LOOP         |            |           THE FAST LOOP            |
   |                                    |            |                                    |
   |  * Natural Language Intent Engine  |            |  * Digital Twin State Reconciler   |
   |  * House Memory (RAG + Episodic)   |            |  * 7-Tier Priority Conflict Engine |
   |  * What-If Simulation Sandbox      |            |  * Deterministic Safety Matrix     |
   |  * Explainable AI (XAI) Tracing    |            |  * Hardware Watchdogs & Deadbands  |
   |  * Predictive Degradation Models   |            |  * In-Memory Telemetry Cache       |
   +-----------------+------------------+            +-----------------+------------------+
                     |                                                 |
                     +------------------------+------------------------+
                                              |
                                              v
                           +-------------------------------------+
                           |           REDIS EVENT BUS           |
                           |   (Pub/Sub, Stream Aggregations)    |
                           +------------------+------------------+
                                              |
                                              v
                           +-------------------------------------+
                           |        MQTT BROKER (Mosquitto)      |
                           |      (TLS 1.3, Strict QoS 1/2)      |
                           +------------------+------------------+
                                              |
                     +------------------------+------------------------+
                     | Dedicated IoT VLAN (Wi-Fi 802.11 / Ethernet LAN) |
                     +------------------------+------------------------+
                                              |
                       +----------------------+----------------------+
                       |                                             |
                       v                                             v
             +--------------------+                        +--------------------+
             |   ESP32 NODE #1    |                        |   ESP32 NODE #N    |
             |  (Living Room HVAC)|                        | (Main Water Vault) |
             |                    |                        |                    |
             | [Hardware Failsafe]|                        | [Hardware Failsafe]|
             | Relays / Sensors   |                        | Valves / Sensors   |
             +--------------------+                        +--------------------+
```

---

## 2. Hardware Tier & Deployment Topology

### 2.1 Edge Server Node (Host Machine)
- **Architecture:** x86-64 (Intel Core i5/i7 or AMD Ryzen 5/7 Mini-PC, e.g., Intel NUC, Beelink, Minisforum).
- **RAM:** Minimum 16 GB DDR4/DDR5 (32 GB recommended for local vector embeddings and simulation caching).
- **Storage:** 512 GB+ NVMe SSD (PCIe Gen 3/4) dedicated to high-frequency TimescaleDB WAL writes.
- **Networking:** Dual Gigabit Ethernet NICs:
  - `eth0`: Primary LAN (management, Web/Mobile clients, WAN uplink).
  - `eth1`: Isolated Hardware IoT Subnet (VLAN 107: `192.168.107.0/24`) with strict firewall isolation—no internet access permitted for edge microcontrollers.
- **Exclusion Clause:** Raspberry Pi or single-board computers with SD card storage are **strictly prohibited** from running the primary host stack due to I/O bottlenecks and write wear under high-frequency telemetry.

### 2.2 Edge Microcontroller Nodes (ESP32)
- **Silicon Platform:** Espressif ESP32-WROOM-32D / ESP32-S3 (Dual-Core Xtensa LX7 @ 240 MHz, 512KB SRAM, 4MB/8MB Flash).
- **Firmware Framework:** C++ (ESP-IDF v5.x or optimized Arduino-ESP32 Core) with FreeRTOS multitasking.
- **Physical Safety Watchdog:** Hardware external watchdog timer (WDT) and local GPIO fail-safe states upon loss of MQTT heartbeat for > 15 seconds.

---

## 3. Microservice & Container Architecture (Docker Compose)

CODEX must implement the edge server deployment using a unified multi-container Docker Compose stack:

```yaml
version: '3.9'

services:
  # 1. Transport Layer
  mosquitto:
    image: eclipse-mosquitto:2.0.18
    container_name: house_mosquitto
    restart: unless-stopped
    volumes:
      - ./infra/mosquitto/config:/mosquitto/config
      - ./infra/mosquitto/data:/mosquitto/data
      - ./infra/mosquitto/certs:/mosquitto/certs
    ports:
      - "1883:1883"       # Internal IoT VLAN (Mutual TLS or Token)
      - "8883:8883"       # Secure TLS 1.3
    networks:
      iot_net:
        ipv4_address: 192.168.107.2

  # 2. Ephemeral State & Event Pipeline
  redis:
    image: redis:7.2-alpine
    container_name: house_redis
    restart: unless-stopped
    command: redis-server --appendonly yes --requirepass ${REDIS_PASSWORD}
    volumes:
      - redis_data:/data
    networks:
      - internal_net

  # 3. Persistent Relational & Time-Series Database
  timescaledb:
    image: timescale/timescaledb:latest-pg16
    container_name: house_timescale
    restart: unless-stopped
    environment:
      POSTGRES_DB: house_os
      POSTGRES_USER: house_admin
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - pg_data:/var/lib/postgresql/data
    networks:
      - internal_net

  # 4. Vector Store for Episodic House Memory
  chromadb:
    image: chromadb/chroma:0.4.24
    container_name: house_chroma
    restart: unless-stopped
    volumes:
      - chroma_data:/chroma/chroma
    environment:
      - IS_PERSISTENT=TRUE
    networks:
      - internal_net

  # 5. Core Application Engine (FastAPI + Workers)
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: house_backend
    restart: unless-stopped
    depends_on:
      - mosquitto
      - redis
      - timescaledb
      - chromadb
    env_file:
      - .env
    ports:
      - "8000:8000"       # REST API & WebSocket Server
    networks:
      - iot_net
      - internal_net
      - public_net

  # 6. Presentation Web Interface (Nginx + Vue/Vite SPA)
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    container_name: house_frontend
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    depends_on:
      - backend
    networks:
      - public_net

networks:
  iot_net:
    driver: bridge
    ipam:
      config:
        - subnet: 192.168.107.0/24
  internal_net:
    driver: bridge
  public_net:
    driver: bridge

volumes:
  redis_data:
  pg_data:
  chroma_data:
```

---

## 4. Software Subsystems & Layer Responsibilities

### 4.1 Ingestion & Transport Worker (`backend/transport/`)
- Maintains persistent, auto-reconnecting `aiomqtt` client pool.
- Validates every incoming MQTT payload against strict Pydantic models before pushing to Redis.
- Drops malformed packets into a quarantined dead-letter queue with telemetry alert.
- Handles QoS 1 / QoS 2 acknowledgments and publishes commands back to devices.

### 4.2 Digital Twin State Manager (`backend/twin/`)
- In-memory living model representing:
  - House topology: Levels $\to$ Zones $\to$ Rooms $\to$ Fixtures.
  - Device nodes: Power state, target setpoints, duty cycles, operational modes.
  - Physical metrics: Temperature, relative humidity, illuminance, atmospheric pressure, air quality (VOC/CO2/PM2.5), presence/motion.
  - Resource vectors: Instantaneous kW, cumulative kWh, water flow rate (L/min), tank volume (liters).
- Emits real-time state diffs to WebSocket listeners when changes exceed configured hysteresis thresholds.

### 4.3 Deterministic Priority & Conflict Engine (`backend/engine/priority/`)
- Enforces an absolute 7-tier priority matrix (documented in [`docs/06_AUTOMATION_AND_CONFLICT_ENGINE.md`](file:///d:/house%20control/docs/06_AUTOMATION_AND_CONFLICT_ENGINE.md)).
- Intercepts all proposed actions from User, AI, Schedules, and Background Optimizers.
- Rejects or mutates actions that violate physical constraints (e.g., HVAC cooling while windows open, running pump with dry tank).

### 4.4 House Brain Cognitive Core (`backend/brain/`)
- **Intent Parser:** Converts unstructured natural language strings into typed `IntentPlan` objects.
- **Explainable Decision Engine (XAI):** Automatically decorates every autonomous setpoint mutation with a structured `DecisionAuditRecord`.
- **Simulation Sandbox:** Executes predictive "What-If" runs on an ephemeral in-memory clone of the Digital Twin without touching physical actuators.
- **Long-Term Memory:** Indexes episodic house events, anomaly timelines, and user interaction histories using hybrid dense vector embeddings and relational time-series.

### 4.5 House Black Box & Audit Logger (`backend/blackbox/`)
- An immutable flight-recorder recording every incoming sensor reading, command dispatch, manual toggle, rule evaluation, network drop, and emergency trigger.
- Partitioned daily in TimescaleDB with rolling data retention policies.

---

## 5. Performance, Latency & Reliability Budgets

CODEX must ensure the codebase meets or exceeds the following performance parameters:

| Metric | Target Budget | Enforcement Mechanism |
| :--- | :--- | :--- |
| **Emergency Trigger to Cutoff** | $\le 45\text{ ms}$ | Direct deterministic Redis PubSub bypass $\to$ MQTT QoS 2 $\to$ ESP32 interrupt pin. |
| **User Manual Toggle to State Ack** | $\le 120\text{ ms}$ | WebSocket event $\to$ FastAPI $\to$ MQTT dispatch $\to$ Hardware Ack loop. |
| **Digital Twin State Sync Refresh** | $\le 100\text{ ms}$ | In-memory Redis cached state dictionary with async DB write-behind. |
| **Telemetry Ingestion Throughput** | $\ge 2,500\text{ msgs/sec}$ | Asynchronous batching into TimescaleDB hypertable chunks. |
| **NL Intent Resolution & Plan** | $\le 850\text{ ms}$ | Local quantized model / Fast pipeline parser with caching. |
| **Broker Disconnect to Local Fail-Safe**| $15.0\text{ s}$ | ESP32 hardware watchdog timeout; triggers safe relay state. |
| **System Boot to Twin Ready** | $\le 6.0\text{ s}$ | Snapshot load from PostgreSQL into RAM during FastAPI startup event. |

---

## 6. CODEX Verification & Architectural Gates

Before any implementation phase is marked complete, CODEX must verify:
1. No direct communication bypasses the Digital Twin State Manager (all actuator writes must pass through the Conflict Engine).
2. All background tasks run as non-blocking `asyncio` coroutines.
3. No secret keys, passwords, or credentials exist in source code (strictly injected via `.env`).
4. Microcontroller code must operate independently if the central server is disconnected (safe local fallback).
