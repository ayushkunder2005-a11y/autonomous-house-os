"""
Authoritative Pydantic Data Contracts for Autonomous House OS
Architect: Anti Gravity | Target Implementer: CODEX
"""

from __future__ import annotations
from datetime import datetime, time
from enum import Enum, IntEnum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, IPvAnyAddress


# ============================================================================
# 1. ENUMS & CONSTANTS
# ============================================================================

class UserRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    GUEST = "guest"
    SERVICE = "service"


class RoomType(str, Enum):
    LIVING = "living"
    BEDROOM = "bedroom"
    KITCHEN = "kitchen"
    BATH = "bath"
    UTILITY = "utility"
    CORRIDOR = "corridor"
    OUTDOOR = "outdoor"


class DeviceCategory(str, Enum):
    HVAC = "hvac"
    LIGHTING = "lighting"
    SWITCH = "switch"
    VALVE = "valve"
    PUMP = "pump"
    LOCK = "lock"
    CURTAIN = "curtain"
    SECURITY = "security"
    SENSOR_HUB = "sensor_hub"


class SensorType(str, Enum):
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


class SecurityMode(str, Enum):
    HOME = "HOME"
    SLEEP = "SLEEP"
    AWAY = "AWAY"
    VACATION = "VACATION"
    EMERGENCY = "EMERGENCY"
    CUSTOM = "CUSTOM"


# ============================================================================
# 2. TELEMETRY & HARDWARE CONTRACTS
# ============================================================================

class TelemetryPayload(BaseModel):
    timestamp: int = Field(..., description="Epoch millisecond timestamp")
    sensor_id: str
    device_id: str
    metric_type: SensorType
    value: float
    unit: str
    read_seq: int
    status: str = "VALID"
    battery_pct: Optional[float] = None
    raw_payload: Optional[Dict[str, Any]] = None


class CommandDispatch(BaseModel):
    command_id: str
    timestamp: int
    device_id: str
    endpoint: str
    action: str
    parameters: Dict[str, Any]
    priority_tier: PriorityTier = PriorityTier.LEVEL_3_MANUAL_OVERRIDE
    timeout_ms: int = 2500
    reason: Optional[str] = None


class HardwareAck(BaseModel):
    command_id: str
    device_id: str
    endpoint: str
    status: str  # APPLIED, REJECTED_LOCAL_FAULT, HARDWARE_TIMEOUT
    execution_duration_ms: float
    current_state: Dict[str, Any]
    error_code: Optional[str] = None


class HeartbeatPayload(BaseModel):
    device_id: str
    status: str  # ONLINE, OFFLINE_UNEXPECTED, SHUTTING_DOWN
    ip_address: Optional[str] = None
    rssi_dbm: Optional[int] = None
    uptime_seconds: Optional[int] = None
    free_heap_bytes: Optional[int] = None
    firmware_version: Optional[str] = None


# ============================================================================
# 3. DIGITAL TWIN MODELS
# ============================================================================

class SensorState(BaseModel):
    sensor_id: str
    sensor_type: SensorType
    current_value: float
    unit: str
    last_updated: datetime
    is_safety_critical: bool = False


class DeviceState(BaseModel):
    device_id: str
    name: str
    category: DeviceCategory
    is_online: bool
    current_state: Dict[str, Any]
    capabilities: Dict[str, Any]
    health_score: int
    last_seen_at: Optional[datetime] = None


class RoomState(BaseModel):
    room_id: str
    name: str
    room_type: RoomType
    current_temperature: Optional[float] = None
    current_humidity: Optional[float] = None
    current_lux: Optional[float] = None
    occupancy_detected: bool = False
    devices: List[DeviceState] = Field(default_factory=list)
    sensors: List[SensorState] = Field(default_factory=list)


class FloorState(BaseModel):
    floor_id: str
    level_index: int
    name: str
    rooms: List[RoomState] = Field(default_factory=list)


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
    floors: List[FloorState] = Field(default_factory=list)


# ============================================================================
# 4. HOUSE BRAIN & EXPLAINABLE AI CONTRACTS
# ============================================================================

class IntentRequest(BaseModel):
    query_text: str
    dry_run: bool = False


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
    contributing_factors: List[ContributingFactor]
    evaluated_alternatives: Optional[List[str]] = None
    confidence_score: float = Field(..., ge=0.0, le=1.0)


class ProposedAction(BaseModel):
    target_device: str
    endpoint: str
    action: str
    parameters: Dict[str, Any]
    priority_tier: PriorityTier
    reasoning: Optional[DecisionReasoning] = None


class WhatIfImpact(BaseModel):
    projected_power_watts_delta: float
    projected_cost_delta: float
    projected_temp_delta: Dict[str, float] = Field(default_factory=dict)
    conflict_detected: bool = False
    conflict_warning: Optional[str] = None


class IntentResponse(BaseModel):
    intent_id: str
    parsed_intent: str
    confidence: float
    requires_confirmation: bool
    proposed_actions: List[ProposedAction]
    simulation_impact: WhatIfImpact
    explanation: str


# ============================================================================
# 5. HEALTH SCORE & FLIGHT RECORDER
# ============================================================================

class HouseHealthRadar(BaseModel):
    overall_score: int
    safety_score: int
    security_score: int
    energy_score: int
    water_score: int
    device_score: int
    network_score: int
    environment_score: int
    maintenance_score: int
    explanations: List[str]


class BlackboxEvent(BaseModel):
    recorded_at: datetime
    event_id: str
    source_type: str
    source_identity: str
    target_entity: str
    action_verb: str
    previous_state: Optional[Dict[str, Any]] = None
    new_state: Optional[Dict[str, Any]] = None
    priority_level: int
    execution_ms: Optional[float] = None
    status: str
