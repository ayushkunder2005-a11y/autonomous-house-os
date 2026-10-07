# Autonomous House Operating System (House OS)
## Master Architecture Manual

> **Architect:** Anti Gravity — Autonomous House OS Architect  
> **Target Implementer:** CODEX  
> **Status:** Complete & Approved  

---

## 1. System Philosophy & Tenets

House OS is an intelligent operating layer for residential environments. It treats the physical house not as a disconnected collection of IoT gadgets, but as a biological organism maintaining homeostatic equilibrium.

### Core Architectural Invariants:
1. **Safety is Deterministic (Zero-AI Path):** Life-safety (gas, fire, flood, power surge) and physical boundary security bypass all probabilistic reasoning and operate via hardcoded, real-time deterministic finite state machines.
2. **The House is a Living Digital Twin:** An in-memory, graph-structured digital twin maintains the exact physical, environmental, electrical, and hydraulic state of every room and device.
3. **Intent-Driven Interaction:** The user expresses outcomes (*"Prepare house for sleep"*, *"Quiet study environment"*), and the House Brain orchestrates multi-system plans.
4. **Radical Explainability (XAI):** Every single autonomous adjustment generates an immutable causal explanation (*"WHY"*), logging contributing factors and evaluated alternatives.
5. **Deterministic Conflict Resolution:** A strict 7-tier priority matrix guarantees that emergency trips override user commands, and manual user commands override AI optimizations, eliminating actuator thrashing.
6. **Local-First & Privacy Sovereign:** Micro-services, time-series storage, vector embeddings, and intent parsing run locally on an on-premises x86-64 Edge Server. Cloud dependencies are optional and non-critical.
7. **Hardware Decoupling:** ESP32 microcontrollers run independent FreeRTOS firmware with 15-second hardware deadman watchdogs that fall back to fail-safe relay positions if network connectivity is severed.

---

## 2. Architectural Blueprint Map

The architectural blueprint is partitioned into modular specifications:

```
d:/house control/
├── README.md                                # Executive summary & system index
├── ARCHITECTURE.md                          # Master architectural manual
├── docs/
│   ├── 01_SYSTEM_ARCHITECTURE.md           # Topology, Docker Compose, latency budgets
│   ├── 02_DATABASE_SCHEMA_SPEC.md          # PostgreSQL + TimescaleDB + pgvector
│   ├── 03_MQTT_AND_HARDWARE_PROTOCOL.md    # Mosquitto, topics, ESP32 FreeRTOS C++ protocol
│   ├── 04_API_AND_WEBSOCKET_SPEC.md        # FastAPI REST & WebSocket streaming
│   ├── 05_HOUSE_BRAIN_AND_AI_SPEC.md       # Intent engine, memory RAG, XAI, What-If simulator
│   ├── 06_AUTOMATION_AND_CONFLICT_ENGINE.md# 7-Tier priority matrix, AST rule engine
│   ├── 07_SAFETY_EMERGENCY_AND_SELF_RECOVERY.md # Deterministic emergency workflows & recovery
│   ├── 08_UI_UX_DESIGN_SPEC.md             # 10 Screen views, 2.5D Digital Twin, tokens
│   └── 09_CODEX_IMPLEMENTATION_ROADMAP.md  # 9-phase implementation roadmap for CODEX
└── contracts/
    ├── db_schema.sql                       # Complete PostgreSQL/TimescaleDB SQL DDL
    ├── mqtt_topics.json                    # Machine-readable MQTT topic & payload registry
    ├── openapi.json                        # OpenAPI 3.1 RESTful contract
    └── schemas_pydantic.py                 # Authoritative Python Pydantic models
```

---

## 3. The 25 Core House OS Capabilities Matrix

