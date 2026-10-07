from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORMModel


class HouseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    timezone: str = Field(default="UTC", min_length=1, max_length=64)


class HouseRead(ORMModel):
    id: str
    name: str
    timezone: str
    created_at: datetime


class FloorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    level: int = 0


class FloorRead(ORMModel):
    id: str
    house_id: str
    name: str
    level: int


class RoomCreate(BaseModel):
    floor_id: str
    name: str = Field(min_length=1, max_length=120)
    room_type: str = Field(default="general", max_length=50)


class RoomRead(ORMModel):
    id: str
    floor_id: str
    name: str
    room_type: str


class DeviceCreate(BaseModel):
    house_id: str
    room_id: str | None = None
    name: str = Field(min_length=1, max_length=120)
    device_type: str = Field(min_length=1, max_length=50)
    driver: Literal["mqtt", "simulated"] = "mqtt"
    external_id: str | None = Field(default=None, max_length=120)
    capabilities: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DevicePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    room_id: str | None = None
    capabilities: list[str] | None = None
    metadata: dict[str, Any] | None = None


class DeviceRead(ORMModel):
    id: str
    house_id: str
    room_id: str | None
    name: str
    device_type: str
    driver: str
    external_id: str | None
    state: dict[str, Any]
    capabilities: list[str]
    availability: str
    last_seen_at: datetime | None
    health_score: float
    metadata_json: dict[str, Any]


class DeviceCommandRequest(BaseModel):
    action: str = Field(min_length=1, max_length=80)
    parameters: dict[str, Any] = Field(default_factory=dict)


class CommandRead(ORMModel):
    id: str
    device_id: str
    action: str
    endpoint: str
    priority_tier: int
    reason: str | None
    parameters: dict[str, Any]
    expected_state: dict[str, Any]
    status: str
    attempt_count: int
    correlation_id: str
    acknowledged_at: datetime | None
    completed_at: datetime | None
    error: str | None
    created_at: datetime


class StateReport(BaseModel):
    state: dict[str, Any]
    correlation_id: str | None = None
    reported_at: datetime | None = None


class Acknowledgement(BaseModel):
    correlation_id: str
    status: Literal["accepted", "completed", "rejected", "failed"]
    error: str | None = None


class SensorCreate(BaseModel):
    house_id: str
    device_id: str | None = None
    room_id: str | None = None
    name: str = Field(min_length=1, max_length=120)
    sensor_type: str = Field(min_length=1, max_length=50)
    unit: str | None = Field(default=None, max_length=30)
    external_id: str | None = Field(default=None, max_length=120)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SensorRead(ORMModel):
    id: str
    house_id: str
    device_id: str | None
    room_id: str | None
    name: str
    sensor_type: str
    unit: str | None
    availability: str
    last_seen_at: datetime | None


class SensorReadingCreate(BaseModel):
    value: float
    quality: Literal["good", "uncertain", "bad"] = "good"
    recorded_at: datetime | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class SensorReadingRead(ORMModel):
    id: str
    sensor_id: str
    value: float
    quality: str
    recorded_at: datetime


class AutomationCreate(BaseModel):
    house_id: str
    name: str = Field(min_length=1, max_length=120)
    trigger_type: Literal["manual", "event", "schedule"]
    trigger_config: dict[str, Any] = Field(default_factory=dict)
    conditions: list[dict[str, Any]] = Field(default_factory=list)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    priority: int = Field(default=4, ge=0, le=6)
    failure_policy: Literal["stop", "continue", "rollback"] = "stop"
    enabled: bool = True


class AutomationRead(ORMModel):
    id: str
    house_id: str
    name: str
    enabled: bool
    trigger_type: str
    trigger_config: dict[str, Any]
    conditions: list[dict[str, Any]]
    actions: list[dict[str, Any]]
    priority: int
    failure_policy: str
    last_run_at: datetime | None


class SceneCreate(BaseModel):
    house_id: str
    name: str = Field(min_length=1, max_length=120)
    mode: str | None = None
    actions: list[dict[str, Any]] = Field(default_factory=list)
    enabled: bool = True


class SceneRead(ORMModel):
    id: str
    house_id: str
    name: str
    mode: str | None
    actions: list[dict[str, Any]]
    enabled: bool


class NaturalLanguageCommand(BaseModel):
    house_id: str
    text: str = Field(min_length=1, max_length=500)
    execute: bool = False


class StructuredIntent(BaseModel):
    intent: str
    scope: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    requires_confirmation: bool
    confidence: float = Field(ge=0, le=1)
    executable: bool
    reason: str | None = None


class SimulationRequest(BaseModel):
    house_id: str
    text: str | None = Field(default=None, max_length=500)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    tariff_per_kwh: float = Field(default=0.15, ge=0)
    duration_hours: float = Field(default=1.0, gt=0, le=168)

    @field_validator("actions")
    @classmethod
    def action_limit(cls, value: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if len(value) > 100:
            raise ValueError("at most 100 actions may be simulated")
        return value


class MemoryQuery(BaseModel):
    house_id: str
    query: str = Field(min_length=1, max_length=300)
    limit: int = Field(default=20, ge=1, le=100)


class MaintenanceCreate(BaseModel):
    maintenance_type: str = Field(min_length=1, max_length=80)
    notes: str = Field(default="", max_length=2000)
    operating_hours: float = Field(default=0, ge=0)
    failure_count: int = Field(default=0, ge=0)
    health_score: float = Field(default=100, ge=0, le=100)
    status: Literal["recommended", "scheduled", "in_progress", "completed", "deferred"] = (
        "recommended"
    )


class MaintenanceRead(ORMModel):
    id: str
    device_id: str
    status: str
    maintenance_type: str
    notes: str
    operating_hours: float
    failure_count: int
    health_score: float
    recommended_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
