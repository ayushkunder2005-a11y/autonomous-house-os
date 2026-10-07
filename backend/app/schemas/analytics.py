from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class EnergyReadingCreate(BaseModel):
    house_id: str
    device_id: str | None = None
    power_watts: float = Field(ge=0)
    energy_kwh: float = Field(default=0, ge=0)
    voltage: float | None = Field(default=None, ge=0)
    current_amps: float | None = Field(default=None, ge=0)
    cost: float | None = Field(default=None, ge=0)
    recorded_at: datetime | None = None


class WaterReadingCreate(BaseModel):
    house_id: str
    sensor_id: str | None = None
    flow_lpm: float | None = Field(default=None, ge=0)
    volume_liters: float = Field(default=0, ge=0)
    tank_level_percent: float | None = Field(default=None, ge=0, le=100)
    pressure_kpa: float | None = Field(default=None, ge=0)
    leak_detected: bool = False
    recorded_at: datetime | None = None


class DashboardHealth(BaseModel):
    house_id: str
    overall_score: float
    status: str
    components: dict[str, dict[str, Any]]
    calculated_at: datetime
