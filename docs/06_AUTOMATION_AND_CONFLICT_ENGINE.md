# Architecture Document 06: Automation & Conflict Resolution Engine

> **Component:** Autonomous House OS — Priority Arbitration & Rule Evaluation Engine  
> **Subsystem Target:** `backend/engine/priority/` and `backend/engine/rules/`  
> **Target Implementer:** CODEX  

---

## 1. Engine Philosophy & Architectural Position

In an autonomous residence, multiple agents and rules frequently attempt to drive the same physical actuator toward opposing states simultaneously. For example:
- **Rule A (Schedule):** Open bedroom curtains at 07:00.
- **Rule B (Climate / Thermal):** Keep curtains closed when outdoor solar radiation is excessive and AC is cooling.
- **Rule C (Security):** Close curtains when security mode is `AWAY`.
- **User Action:** Manually toggles curtains open via wall switch at 07:05.

Without an unambiguous, mathematically formalized conflict engine, systems experience actuator thrashing (relays rapidly clicking on and off), mechanical wear, and unpredictable behavior.

```
   RULE ENGINE (Triggers)        USER DASHBOARD (Click)        HOUSE BRAIN (AI)
            │                             │                           │
            ▼                             ▼                           ▼
   +──────────────────────────────────────────────────────────────────────+
   |                  PROPOSED ACTION INTERCEPTOR                         |
   +──────────────────────────────────┬───────────────────────────────────+
                                      │
                                      ▼
   +──────────────────────────────────────────────────────────────────────+
   |            7-TIER DETERMINISTIC PRIORITY ARBITRATION MATRIX          |
   |                                                                      |
   |  Level 0: Life Safety & Emergency Failsafe   [ABSOLUTE LOCK]         |
   |  Level 1: Physical Security & Perimeter     [PREEMPTS L2-L6]        |
   |  Level 2: Infrastructure Preservation       [PREEMPTS L3-L6]        |
   |  Level 3: Explicit Manual User Override     [PREEMPTS L4-L6]        |
   |  Level 4: User Scheduled / Intent Scene     [PREEMPTS L5-L6]        |
   |  Level 5: Autonomous AI Optimization        [PREEMPTS L6]           |
   |  Level 6: Background Maintenance Cycle      [LOWEST TIER]           |
   +──────────────────────────────────┬───────────────────────────────────+
                                      │
                                      ▼
   +──────────────────────────────────────────────────────────────────────+
   |                 SPATIAL & HYDRAULIC CONSTRAINTS CHECK                |
   |  - Anti-Thrashing Deadbands & Minimum Cycling Timers                 |
   |  - Window Open vs HVAC Lockout                                       |
   |  - Multi-Occupant Preference Weight Aggregator                       |
   +──────────────────────────────────┬───────────────────────────────────+
                                      │
                   ┌──────────────────┴──────────────────┐
                   ▼                                     ▼
          [APPROVED FOR MQTT]                  [REJECTED / PREEMPTED]
                   │                                     │
         Dispatches to ESP32                    Logs to `conflict_logs`
                                                with Causal Reason
```

---

## 2. The 7-Tier Strict Priority Matrix

CODEX must implement the priority hierarchy as an immutable integer rank where lower numerical value strictly preempts higher values ($0 > 1 > 2 > 3 > 4 > 5 > 6$):

| Tier Level | Name | Authority Scope | Preemption Behavior |
| :---: | :--- | :--- | :--- |
| **0** | **Safety & Emergency** | Gas leaks, smoke/fire alarms, seismic, water line burst, electrical arc/surge. | **Instantaneous Preemption.** Locks affected actuators into hardware safe state. No user, schedule, or AI command can override until an explicit `EMERGENCY_RESET` is logged with administrative credentials. |
| **1** | **Physical Security** | Perimeter intrusion, exterior door/window locks, motorized hurricane shutters. | Preempts comfort and convenience actions. If mode is `AWAY`, automated curtain opening or exterior door unlocking is rejected. |
| **2** | **Infrastructure Protection** | Water tank overflow prevention, pump dry-run cutoff, compressor short-cycle protection, peak electrical overload shedding. | Prevents equipment destruction. If water tank is empty, booster pump cannot start regardless of user command. |
| **3** | **Explicit Manual User Override** | Physical wall switch press, direct dashboard toggle, voice explicit toggle. | Preempts AI optimization and schedules. Enters a temporary **Manual Hold State** (configurable default: 120 minutes) before returning to autonomous regulation. |
| **4** | **Scheduled & Intent Macro** | Scheduled scenes ("Wake Up", "Movie Night", "Sleep Routine"). | Executes at planned times; overrides background ambient AI optimization. |
| **5** | **Autonomous AI Optimization** | Thermal comfort auto-tuning, daylight harvesting dimming, energy peak-shaving adjustments. | Runs continuously; yields immediately whenever a higher-tier command is received. |
| **6** | **Background Maintenance** | Water pipe descaling flush cycles, sensor baseline auto-zeroing, air filter cleaning cycles. | Runs only during unoccupied periods and low-tariff windows. |

