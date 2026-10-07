# Architecture Document 02: Database Schema & Storage Architecture

> **Component:** Autonomous House OS — Persistence Layer  
> **Target Database:** PostgreSQL 16 + TimescaleDB Extension + pgvector  
> **Target Implementer:** CODEX  
> **Source DDL Artifact:** [`contracts/db_schema.sql`](file:///d:/house%20control/contracts/db_schema.sql)  

---

## 1. Persistence Architecture Overview

The persistence architecture divides data storage into four specialized tiers:
1. **Relational Metadata Tier (PostgreSQL):** Configuration, floors, rooms, device topology, user permissions, automation rules, preference graphs, and maintenance schedules.
2. **High-Frequency Time-Series Tier (TimescaleDB Hypertables):** Telemetry from sensors, power monitors (kW/kWh), water flow meters, pump pressures, and system network health metrics.
3. **Immutable Audit & Event Flight-Recorder Tier (TimescaleDB Hypertables):** The **House Black Box**, recording all user commands, state mutations, priority preemptions, and emergency trips.
4. **Episodic & Semantic Memory Tier (pgvector / ChromaDB):** Dense vector embeddings of house state summaries, conversational queries, anomaly logs, and system explanations.

---

## 2. Entity-Relationship & Relational Model

```
   +--------------------+       1:N       +--------------------+
   |       houses       | --------------< |       floors       |
   +--------------------+                 +--------------------+
             | 1:N                                  | 1:N
             v                                      v
   +--------------------+       1:N       +--------------------+
   |       users        |                 |       rooms        |
   +--------------------+                 +--------------------+
             |                                      | 1:N
             |                                      v
             |                            +--------------------+
             | 1:N                        |      devices       |
             v                            +--------------------+
   +--------------------+                           | 1:N
   |  user_preferences  |                           v
   +--------------------+                 +--------------------+
                                          |      sensors       |
                                          +--------------------+
                                                    | 1:N
                                                    v
                                          +--------------------+ (Hypertable)
                                          |  sensor_telemetry  |
                                          +--------------------+
```

---

## 3. Relational Table Specifications

### 3.1 Structural Topology: Houses, Floors, Rooms

#### `houses`
| Column | Data Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | `PRIMARY KEY, DEFAULT gen_random_uuid()` | Unique house identifier. |
| `name` | `VARCHAR(100)` | `NOT NULL` | House human-readable name. |
| `timezone` | `VARCHAR(50)` | `NOT NULL DEFAULT 'UTC'` | Local timezone string (e.g., 'America/New_York'). |
| `latitude` | `DOUBLE PRECISION` | `NOT NULL` | Geographic coordinate for solar & weather calculation. |
| `longitude` | `DOUBLE PRECISION` | `NOT NULL` | Geographic coordinate. |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL DEFAULT NOW()` | Record creation timestamp. |

#### `floors`
| Column | Data Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | `PRIMARY KEY, DEFAULT gen_random_uuid()` | Floor identifier. |
| `house_id` | `UUID` | `REFERENCES houses(id) ON DELETE CASCADE` | Parent house reference. |
| `level_index` | `INT` | `NOT NULL` | Numerical floor order (e.g., -1=Basement, 0=Ground, 1=First). |
| `name` | `VARCHAR(100)` | `NOT NULL` | Floor name (e.g., 'Ground Floor'). |
| `floor_plan_svg` | `TEXT` | `NULL` | Vector representation for 2.5D Digital Twin UI. |

#### `rooms`
| Column | Data Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | `PRIMARY KEY, DEFAULT gen_random_uuid()` | Room identifier. |
| `floor_id` | `UUID` | `REFERENCES floors(id) ON DELETE CASCADE` | Parent floor reference. |
| `name` | `VARCHAR(100)` | `NOT NULL` | Room name (e.g., 'Master Bedroom'). |
| `room_type` | `VARCHAR(50)` | `NOT NULL` | Enum: `living`, `bedroom`, `kitchen`, `bath`, `utility`, `corridor`. |
| `area_sqm` | `DOUBLE PRECISION`| `NULL` | Room surface area in square meters. |
| `target_temp_default`| `DOUBLE PRECISION`| `DEFAULT 23.0` | Default baseline setpoint. |
| `lighting_lux_target` | `INT` | `DEFAULT 350` | Target illuminance level when occupied. |

---

### 3.2 Devices, Capabilities & Endpoints

#### `devices`
| Column | Data Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `VARCHAR(64)` | `PRIMARY KEY` | Hardware-unique slug (e.g., `esp32_lr_hvac_01`). |
| `room_id` | `UUID` | `REFERENCES rooms(id) ON DELETE SET NULL`| Assigned room location. |
| `name` | `VARCHAR(100)` | `NOT NULL` | User-friendly device alias. |
| `category` | `VARCHAR(50)` | `NOT NULL` | Enum: `hvac`, `lighting`, `switch`, `valve`, `pump`, `lock`, `curtain`, `security`. |
| `ip_address` | `INET` | `NULL` | Assigned IoT VLAN IP. |
| `mac_address` | `MACADDR` | `NULL` | Hardware MAC address. |
| `firmware_version`| `VARCHAR(32)`| `NOT NULL DEFAULT '1.0.0'` | Deployed ESP32 firmware version. |
| `is_online` | `BOOLEAN` | `NOT NULL DEFAULT FALSE` | Live connectivity status. |
| `last_seen_at` | `TIMESTAMPTZ` | `NULL` | Heartbeat timestamp. |
| `capabilities` | `JSONB` | `NOT NULL DEFAULT '{}'` | Capability flags: `{"dimmable": true, "color_temp": true, "power_metering": true}`. |
| `current_state` | `JSONB` | `NOT NULL DEFAULT '{}'` | Live state dictionary: `{"power": "ON", "speed": 2, "setpoint": 23.5}`. |
| `health_score` | `INT` | `NOT NULL DEFAULT 100` | Dynamic rating (0 - 100). |

#### `sensors`
| Column | Data Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `VARCHAR(64)` | `PRIMARY KEY` | Sensor slug (e.g., `temp_lr_bme280`). |
| `device_id` | `VARCHAR(64)` | `REFERENCES devices(id) ON DELETE CASCADE`| Host microcontroller device. |
| `room_id` | `UUID` | `REFERENCES rooms(id) ON DELETE SET NULL`| Physical telemetry location. |
| `sensor_type` | `VARCHAR(50)` | `NOT NULL` | Enum: `temperature`, `humidity`, `lux`, `motion`, `smoke`, `gas`, `water_leak`, `power_w`, `water_flow`, `tank_level`. |
| `unit` | `VARCHAR(20)` | `NOT NULL` | Unit of measure (`C`, `%`, `lux`, `boolean`, `W`, `L/m`, `cm`). |
| `is_safety_critical`| `BOOLEAN`| `NOT NULL DEFAULT FALSE` | Flag for Level 0 emergency interlocks. |

---

### 3.3 Users, Permissions & Preferences

#### `users`
| Column | Data Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | `PRIMARY KEY, DEFAULT gen_random_uuid()` | User identifier. |
| `username` | `VARCHAR(50)` | `UNIQUE NOT NULL` | Login username. |
| `password_hash`| `VARCHAR(255)`| `NOT NULL` | Argon2id password hash. |
| `role` | `VARCHAR(30)` | `NOT NULL DEFAULT 'member'` | Enum: `owner`, `admin`, `member`, `guest`, `service`. |
| `pin_code_hash`| `VARCHAR(255)`| `NULL` | Emergency/Security mode PIN hash. |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL DEFAULT NOW()` | Creation timestamp. |

#### `user_preferences`
| Column | Data Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | `PRIMARY KEY, DEFAULT gen_random_uuid()` | Record identifier. |
| `user_id` | `UUID` | `REFERENCES users(id) ON DELETE CASCADE` | Associated user. |
| `room_id` | `UUID` | `REFERENCES rooms(id) ON DELETE CASCADE` | Specific room (or NULL for global). |
| `preferred_temp`| `DOUBLE PRECISION`| `DEFAULT 23.5` | Preferred temperature. |
| `preferred_lux` | `INT` | `DEFAULT 300` | Preferred brightness level. |
| `sleep_time` | `TIME` | `DEFAULT '23:00'` | Typical sleep schedule. |
| `wake_time` | `TIME` | `DEFAULT '07:00'` | Typical wake schedule. |
| `priority_rank`| `INT` | `DEFAULT 5` | Tie-breaker rank for multi-occupant conflicts (1 = highest). |

---

## 4. Time-Series Hypertables (TimescaleDB)

CODEX must configure TimescaleDB chunk intervals for optimal memory usage and query performance.

### 4.1 `sensor_telemetry` (Hypertable)
```sql
CREATE TABLE sensor_telemetry (
    recorded_at TIMESTAMPTZ NOT NULL,
    sensor_id   VARCHAR(64) NOT NULL,
    value       DOUBLE PRECISION NOT NULL,
    raw_payload JSONB NULL
);
SELECT create_hypertable('sensor_telemetry', 'recorded_at', chunk_time_interval => INTERVAL '1 day');
CREATE INDEX idx_telemetry_sensor_time ON sensor_telemetry (sensor_id, recorded_at DESC);
```

### 4.2 `energy_readings` (Hypertable)
```sql
CREATE TABLE energy_readings (
    recorded_at    TIMESTAMPTZ NOT NULL,
    device_id      VARCHAR(64) NOT NULL,
    phase          VARCHAR(10) DEFAULT 'L1', -- L1, L2, L3, total
    power_watts    DOUBLE PRECISION NOT NULL,
    voltage_volts  DOUBLE PRECISION NOT NULL,
    current_amps   DOUBLE PRECISION NOT NULL,
    power_factor   DOUBLE PRECISION DEFAULT 1.0,
    cumulative_kwh DOUBLE PRECISION NOT NULL
);
SELECT create_hypertable('energy_readings', 'recorded_at', chunk_time_interval => INTERVAL '1 day');
CREATE INDEX idx_energy_device_time ON energy_readings (device_id, recorded_at DESC);
```

### 4.3 `water_metrics` (Hypertable)
```sql
CREATE TABLE water_metrics (
    recorded_at      TIMESTAMPTZ NOT NULL,
    sensor_id        VARCHAR(64) NOT NULL,
    flow_rate_lpm    DOUBLE PRECISION NOT NULL,
    tank_level_pct   DOUBLE PRECISION NULL,
    line_pressure_bar DOUBLE PRECISION NULL,
    pump_state       VARCHAR(20) NOT NULL -- 'OFF', 'RUNNING', 'FAULT', 'DRY_RUN_TRIP'
);
SELECT create_hypertable('water_metrics', 'recorded_at', chunk_time_interval => INTERVAL '1 day');
CREATE INDEX idx_water_sensor_time ON water_metrics (sensor_id, recorded_at DESC);
```

---

## 5. House Black Box & Explainable AI Audit Tables

### 5.1 `house_blackbox` (Hypertable: Flight Recorder)
Every state mutation, user button press, MQTT ack, and error must be recorded here:
```sql
CREATE TABLE house_blackbox (
    recorded_at     TIMESTAMPTZ NOT NULL,
    event_id        UUID DEFAULT gen_random_uuid(),
    source_type     VARCHAR(50) NOT NULL, -- 'USER_UI', 'AI_BRAIN', 'SAFETY_MATRIX', 'HARDWARE_ESP32', 'AUTOMATION_RULE'
    source_identity VARCHAR(100) NOT NULL, -- User ID, Rule ID, or Sensor ID
    target_entity   VARCHAR(100) NOT NULL, -- Device ID, Room ID, or System
    action_verb     VARCHAR(50) NOT NULL,  -- 'SET_SETPOINT', 'EMERGENCY_SHUTDOWN', 'PREEMPT_RULE', 'TOGGLE'
    previous_state  JSONB NULL,
    new_state       JSONB NULL,
    priority_level  INT NOT NULL,          -- 0 to 6
    execution_ms    DOUBLE PRECISION NULL, -- Execution latency
    status          VARCHAR(20) NOT NULL   -- 'SUCCESS', 'PREEMPTED', 'BLOCKED_SAFETY', 'HARDWARE_TIMEOUT'
);
SELECT create_hypertable('house_blackbox', 'recorded_at', chunk_time_interval => INTERVAL '1 day');
CREATE INDEX idx_blackbox_target_time ON house_blackbox (target_entity, recorded_at DESC);
```

### 5.2 `ai_decision_reasons` (Explainable AI - "WHY" Storage)
```sql
CREATE TABLE ai_decision_reasons (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    blackbox_id     UUID NULL,
    device_id       VARCHAR(64) NOT NULL,
    action_summary  VARCHAR(255) NOT NULL,
    decided_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    primary_reason  TEXT NOT NULL,
    contributing_factors JSONB NOT NULL, 
    -- Format: [{"metric": "room_temp", "val": 27.4, "threshold": 25.0}, {"metric": "occupancy", "val": true}]
    evaluated_alternatives JSONB NULL,
    confidence_score DOUBLE PRECISION NOT NULL
);
CREATE INDEX idx_ai_reasons_device_time ON ai_decision_reasons (device_id, decided_at DESC);
```

---

## 6. Automations, Conflict Management & Experiments

### 6.1 `automation_rules`
```sql
CREATE TABLE automation_rules (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name           VARCHAR(100) NOT NULL,
    description    TEXT,
    is_active      BOOLEAN NOT NULL DEFAULT TRUE,
    priority_tier  INT NOT NULL DEFAULT 4, -- 0=Emergency, 1=Security, 2=Infra, 3=Manual, 4=Schedule, 5=AI, 6=Maintenance
    triggers       JSONB NOT NULL, -- Array of trigger definitions
    conditions     JSONB NOT NULL, -- Compound boolean AST
    actions        JSONB NOT NULL, -- Array of target actions
    debounce_sec   INT NOT NULL DEFAULT 0,
    cooldown_sec   INT NOT NULL DEFAULT 60,
    last_triggered_at TIMESTAMPTZ NULL
);
```

### 6.2 `conflict_logs`
```sql
CREATE TABLE conflict_logs (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    detected_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    target_device_id VARCHAR(64) NOT NULL,
    competing_rules  JSONB NOT NULL, -- Details of conflicting rule/action attempts
    winning_source   VARCHAR(100) NOT NULL,
    resolution_basis VARCHAR(100) NOT NULL, -- 'HIGHER_PRIORITY_TIER', 'USER_OVERRIDE_PREEMPTION', 'SAFETY_LOCK'
    preempted_source VARCHAR(100) NOT NULL
);
```

### 6.3 `house_experiments`
```sql
CREATE TABLE house_experiments (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title           VARCHAR(100) NOT NULL,
    hypothesis      TEXT NOT NULL,
    status          VARCHAR(30) NOT NULL DEFAULT 'PLANNED', -- 'PLANNED', 'RUNNING', 'COMPLETED', 'ABORTED'
    start_date      TIMESTAMPTZ NOT NULL,
    end_date        TIMESTAMPTZ NOT NULL,
    control_params  JSONB NOT NULL,
    test_params     JSONB NOT NULL,
    energy_delta_kwh DOUBLE PRECISION NULL,
    user_comfort_score DOUBLE PRECISION NULL,
    conclusion_notes TEXT NULL
);
```

---

## 7. Continuous Aggregations (TimescaleDB)

CODEX must enable the following continuous aggregation views to avoid full-table scans for dashboard rendering:

```sql
-- Hourly Energy Rollup
CREATE MATERIALIZED VIEW hourly_energy_summary
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', recorded_at) AS bucket,
    device_id,
    AVG(power_watts) as avg_watts,
    MAX(power_watts) as peak_watts,
    MAX(cumulative_kwh) - MIN(cumulative_kwh) as consumed_kwh
FROM energy_readings
GROUP BY bucket, device_id;

-- Daily Water Rollup
CREATE MATERIALIZED VIEW daily_water_summary
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', recorded_at) AS bucket,
    sensor_id,
    SUM(flow_rate_lpm / 60.0) as total_liters_used
FROM water_metrics
GROUP BY bucket, sensor_id;
```

---

## 8. CODEX Implementation Directives

1. Use **Alembic** for Python database migrations in `backend/alembic/`.
2. All timeseries tables must use `TIMESTAMPTZ` with UTC enforcement.
3. Every mutating transaction touching multiple devices must wrap inside explicit PostgreSQL isolation levels (`READ COMMITTED`).
4. Read queries for dashboard charts must hit the TimescaleDB continuous aggregates rather than raw telemetry tables.