| # | Subsystem Feature | Specification Location | Architectural Solution Summary |
| :-: | :--- | :--- | :--- |
| **1** | **House Digital Twin** | [`docs/01`](file:///d:/house%20control/docs/01_SYSTEM_ARCHITECTURE.md), [`docs/04`](file:///d:/house%20control/docs/04_API_AND_WEBSOCKET_SPEC.md) | In-memory tree model of floors, rooms, devices, sensors, occupants, and resource flows. Emits real-time delta diffs via WebSocket. |
| **2** | **House Brain** | [`docs/05_HOUSE_BRAIN_AND_AI_SPEC.md`](file:///d:/house%20control/docs/05_HOUSE_BRAIN_AND_AI_SPEC.md) | High-level reasoning layer balancing user preferences, ambient conditions, and energy tariffs. |
| **3** | **Natural-Language Control** | [`docs/05_HOUSE_BRAIN_AND_AI_SPEC.md`](file:///d:/house%20control/docs/05_HOUSE_BRAIN_AND_AI_SPEC.md) | Conversational parser translating multi-step user intent into structured JSON execution plans. |
| **4** | **House Intent Engine** | [`docs/05_HOUSE_BRAIN_AND_AI_SPEC.md`](file:///d:/house%20control/docs/05_HOUSE_BRAIN_AND_AI_SPEC.md) | Goal-driven orchestration (e.g., *"study environment"* $\to$ lighting, climate, mute audio, DND). |
| **5** | **House Memory** | [`docs/05_HOUSE_BRAIN_AND_AI_SPEC.md`](file:///d:/house%20control/docs/05_HOUSE_BRAIN_AND_AI_SPEC.md) | Hybrid search combining vector embeddings (episodic summaries) and TimescaleDB (time-series). |
| **6** | **Predictive House Engine** | [`docs/05_HOUSE_BRAIN_AND_AI_SPEC.md`](file:///d:/house%20control/docs/05_HOUSE_BRAIN_AND_AI_SPEC.md) | Degradation curves for HVAC COP, water pump performance, and occupancy pattern prediction. |
| **7** | **What-If Simulation Engine** | [`docs/05_HOUSE_BRAIN_AND_AI_SPEC.md`](file:///d:/house%20control/docs/05_HOUSE_BRAIN_AND_AI_SPEC.md) | Ephemeral in-memory Digital Twin sandbox forecasting energy draw, thermal equilibrium, and costs before actuation. |
| **8** | **House Anomaly Detection** | [`docs/05_HOUSE_BRAIN_AND_AI_SPEC.md`](file:///d:/house%20control/docs/05_HOUSE_BRAIN_AND_AI_SPEC.md) | Rolling Z-score electricity anomalies, continuous micro-flow acoustic water leaks, frozen sensor detection. |
| **9** | **House Health Score** | [`docs/02`](file:///d:/house%20control/docs/02_DATABASE_SCHEMA_SPEC.md), [`docs/08`](file:///d:/house%20control/docs/08_UI_UX_DESIGN_SPEC.md) | 9-dimensional health radar (Safety, Security, Energy, Water, Devices, Sensors, Network, Environment, Maintenance). |
| **10**| **Automation Conflict Engine** | [`docs/06_AUTOMATION_AND_CONFLICT_ENGINE.md`](file:///d:/house%20control/docs/06_AUTOMATION_AND_CONFLICT_ENGINE.md) | Strict 7-tier priority matrix, spatial interlocks (window vs HVAC), deadbands, and anti-thrashing. |
| **11**| **Household Preference Engine** | [`docs/06_AUTOMATION_AND_CONFLICT_ENGINE.md`](file:///d:/house%20control/docs/06_AUTOMATION_AND_CONFLICT_ENGINE.md) | Multi-occupant room setpoint weighted consensus formula based on user tier and room affinity. |
| **12**| **Energy Intelligence** | [`docs/02`](file:///d:/house%20control/docs/02_DATABASE_SCHEMA_SPEC.md), [`docs/08`](file:///d:/house%20control/docs/08_UI_UX_DESIGN_SPEC.md) | Real-time phase monitoring, device-level consumption, continuous aggregates, and peak tariff shaving. |
| **13**| **Water Intelligence** | [`docs/02`](file:///d:/house%20control/docs/02_DATABASE_SCHEMA_SPEC.md), [`docs/07`](file:///d:/house%20control/docs/07_SAFETY_EMERGENCY_AND_SELF_RECOVERY.md) | Dual-tank (underground/overhead) monitoring, pump dry-run cutoff, and burst leak isolation. |
| **14**| **Smart Maintenance** | [`docs/02`](file:///d:/house%20control/docs/02_DATABASE_SCHEMA_SPEC.md), [`docs/05`](file:///d:/house%20control/docs/05_HOUSE_BRAIN_AND_AI_SPEC.md) | Condition-based maintenance monitoring filter flow resistance and compressor thermal drop vs calendar time. |
| **15**| **House Black Box** | [`docs/02`](file:///d:/house%20control/docs/02_DATABASE_SCHEMA_SPEC.md), [`docs/04`](file:///d:/house%20control/docs/04_API_AND_WEBSOCKET_SPEC.md) | Append-only flight recorder logging all commands, transitions, preemption logs, and emergency trips. |
| **16**| **Explainable AI (XAI)** | [`docs/05_HOUSE_BRAIN_AND_AI_SPEC.md`](file:///d:/house%20control/docs/05_HOUSE_BRAIN_AND_AI_SPEC.md) | Typed `DecisionReasoning` records documenting contributing sensor metrics, weights, and rejected options. |
| **17**| **Security Modes** | [`docs/07_SAFETY_EMERGENCY_AND_SELF_RECOVERY.md`](file:///d:/house%20control/docs/07_SAFETY_EMERGENCY_AND_SELF_RECOVERY.md) | State machine for `HOME`, `SLEEP`, `AWAY`, `VACATION`, `EMERGENCY` with granular sensor posture. |
| **18**| **Emergency System** | [`docs/07_SAFETY_EMERGENCY_AND_SELF_RECOVERY.md`](file:///d:/house%20control/docs/07_SAFETY_EMERGENCY_AND_SELF_RECOVERY.md) | Hard real-time deterministic workflows for gas leak, fire, flood, and electrical overload. |
| **19**| **Device Health** | [`docs/07_SAFETY_EMERGENCY_AND_SELF_RECOVERY.md`](file:///d:/house%20control/docs/07_SAFETY_EMERGENCY_AND_SELF_RECOVERY.md) | Tracks Wi-Fi RSSI, packet loss, sensor sticking/drift, and round-trip MQTT latency. |
| **20**| **Self-Recovery** | [`docs/07_SAFETY_EMERGENCY_AND_SELF_RECOVERY.md`](file:///d:/house%20control/docs/07_SAFETY_EMERGENCY_AND_SELF_RECOVERY.md) | Automatic reconnect with jitter, command queue buffering in Redis, and bi-directional state sync. |
| **21**| **House Experiment Mode** | [`docs/02`](file:///d:/house%20control/docs/02_DATABASE_SCHEMA_SPEC.md), [`docs/05`](file:///d:/house%20control/docs/05_HOUSE_BRAIN_AND_AI_SPEC.md) | Controlled scientific A/B trials comparing energy efficiency and comfort against baseline periods. |
| **22**| **Privacy Architecture** | [`docs/01`](file:///d:/house%20control/docs/01_SYSTEM_ARCHITECTURE.md), [`docs/07`](file:///d:/house%20control/docs/07_SAFETY_EMERGENCY_AND_SELF_RECOVERY.md) | 100% on-premises edge processing, Argon2id hashing, encrypted NVS on ESP32, zero required cloud calls. |
| **23**| **UI/UX Design** | [`docs/08_UI_UX_DESIGN_SPEC.md`](file:///d:/house%20control/docs/08_UI_UX_DESIGN_SPEC.md) | Obsidian dark mode, glassmorphic cards, 2.5D Digital Twin Floorplan, and 10 specialized views. |
| **24**| **Multi-Device Responsiveness**| [`docs/08_UI_UX_DESIGN_SPEC.md`](file:///d:/house%20control/docs/08_UI_UX_DESIGN_SPEC.md) | Adaptive layouts for wall panels, desktop cockpits, tablets, and smartphones. |
| **25**| **Documentation for CODEX**| [`docs/09_CODEX_IMPLEMENTATION_ROADMAP.md`](file:///d:/house%20control/docs/09_CODEX_IMPLEMENTATION_ROADMAP.md) | 9-phase roadmap, acceptance criteria, directory blueprint, and pre-compiled machine contracts. |

---

## 4. Architectural Sign-Off

This document and its referenced specifications constitute the complete architectural definition of the Autonomous House Operating System. CODEX has full authorization to proceed with implementation.
