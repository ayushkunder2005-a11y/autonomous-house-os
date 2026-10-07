# Architecture Document 09: CODEX Implementation Roadmap & Engineering Charter

> **Target Implementer:** CODEX (Autonomous Implementation Agent)  
> **Architect:** Anti Gravity — Autonomous House OS Architect  
> **Status:** Ready for Execution  

---

## 1. Implementer Charter & Strict Boundaries

To CODEX:

As the **Architect**, I have designed the complete system architecture, data models, protocols, algorithms, priority matrices, and interface specifications.

Your mission is to **implement the production-grade application codebase** in accordance with these specifications.
- **Do not guess or improvise core architectural decisions.** Adhere strictly to the contracts and specifications in `docs/` and `contracts/`.
- **Do not take shortcuts with safety.** Deterministic Level 0 emergency interlocks must never depend on external AI APIs or probabilistic code.
- **Do not introduce Raspberry Pi assumptions.** Target x86-64 server environments and ESP32 microcontrollers.
- **Implement comprehensive tests and emulators.** Provide a high-fidelity hardware emulator so the entire system can be tested and demonstrated end-to-end without requiring physical ESP32 chips attached during software builds.

---

## 2. Target Repository Directory Structure

CODEX must construct the repository according to the following clean, modular structure:

```
house-control/
├── contracts/                        # Authoritative machine contracts
│   ├── db_schema.sql                 # Complete PostgreSQL + TimescaleDB DDL
│   ├── mqtt_topics.json              # Canonical topic registry & schemas
│   ├── openapi.json                  # OpenAPI 3.1 REST specification
│   └── schemas_pydantic.py           # Core Pydantic data models
├── docs/                             # Architecture & specification suite
├── docker-compose.yml                # Production multi-service orchestration
├── .env.example                      # Environment variables template
├── Makefile                          # Build, lint, test, and run automation
│
├── backend/                          # FastAPI Core Application
│   ├── Dockerfile
│   ├── pyproject.toml / requirements.txt
│   ├── alembic/                      # Database migrations
│   │   ├── env.py
│   │   └── versions/
│   ├── app/
│   │   ├── main.py                   # FastAPI entrypoint & lifecycle hooks
│   │   ├── config.py                 # Pydantic BaseSettings (.env loader)
│   │   ├── db/
│   │   │   ├── session.py            # SQLAlchemy async session pool
│   │   │   └── models/               # SQLAlchemy ORM models
│   │   ├── transport/                # Transport & Field Bus Layer
│   │   │   ├── mqtt_client.py        # aiomqtt client pool & auto-reconnect
│   │   │   └── redis_bus.py          # Redis Pub/Sub & stream manager
│   │   ├── twin/                     # Digital Twin Layer
│   │   │   ├── state_manager.py      # In-memory living house state
│   │   │   └── synchronizer.py       # State diff generator & DB write-behind
│   │   ├── engine/                   # Automation & Conflict Layer
│   │   │   ├── priority/
│   │   │   │   ├── arbitrator.py     # 7-Tier priority conflict engine
│   │   │   │   └── constraints.py    # Spatial & interlock validator
│   │   │   └── rules/
│   │   │       ├── ast_evaluator.py  # Compound condition evaluator
│   │   │       └── scheduler.py      # Time & cron trigger scheduler
│   │   ├── brain/                    # AI & Cognitive Layer
│   │   │   ├── intent_parser.py      # Natural language intent engine
│   │   │   ├── xai_logger.py         # Explainable AI causal tracer
│   │   │   ├── simulator.py          # What-If in-memory physics sandbox
│   │   │   ├── memory_rag.py         # Episodic house memory & embeddings
│   │   │   └── anomaly.py            # Rolling Z-score & leak detectors
│   │   ├── safety/                   # Safety & Emergency Layer
│   │   │   ├── emergency_matrix.py   # Level 0 deterministic cutoffs
│   │   │   ├── security_modes.py     # Home/Sleep/Away/Vacation FSM
│   │   │   └── device_health.py      # Telemetry drift & health scoring
│   │   ├── recovery/                 # Self-Healing Subsystem
│   │   │   └── reconciler.py         # Node drop recovery & state resync
│   │   ├── api/v1/                   # RESTful API Routers
│   │   │   ├── auth.py
│   │   │   ├── twin.py
│   │   │   ├── devices.py
│   │   │   ├── brain.py
│   │   │   ├── energy.py
│   │   │   ├── water.py
│   │   │   ├── security.py
│   │   │   ├── health.py
│   │   │   └── ws.py                 # WebSocket multiplexed streaming
│   │   └── services/                 # Specialized domain workers
│   │       ├── energy_service.py
│   │       └── water_service.py
│   └── tests/                        # Backend test suite
│       ├── unit/
│       ├── integration/
│       └── conftest.py
│
├── frontend/                         # Modern Web/Mobile SPA Interface
│   ├── Dockerfile
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   ├── src/
│   │   ├── main.ts
│   │   ├── App.vue / App.tsx
│   │   ├── stores/                   # Pinia / Redux state stores
│   │   │   ├── twin.ts
│   │   │   ├── ws.ts
│   │   │   └── security.ts
│   │   ├── components/               # UI Component Library
│   │   │   ├── twin/                 # 2.5D Digital Twin Floorplan Canvas
│   │   │   ├── dashboard/            # Top bar, Health radial, quick scenes
│   │   │   ├── rooms/                # Spatial cards & controls
│   │   │   ├── brain/                # AI console & XAI badges
│   │   │   ├── energy/               # Sankey diagram & power charts
│   │   │   ├── water/                # 3D tank visuals & pump controls
│   │   │   ├── security/             # Mode keypad & emergency panic
│   │   │   └── health/               # Health radar & maintenance cards
│   │   └── views/                    # 10 Core Application Screens
│
├── firmware/                         # ESP32 C++ Microcontroller Code
│   ├── platformio.ini
│   ├── src/
│   │   ├── main.cpp                  # FreeRTOS setup & core pins
│   │   ├── net/
│   │   │   ├── wifi_manager.cpp
│   │   │   └── mqtt_handler.cpp
│   │   ├── safety/
│   │   │   └── deadman_watchdog.cpp  # 15s server loss fallback
│   │   └── drivers/
│   │       ├── bme280_driver.cpp
│   │       ├── relay_driver.cpp
│   │       └── flow_meter_driver.cpp
│
└── simulation/                       # Hardware Emulation Testbed
    └── esp32_fleet_emulator.py       # Python script emulating 20+ ESP32 nodes
```

