"""Runtime models matching contracts/schemas_pydantic.py."""

from datetime import datetime
from enum import IntEnum, StrEnum
from typing import Any

from pydantic import BaseModel, Field


class UserRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    GUEST = "guest"
    SERVICE = "service"


class DeviceCategory(StrEnum):
    HVAC = "hvac"
    LIGHTING = "lighting"
    SWITCH = "switch"
    VALVE = "valve"
    PUMP = "pump"
    LOCK = "lock"
    CURTAIN = "curtain"
    SECURITY = "security"
    SENSOR_HUB = "sensor_hub"


class SensorType(StrEnum):
    TEMPERATURE = "temperature"
    HUMIDITY = "humidity"
    LUX = "lux"
    MOTION = "motion"
    SMOKE = "smoke"
    GAS = "gas"
    WATER_LEAK = "water_leak"
    POWER_W = "power_w"
    WATER_FLOW = "water_flow"
    TANK_LEVEL = "tank_level"
    PRESSURE_BAR = "pressure_bar"


class PriorityTier(IntEnum):
    LEVEL_0_SAFETY_EMERGENCY = 0
    LEVEL_1_SECURITY_PERIMETER = 1
    LEVEL_2_INFRASTRUCTURE = 2
    LEVEL_3_MANUAL_OVERRIDE = 3
    LEVEL_4_SCHEDULE_INTENT = 4
    LEVEL_5_AUTONOMOUS_OPTIMIZATION = 5
    LEVEL_6_BACKGROUND_CALIBRATION = 6


class SecurityMode(StrEnum):
    HOME = "HOME"
    SLEEP = "SLEEP"
    AWAY = "AWAY"
    VACATION = "VACATION"
    EMERGENCY = "EMERGENCY"
    CUSTOM = "CUSTOM"


class TelemetryPayload(BaseModel):
    timestamp: int
    sensor_id: str
    device_id: str
    metric_type: SensorType
    value: float
    unit: str
    read_seq: int
    status: str = Field(pattern="^(VALID|OUT_OF_BOUNDS|SENSOR_FAULT)$")
    battery_pct: float | None = None
    raw_payload: dict[str, Any] | None = None


class CommandDispatch(BaseModel):
    command_id: str
    timestamp: int
    device_id: str
    endpoint: str
    action: str
    parameters: dict[str, Any]
    priority_tier: PriorityTier = PriorityTier.LEVEL_3_MANUAL_OVERRIDE
    timeout_ms: int = Field(default=2500, ge=100, le=60_000)
    reason: str | None = None


class CommandProposal(BaseModel):
    endpoint: str = "default"
    action: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    priority_tier: PriorityTier = PriorityTier.LEVEL_3_MANUAL_OVERRIDE
    reason: str | None = None


class HardwareAck(BaseModel):
    command_id: str
    device_id: str
    endpoint: str
    status: str = Field(pattern="^(APPLIED|REJECTED_LOCAL_FAULT|HARDWARE_TIMEOUT)$")
    execution_duration_ms: float = Field(ge=0)
    current_state: dict[str, Any]
    error_code: str | None = None


class HeartbeatPayload(BaseModel):
    device_id: str
    status: str = Field(pattern="^(ONLINE|OFFLINE_UNEXPECTED|SHUTTING_DOWN)$")
    ip_address: str | None = None
    rssi_dbm: int | None = None
    uptime_seconds: int | None = None
    free_heap_bytes: int | None = None
    firmware_version: str | None = None


class ContributingFactor(BaseModel):
    metric: str
    current_val: Any
    threshold_or_target: Any
    weight: float = 1.0


class DecisionReasoning(BaseModel):
    decision_id: str
    device_id: str
    action_summary: str
    timestamp: datetime
    primary_reason: str
    contributing_factors: list[ContributingFactor]
    evaluated_alternatives: list[str] | None = None
    confidence_score: float = Field(ge=0, le=1)


class IntentRequest(BaseModel):
    query_text: str = Field(min_length=1, max_length=500)
    dry_run: bool = False


class WhatIfImpact(BaseModel):
    projected_power_watts_delta: float
    projected_cost_delta: float = 0
    projected_temp_delta: dict[str, float] = Field(default_factory=dict)
    conflict_detected: bool = False
    conflict_warning: str | None = None


class IntentResponse(BaseModel):
    intent_id: str
    parsed_intent: str
    confidence: float
    requires_confirmation: bool
    proposed_actions: list[dict[str, Any]]
    simulation_impact: WhatIfImpact
    explanation: str


class DigitalTwinSnapshot(BaseModel):
    house_id: str
    name: str
    timestamp: datetime
    security_mode: SecurityMode
    health_score: int
    active_power_watts: float
    daily_energy_kwh: float
    main_tank_level_pct: float
    water_flow_lpm: float
    floors: list[dict[str, Any]]


class HouseHealthRadar(BaseModel):
    overall_score: int
    safety_score: int
    security_score: int
    energy_score: int
    water_score: int
    device_score: int
    sensor_score: int
    network_score: int
    environment_score: int
    maintenance_score: int
    explanations: list[str]