---

## 3. Spatial, Physical & Multi-Actuator Constraints

CODEX must enforce physical constraint rules inside `backend/engine/priority/constraints.py`:

### 3.1 Mutual Exclusion & Interlocks
1. **HVAC Dual-Mode Interlock:** Heating and cooling relays for the same thermal zone must **never** be energized simultaneously. Minimum 5-minute deadband between heating $\to$ cooling transition.
2. **Thermal Envelope Breach Interlock:** If an exterior door or window sensor remains `OPEN` for $> 180\text{ seconds}$ in an active HVAC zone, the HVAC mode is automatically forced to `STANDBY` with notification: *"Living Room AC paused: Window has been open for 3 minutes"*.
3. **Hydraulic Interlock:** If `tank_level_pct` $< 10\%$, water booster pump relay is hardware-locked to `OFF` (dry-run prevention).

### 3.2 Anti-Thrashing, Deadbands & Hysteresis
To prevent rapid relay wear on thermal switches and blinds:
- **Temperature Hysteresis:**
  - Setpoint: $T_{\text{target}}$
  - Cooling triggers when: $T_{\text{room}} \ge T_{\text{target}} + \Delta T_{\text{deadband}}$ (where $\Delta T = 0.5\text{°C}$)
  - Cooling shuts off when: $T_{\text{room}} \le T_{\text{target}} - \Delta T_{\text{deadband}}$
- **Compressor Minimum Run/Dwell Times:**
  - Minimum ON time: 180 seconds.
  - Minimum OFF time (anti-short-cycling): 300 seconds.
- **Motorized Blind Debounce:**
  - Solar lux threshold must persist above or below trigger level for continuously $> 5\text{ minutes}$ before blinds transition state.

---

## 4. Multi-Occupant Household Preference Engine

When multiple users with conflicting preferences occupy the same physical room, House OS resolves setpoints using a mathematical weighting algorithm.

### 4.1 Preference Arbitration Formula
Each user $u \in \text{Occupants}(R)$ possesses a configured preference vector $\mathbf{P}_u = [T_u, L_u]$ and a priority weight $w_u$.

The composite target setpoint $S_{\text{target}}$ for room $R$ is calculated as:

$$S_{\text{target}} = \frac{\sum_{u \in \text{Occupants}(R)} w_u \cdot \mathbf{P}_u}{\sum_{u \in \text{Occupants}(R)} w_u}$$

### 4.2 Dynamic Weight Assignment Rules
- **Base Weight:** `owner` = 1.5, `admin` = 1.3, `member` = 1.0, `guest` = 0.8.
- **Primary Room Affinity:** The primary occupant assigned to a bedroom receives $+0.5$ bonus weight in that specific room.
- **Presence Confirmation:** Only users actively detected in the room via BLE beacon, mmWave radar, or door trip sensors contribute to the equation. If no occupants are present, the room reverts to the baseline eco-profile.

---

## 5. Automation Rule AST & Condition Evaluator

Automation rules are defined via a deterministic JSON Abstract Syntax Tree (AST):

```json
{
  "rule_id": "rule_solar_thermal_management",
  "name": "Solar Thermal Curtain Protection",
  "priority_tier": 5,
  "triggers": [
    {
      "type": "SENSOR_TELEMETRY",
      "sensor_id": "lux_south_facade",
      "operator": "GREATER_THAN",
      "threshold": 35000,
      "duration_sec": 300
    }
  ],
  "conditions": {
    "operator": "AND",
    "clauses": [
      {
        "type": "DEVICE_STATE",
        "device_id": "esp32_lr_hvac_01",
        "path": "current_state.mode",
        "operator": "EQUALS",
        "value": "COOL"
      },
      {
        "type": "ROOM_METRIC",
        "room_id": "room_living_01",
        "metric": "temperature",
        "operator": "GREATER_THAN",
        "value": 24.0
      }
    ]
  },
  "actions": [
    {
      "target_device": "esp32_lr_curtain_01",
      "endpoint": "motor",
      "action": "SET_POSITION",
      "parameters": { "position_pct": 0 },
      "reason": "High solar gain detected while cooling; closed curtains to preserve thermal energy."
    }
  ],
  "cooldown_sec": 600
}
```

---

## 6. CODEX Implementation Directives

1. Implement the priority resolution loop in `backend/engine/priority/arbitrator.py` with an evaluation latency under $5\text{ms}$.
2. Every rejected or mutated command must generate an entry in the `conflict_logs` table detailing: `target_device_id`, `winning_source`, `resolution_basis`, and `preempted_source`.
3. Provide unit test suites simulating edge-case conflicts (e.g., simultaneous button click during fire alarm, user manual override during schedule trigger, multi-user bedroom conflict).