---

## 3. Phased Implementation Roadmap for CODEX

CODEX must execute development in **9 Sequential Phases**, validating acceptance criteria before advancing:

### Phase 1: Infrastructure & Data Persistence
- **Tasks:**
  - Create `docker-compose.yml` defining Mosquitto, Redis, TimescaleDB, ChromaDB, Backend, Frontend.
  - Implement SQLAlchemy async connection pool and Alembic migrations from `contracts/db_schema.sql`.
  - Implement base Pydantic models from `contracts/schemas_pydantic.py`.
- **Acceptance Criteria:** `docker compose up -d` boots all database and broker services cleanly; Alembic migrations run with zero errors.

### Phase 2: Transport & Field Bus Layer
- **Tasks:**
  - Implement `backend/app/transport/mqtt_client.py` using `aiomqtt`.
  - Implement automatic reconnect backoff with jitter and topic subscriptions.
  - Implement incoming payload validation against `contracts/mqtt_topics.json`.
  - Create `simulation/esp32_fleet_emulator.py` to publish synthetic temperature, energy, and water telemetry.
- **Acceptance Criteria:** Backend ingests $> 1000$ telemetry packets per second from the emulator and streams them to Redis without packet loss.

### Phase 3: Digital Twin & In-Memory State Manager
- **Tasks:**
  - Build `backend/app/twin/state_manager.py` maintaining in-memory tree of floors, rooms, devices, sensors.
  - Implement differential delta generator emitting changes via Redis Pub/Sub.
  - Implement asynchronous write-behind worker saving telemetry batches to TimescaleDB hypertables.
