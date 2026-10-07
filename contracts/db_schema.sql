-- ============================================================================
-- AUTONOMOUS HOUSE OPERATING SYSTEM (HOUSE OS)
-- Authoritative Database DDL Schema (PostgreSQL 16 + TimescaleDB + pgvector)
-- Architect: Anti Gravity | Target Implementer: CODEX
-- ============================================================================

-- 1. EXTENSIONS
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "timescaledb";
CREATE EXTENSION IF NOT EXISTS "vector";

-- 2. TOPOLOGY & STRUCTURE
CREATE TABLE IF NOT EXISTS houses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    timezone VARCHAR(50) NOT NULL DEFAULT 'UTC',
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS floors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    house_id UUID NOT NULL REFERENCES houses(id) ON DELETE CASCADE,
    level_index INT NOT NULL,
    name VARCHAR(100) NOT NULL,
    floor_plan_svg TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS rooms (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    floor_id UUID NOT NULL REFERENCES floors(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    room_type VARCHAR(50) NOT NULL,
    area_sqm DOUBLE PRECISION,
    target_temp_default DOUBLE PRECISION DEFAULT 23.0,
    lighting_lux_target INT DEFAULT 350,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3. USERS, ROLES & PREFERENCES
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(30) NOT NULL DEFAULT 'member', -- owner, admin, member, guest, service
    pin_code_hash VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS user_preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    room_id UUID REFERENCES rooms(id) ON DELETE CASCADE,
    preferred_temp DOUBLE PRECISION DEFAULT 23.5,
    preferred_lux INT DEFAULT 300,
    sleep_time TIME DEFAULT '23:00',
    wake_time TIME DEFAULT '07:00',
    priority_rank INT DEFAULT 5,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 4. DEVICES & SENSORS
CREATE TABLE IF NOT EXISTS devices (
    id VARCHAR(64) PRIMARY KEY, -- e.g., 'esp32_lr_hvac_01'
    room_id UUID REFERENCES rooms(id) ON DELETE SET NULL,
    name VARCHAR(100) NOT NULL,
    category VARCHAR(50) NOT NULL, -- hvac, lighting, switch, valve, pump, lock, curtain, security
    ip_address INET,
    mac_address MACADDR,
    firmware_version VARCHAR(32) NOT NULL DEFAULT '1.0.0',
    is_online BOOLEAN NOT NULL DEFAULT FALSE,
    last_seen_at TIMESTAMPTZ,
    capabilities JSONB NOT NULL DEFAULT '{}'::jsonb,
    current_state JSONB NOT NULL DEFAULT '{}'::jsonb,
    health_score INT NOT NULL DEFAULT 100,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sensors (
    id VARCHAR(64) PRIMARY KEY, -- e.g., 'temp_lr_bme280'
    device_id VARCHAR(64) NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    room_id UUID REFERENCES rooms(id) ON DELETE SET NULL,
    sensor_type VARCHAR(50) NOT NULL, -- temperature, humidity, lux, motion, smoke, gas, water_leak, power_w, water_flow, tank_level
    unit VARCHAR(20) NOT NULL,
    is_safety_critical BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 5. TIME-SERIES HYPERTABLES (TimescaleDB)
CREATE TABLE IF NOT EXISTS sensor_telemetry (
    recorded_at TIMESTAMPTZ NOT NULL,
    sensor_id VARCHAR(64) NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    raw_payload JSONB
);
SELECT create_hypertable('sensor_telemetry', 'recorded_at', if_not_exists => TRUE, chunk_time_interval => INTERVAL '1 day');
CREATE INDEX IF NOT EXISTS idx_telemetry_sensor_time ON sensor_telemetry (sensor_id, recorded_at DESC);

CREATE TABLE IF NOT EXISTS energy_readings (
    recorded_at TIMESTAMPTZ NOT NULL,
    device_id VARCHAR(64) NOT NULL,
    phase VARCHAR(10) DEFAULT 'L1',
    power_watts DOUBLE PRECISION NOT NULL,
    voltage_volts DOUBLE PRECISION NOT NULL,
    current_amps DOUBLE PRECISION NOT NULL,
    power_factor DOUBLE PRECISION DEFAULT 1.0,
    cumulative_kwh DOUBLE PRECISION NOT NULL
);
SELECT create_hypertable('energy_readings', 'recorded_at', if_not_exists => TRUE, chunk_time_interval => INTERVAL '1 day');
CREATE INDEX IF NOT EXISTS idx_energy_device_time ON energy_readings (device_id, recorded_at DESC);

CREATE TABLE IF NOT EXISTS water_metrics (
    recorded_at TIMESTAMPTZ NOT NULL,
    sensor_id VARCHAR(64) NOT NULL,
    flow_rate_lpm DOUBLE PRECISION NOT NULL,
    tank_level_pct DOUBLE PRECISION,
    line_pressure_bar DOUBLE PRECISION,
    pump_state VARCHAR(20) NOT NULL
);
SELECT create_hypertable('water_metrics', 'recorded_at', if_not_exists => TRUE, chunk_time_interval => INTERVAL '1 day');
CREATE INDEX IF NOT EXISTS idx_water_sensor_time ON water_metrics (sensor_id, recorded_at DESC);

-- 6. AUDIT & HOUSE BLACK BOX FLIGHT RECORDER
CREATE TABLE IF NOT EXISTS house_blackbox (
    recorded_at TIMESTAMPTZ NOT NULL,
    event_id UUID DEFAULT gen_random_uuid(),
    source_type VARCHAR(50) NOT NULL, -- USER_UI, AI_BRAIN, SAFETY_MATRIX, HARDWARE_ESP32, AUTOMATION_RULE
    source_identity VARCHAR(100) NOT NULL,
    target_entity VARCHAR(100) NOT NULL,
    action_verb VARCHAR(50) NOT NULL,
    previous_state JSONB,
    new_state JSONB,
    priority_level INT NOT NULL,
    execution_ms DOUBLE PRECISION,
    status VARCHAR(20) NOT NULL
);
SELECT create_hypertable('house_blackbox', 'recorded_at', if_not_exists => TRUE, chunk_time_interval => INTERVAL '1 day');
CREATE INDEX IF NOT EXISTS idx_blackbox_target_time ON house_blackbox (target_entity, recorded_at DESC);

CREATE TABLE IF NOT EXISTS ai_decision_reasons (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    blackbox_id UUID,
    device_id VARCHAR(64) NOT NULL,
    action_summary VARCHAR(255) NOT NULL,
    decided_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    primary_reason TEXT NOT NULL,
    contributing_factors JSONB NOT NULL,
    evaluated_alternatives JSONB,
    confidence_score DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ai_reasons_device_time ON ai_decision_reasons (device_id, decided_at DESC);

-- 7. AUTOMATIONS, SCENES & CONFLICT RESOLUTION
CREATE TABLE IF NOT EXISTS scenes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    icon VARCHAR(50),
    description TEXT,
    actions JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS automation_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    priority_tier INT NOT NULL DEFAULT 4,
    triggers JSONB NOT NULL,
    conditions JSONB NOT NULL,
    actions JSONB NOT NULL,
    debounce_sec INT NOT NULL DEFAULT 0,
    cooldown_sec INT NOT NULL DEFAULT 60,
    last_triggered_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS conflict_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    target_device_id VARCHAR(64) NOT NULL,
    competing_rules JSONB NOT NULL,
    winning_source VARCHAR(100) NOT NULL,
    resolution_basis VARCHAR(100) NOT NULL,
    preempted_source VARCHAR(100) NOT NULL
);

-- 8. SYSTEM HEALTH, MAINTENANCE & EXPERIMENTS
CREATE TABLE IF NOT EXISTS maintenance_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id VARCHAR(64) NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    component_name VARCHAR(100) NOT NULL, -- e.g., 'HEPA Filter', 'Compressor', 'Impeller'
    wear_index_pct DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    installed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_serviced_at TIMESTAMPTZ,
    predicted_service_due TIMESTAMPTZ,
    condition_notes TEXT
);

CREATE TABLE IF NOT EXISTS house_health_snapshots (
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    overall_score INT NOT NULL,
    safety_score INT NOT NULL,
    security_score INT NOT NULL,
    energy_score INT NOT NULL,
    water_score INT NOT NULL,
    device_score INT NOT NULL,
    network_score INT NOT NULL,
    environment_score INT NOT NULL,
    breakdown_details JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS house_experiments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(100) NOT NULL,
    hypothesis TEXT NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'PLANNED',
    start_date TIMESTAMPTZ NOT NULL,
    end_date TIMESTAMPTZ NOT NULL,
    control_params JSONB NOT NULL,
    test_params JSONB NOT NULL,
    energy_delta_kwh DOUBLE PRECISION,
    user_comfort_score DOUBLE PRECISION,
    conclusion_notes TEXT
);

-- 9. VECTOR MEMORY EMBEDDINGS (pgvector)
CREATE TABLE IF NOT EXISTS house_memory_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    category VARCHAR(50) NOT NULL, -- episodic_event, maintenance, anomaly, preference
    content_text TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding vector(1536) -- Standard OpenAI / Ollama dimension
);
CREATE INDEX IF NOT EXISTS idx_house_memory_vec ON house_memory_embeddings USING ivfflat (embedding vector_cosine_ops);
