import asyncio
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.device import Device, Sensor, SensorReading
from app.models.domain import Floor, House, Room
from app.models.operations import EnergyReading, WaterReading

CATEGORY_MAP = {
    "light": "lighting",
    "fan": "switch",
    "ac": "hvac",
    "smart_plug": "switch",
    "entertainment": "switch",
}


class DigitalTwinStateManager:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory
        self._snapshots: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        self._worker: asyncio.Task[None] | None = None

    async def start(self) -> None:
        await self.load()
        self._worker = asyncio.create_task(self._refresh_loop())

    async def stop(self) -> None:
        if self._worker:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass

    async def load(self) -> None:
        async with self.session_factory() as db:
            houses = list((await db.scalars(select(House))).all())
            floors = list((await db.scalars(select(Floor))).all())
            rooms = list((await db.scalars(select(Room))).all())
            devices = list((await db.scalars(select(Device))).all())
            sensors = list((await db.scalars(select(Sensor))).all())
            readings: dict[str, SensorReading] = {}
            for sensor in sensors:
                latest = await db.scalar(
                    select(SensorReading)
                    .where(SensorReading.sensor_id == sensor.id)
                    .order_by(SensorReading.recorded_at.desc())
                    .limit(1)
                )
                if latest:
                    readings[sensor.id] = latest
            snapshots: dict[str, dict[str, Any]] = {}
            for house in houses:
                house_devices = [item for item in devices if item.house_id == house.id]
                house_sensors = [item for item in sensors if item.house_id == house.id]
                power = sum(float(item.state.get("power_watts", 0)) for item in house_devices)
                energy = await db.scalar(
                    select(EnergyReading.energy_kwh)
                    .where(EnergyReading.house_id == house.id)
                    .order_by(EnergyReading.recorded_at.desc())
                    .limit(1)
                )
                water = await db.scalar(
                    select(WaterReading)
                    .where(WaterReading.house_id == house.id)
                    .order_by(WaterReading.recorded_at.desc())
                    .limit(1)
                )
                snapshots[house.id] = {
                    "house_id": house.id,
                    "name": house.name,
                    "timestamp": datetime.now(UTC),
                    "security_mode": house.security_mode,
                    "health_score": round(
                        sum(item.health_score for item in house_devices) / len(house_devices)
                    )
                    if house_devices
                    else 100,
                    "active_power_watts": power,
                    "daily_energy_kwh": float(energy or 0),
                    "main_tank_level_pct": float(water.tank_level_percent or 0) if water else 0,
                    "water_flow_lpm": float(water.flow_lpm or 0) if water else 0,
                    "floors": [
                        self._floor_state(
                            floor,
                            rooms,
                            house_devices,
                            house_sensors,
                            readings,
                        )
                        for floor in floors
                        if floor.house_id == house.id
                    ],
                }
        async with self._lock:
            self._snapshots = snapshots

    async def snapshot(self, house_id: str) -> dict[str, Any] | None:
        async with self._lock:
            value = self._snapshots.get(house_id)
            return deepcopy(value) if value else None

    async def house_ids(self) -> list[str]:
        async with self._lock:
            return list(self._snapshots)

    @staticmethod
    def _floor_state(
        floor: Floor,
        rooms: list[Room],
        devices: list[Device],
        sensors: list[Sensor],
        readings: dict[str, SensorReading],
    ) -> dict[str, Any]:
        return {
            "floor_id": floor.id,
            "level_index": floor.level,
            "name": floor.name,
            "rooms": [
                DigitalTwinStateManager._room_state(room, devices, sensors, readings)
                for room in rooms
                if room.floor_id == floor.id
            ],
        }

    @staticmethod
    def _room_state(
        room: Room,
        devices: list[Device],
        sensors: list[Sensor],
        readings: dict[str, SensorReading],
    ) -> dict[str, Any]:
        room_sensors = [item for item in sensors if item.room_id == room.id]

        def metric(kind: str) -> float | None:
            sensor = next((item for item in room_sensors if item.sensor_type == kind), None)
            reading = readings.get(sensor.id) if sensor else None
            return reading.value if reading else None

        return {
            "room_id": room.id,
            "name": room.name,
            "room_type": room.room_type,
            "current_temperature": metric("temperature"),
            "current_humidity": metric("humidity"),
            "current_lux": metric("lux"),
            "occupancy_detected": bool(metric("motion")),
            "devices": [
                {
                    "device_id": item.id,
                    "name": item.name,
                    "category": CATEGORY_MAP.get(item.device_type, item.device_type),
                    "is_online": item.availability == "online",
                    "current_state": item.state,
                    "capabilities": {key: True for key in item.capabilities},
                    "health_score": round(item.health_score),
                    "last_seen_at": item.last_seen_at,
                }
                for item in devices
                if item.room_id == room.id
            ],
            "sensors": [
                {
                    "sensor_id": item.id,
                    "sensor_type": item.sensor_type,
                    "current_value": readings[item.id].value if item.id in readings else 0,
                    "unit": item.unit or "",
                    "last_updated": readings[item.id].recorded_at
                    if item.id in readings
                    else item.created_at,
                    "is_safety_critical": item.sensor_type in {"smoke", "gas", "water_leak"},
                }
                for item in room_sensors
            ],
        }

    async def _refresh_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(1)
                await self.load()
            except asyncio.CancelledError:
                return