- **Acceptance Criteria:** Querying `GET /api/v1/twin/state` returns a complete, consistent snapshot in $< 15\text{ms}$.

### Phase 4: Deterministic 7-Tier Priority & Conflict Engine
- **Tasks:**
  - Implement `backend/app/engine/priority/arbitrator.py`.
  - Implement spatial constraint checkers (HVAC dual-mode lockout, window-open timer, pump dry-run lockout).
  - Implement conflict logging to `conflict_logs` table.
- **Acceptance Criteria:** Comprehensive unit tests demonstrate Tier 0 emergency commands instantly preempt Tier 3 user commands, and Tier 3 manual commands preempt Tier 5 AI commands.

### Phase 5: Deterministic Safety, Emergency & Self-Recovery
- **Tasks:**
  - Implement Level 0 emergency handlers for gas, fire, flood, and electrical overload.
  - Implement security modes (`HOME`, `SLEEP`, `AWAY`, `VACATION`, `EMERGENCY`) finite state machine.
  - Implement self-recovery worker handling MQTT disconnection, node drops, and bi-directional state reconciliation.
- **Acceptance Criteria:** Triggering a synthetic gas or water alarm trips isolation valves and locks actuators in $< 45\text{ms}$.

### Phase 6: Energy, Water & Device Health Intelligence
- **Tasks:**
  - Implement real-time energy aggregation (instantaneous kW, phase balance, cost tracker).
  - Implement water monitoring (tank volume calculations, flow rate analysis, continuous run leak alerts).
  - Implement Device Health scoring and sensor drift anomaly detection (frozen sensor detector).
- **Acceptance Criteria:** TimescaleDB continuous aggregates compute hourly energy and daily water rollups accurately.

### Phase 7: House Brain, Intent & Explainable AI (XAI)
- **Tasks:**
  - Implement `backend/app/brain/intent_parser.py` supporting conversational commands.
  - Implement What-If simulation engine running on in-memory Digital Twin forks.
  - Implement XAI logger decorating every automated mutation with a typed `DecisionReasoning` object.
  - Implement episodic house memory worker with vector indexing.
- **Acceptance Criteria:** Sending *"Make living room comfortable"* produces a valid multi-device plan with projected power impact and explainability card.

### Phase 8: Modern Web & Mobile Front-End
- **Tasks:**
  - Build Vue 3 / React SPA with TailwindCSS in `frontend/`.
  - Implement WebSocket client connecting to `/api/v1/ws/live-stream` with auto-reconnect.
  - Implement 2.5D interactive Digital Twin Floorplan canvas.
  - Build all 10 core views (Dashboard, Rooms, Devices, Brain, Memory, Energy, Water, Security, Health, Maintenance).
- **Acceptance Criteria:** UI updates smoothly in real time without lag as the ESP32 emulator streams live sensor updates.

### Phase 9: Testing, Benchmarking & Hardening
- **Tasks:**
  - Run full Pytest test suite covering unit, integration, and security checks.
  - Execute stress test with 50 emulated ESP32 nodes running at 10Hz telemetry.
  - Audit all endpoints against OpenAPI 3.1 contract.
  - Produce final operational documentation.
- **Acceptance Criteria:** Zero critical vulnerabilities, $> 85\%$ test coverage across safety and priority engines, $99.99\%$ packet delivery.

---

## 4. CODEX Readiness Sign-Off

The architectural specifications in `docs/` and `contracts/` provide an exhaustive, deterministic blueprint. CODEX can proceed directly with Phase 1 execution.
