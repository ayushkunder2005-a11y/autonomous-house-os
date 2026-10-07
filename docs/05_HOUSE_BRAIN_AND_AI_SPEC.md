# Architecture Document 05: House Brain & AI Cognitive Layer

> **Component:** Autonomous House OS — Intelligence, Intent, Memory & Simulation Engines  
> **Subsystem Targets:** Local LLM / SLM (via Ollama / vLLM / llama.cpp or OpenAI compatible API), ChromaDB / pgvector, TimescaleDB  
> **Target Implementer:** CODEX  

---

## 1. Cognitive Architecture Overview

The **House Brain** is the high-level reasoning and cognitive optimization layer of House OS. It bridges human language and intent with physical cyber-physical actuators.

```
                     USER INTENT / CONVERSATION
                                  │
                                  ▼
                     +──────────────────────────+
                     |   INTENT PARSER & SLM    |
                     |  (Grammar-Constrained)   |
                     +────────────┬─────────────+
                                  │
                  +───────────────┴───────────────+
                  │                               │
                  ▼                               ▼
       +─────────────────────+         +─────────────────────+
       |    HOUSE MEMORY     |         |  WHAT-IF SIMULATOR  |
       |  (Episodic RAG)     |         |  (Twin Sandbox)     |
       +──────────┬──────────+         +──────────┬──────────+
                  │                               │
                  +───────────────┬───────────────+
                                  │
                                  ▼
                     +──────────────────────────+
                     |    PLANNER & XAI ENGINE  |
                     | (Produces Concrete Plan  |
                     |   + "WHY" Causal Trace)  |
                     +────────────┬─────────────+
                                  │
                                  ▼
                     PRIORITY & CONFLICT ENGINE
                     (Deterministic Verification)
```

---

## 2. Natural Language Intent Engine

### 2.1 Intent Pipeline & Finite State Machine
When a user speaks or submits a command (e.g., *"I need a quiet environment for studying in the living room"*), the pipeline executes four sequential phases:

1. **Phase 1: Lexical & Contextual Disambiguation:**
   - Extracts: `Target Space` (Living Room), `Goal` (Study / Focused Work), `Time Horizon` (Immediate), `Occupants` (User).
   - Injects active Digital Twin state (current lux: 120, current temp: 26.2°C, active TV: ON, current noise/audio: Playing Spotify).
2. **Phase 2: Multi-Domain Slot Filling:**
   - **Lighting:** Requires focused neutral white light ($\ge 400\text{ lux}$, $4000\text{K}$).
   - **Climate:** Requires thermal comfort ($23.0\text{°C}$, low fan noise).
   - **Entertainment / Audio:** Mute TV, pause media streams.
   - **Notifications:** Enable "Do Not Disturb" on living room smart speakers.
3. **Phase 3: Sandbox Verification & What-If Run:**
   - Checks if any proposed action violates higher-tier constraints (e.g., if another user in the same room is watching TV with higher preference weight).
4. **Phase 4: Confirmation Gating:**
   - If impact is high or ambiguous (cost increase, affects sleeping family members), returns `requires_confirmation: true`. Otherwise, emits plan for execution.

### 2.2 Canonical Conversational Query Templates
CODEX must implement handlers for the primary natural language archetypes:

| User Query | Intent Category | Execution Resolution |
| :--- | :--- | :--- |
| *"Turn off everything downstairs"* | `SPATIAL_SWEEP` | Resolves all lights, non-essential plugs, and AV on Floor 0. Exempts refrigerators, routers, security cameras. |
| *"Prepare the house for sleeping"* | `MACRO_SCENE` | Sets security mode `SLEEP`, locks all exterior doors, closes motorized blinds, dims corridor nightlights to 10% red, sets bedroom AC to $21.5\text{°C}$. |
| *"I'm leaving for two hours"* | `TIMED_ABSENCE` | Arms security to `AWAY`, turns off interior lights, sets HVAC to eco-setpoint ($26\text{°C}$), sets auto-revert timer to 120 min. |
| *"Why is electricity unusually high today?"* | `FORENSIC_EXPLAIN` | Queries TimescaleDB continuous aggregate; computes device delta vs 30-day baseline; identifies outlier (e.g., *"HVAC in Master Bedroom ran continuously for 7 hours due to an open window"*). |
| *"What happened in the kitchen yesterday?"* | `MEMORY_RECALL` | Semantic search over `house_blackbox` and anomaly tables for `location: Kitchen` between `NOW - 48h` and `NOW - 24h`. |

---

## 3. House Memory & Episodic RAG

### 3.1 Architecture of House Memory
House Memory is a hybrid search system combining:
1. **Dense Vector Embeddings (ChromaDB / pgvector):**
   - Automatically summarizes daily house logs, anomaly events, and maintenance interventions into natural language text paragraphs.
   - Embeds summaries using a 1536-dimensional or 768-dimensional model (e.g., `text-embedding-3-small` or local `bge-base-en-v1.5`).
2. **Structured Relational Time-Series (TimescaleDB):**
   - Exact numerical sensor logs, kWh figures, and state transition histories.

### 3.2 Ingestion & Indexing Worker (`backend/brain/memory_worker.py`)
- Runs every 1 hour and daily at midnight.
- Summarizes hourly operational patterns:
  > *"On Oct 7, 2026, 14:15, a water pressure drop was detected in Main Vault while the booster pump was active. Flow rate peaked at 45 L/min for 8 minutes before the auto-cutoff tripped. User cleared alert at 14:30."*
- Stores embedded record with metadata: `{"tags": ["water", "pressure", "anomaly"], "timestamp": 1772969700}`.

---

## 4. Explainable AI (XAI) Model

### 4.1 Invariant: No Unexplained Automated Action
Every autonomous mutation of a device state must generate a typed `DecisionReasoning` object that is permanently logged to `ai_decision_reasons`.

### 4.2 Causal Reason Structure
When the AC setpoint is automatically adjusted:
```json
{
  "decision_id": "dec_89c011e-2849",
  "device_id": "esp32_lr_hvac_01",
  "action_summary": "Set Living Room AC to 24.0°C (Cooling)",
  "timestamp": "2026-10-07T14:00:00Z",
  "primary_reason": "Dynamic comfort adjustment based on elevated room temperature and confirmed occupancy.",
  "contributing_factors": [
    {
      "metric": "room_temperature",
      "current_val": 27.4,
      "threshold_or_target": 24.0,
      "weight": 0.45
    },
    {
      "metric": "indoor_relative_humidity",
      "current_val": 68.0,
      "threshold_or_target": 55.0,
      "weight": 0.25
    },
    {
      "metric": "occupancy_detected",
      "current_val": true,
      "threshold_or_target": true,
      "weight": 0.20
    },
    {
      "metric": "tariff_peak_pricing_active",
      "current_val": false,
      "threshold_or_target": false,
      "weight": 0.10
    }
  ],
  "evaluated_alternatives": [
    "Keep current setpoint 27°C (Rejected: Exceeds user comfort upper bound 25.5°C)",
    "Set to 22°C max power (Rejected: Energy conservation mode active)"
  ],
  "confidence_score": 0.94
}
```

---

## 5. What-If Simulation Sandbox

### 5.1 In-Memory Digital Twin Fork
Before executing multi-device macro plans or responding to user queries like *"What happens if I set all AC units to 21°C?"*, the system forks an ephemeral clone of `DigitalTwinSnapshot`.

### 5.2 Physics & Financial Estimation Models
1. **Thermal Load Equilibrium Model:**
   $$P_{\text{thermal}} = U \cdot A \cdot (T_{\text{outdoor}} - T_{\text{target}}) + \dot{Q}_{\text{internal}}$$
2. **Electrical Power Delta Model:**
   $$\Delta P_{\text{total}} = \sum_{i \in \text{devices}} \text{RatedPower}_i \cdot \text{ProjectedDutyCycle}_i(T_{\text{target}})$$
3. **Financial Impact Calculation:**
   $$\text{EstimatedCost} = \int_{0}^{H} \Delta P_{\text{total}}(t) \cdot \text{TariffRate}(t) \, dt$$

The simulator checks whether $\sum P_{\text{total}}$ breaches the main breaker limit (e.g., $10\text{ kW}$) or conflicts with active schedules.

---

## 6. Predictive House Engine & Anomaly Detection

### 6.1 Anomaly Detection Subsystems
CODEX must implement real-time sliding-window detectors in `backend/brain/anomaly.py`:

- **Electrical Anomaly Detector:**
  - Computes Rolling Z-Score on 1-minute power draws:
    $$Z = \frac{P_{\text{current}} - \mu_{30\text{d}}}{\sigma_{30\text{d}}}$$
  - If $|Z| > 3.5$ for $> 120\text{ seconds}$, flags `UNUSUAL_ELECTRICAL_CONSUMPTION`.
- **Water Hydraulic Acoustic / Leak Detector:**
  - Continuous micro-flow detection: If water flow $> 0.5\text{ L/min}$ continuously for $> 45\text{ minutes}$ with zero occupancy in bathrooms/kitchen, trips `POSSIBLE_PIPE_LEAK`.
- **HVAC Compressor Thermal Degradation:**
  - Computes COP (Coefficient of Performance) degradation: Ratio of electrical kW consumed to $\Delta T$ temperature drop across heat exchanger over 30 days. If COP drops $> 20\%$, flags `FILTER_OR_REFRIGERANT_MAINTENANCE_DUE`.

---

## 7. House Experiment Mode (A/B Testing Sandbox)

Users can configure scientific house trials via API / UI:
- **Experiment Structure:**
  - Hypothesis: *"Setting bedroom AC to 24°C instead of 22°C between 00:00 and 06:00 will reduce nightly energy consumption by $> 18\%$ without degrading sleep quality."*
  - Control Period: 7 days historical baseline.
  - Active Trial Period: 7 days test parameters.
  - Telemetry Tracked: Bedroom hourly kWh, indoor humidity, ambient sound, user morning feedback score (1-5).
  - Outcome: Automatically generates an empirical results card with statistical confidence intervals ($p\text{-value}$).

---

## 8. CODEX Implementation Directives

1. Implement the Intent Parser with structured output validation (Pydantic models) using local SLMs or standard APIs.
2. Ensure the Simulation Engine runs synchronously in memory without blocking I/O (execution budget $\le 100\text{ms}$).
3. All anomaly detection routines must use bounded Redis circular buffers for rolling statistics to prevent memory leaks.
