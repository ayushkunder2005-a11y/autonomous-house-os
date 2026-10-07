import math
import random
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import Runtime, get_runtime
from app.database.session import get_db
from app.models.device import Device, Sensor
from app.models.domain import Floor, House, Room, User
from app.models.operations import Scene
from app.mqtt.topics import telemetry_topic
from app.schemas.domain import SimulationRequest
from app.security.auth import ensure_house_access, require_permission
from app.simulation.service import simulation_service

router = APIRouter()


@router.post("/house")
async def simulate_house(
    payload: SimulationRequest,
    user: Annotated[User, Depends(require_permission("device:control"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    ensure_house_access(user, payload.house_id)
    return await simulation_service.simulate(db, payload)


@router.post("/bootstrap", status_code=201)
async def bootstrap_simulation(
    user: Annotated[User, Depends(require_permission("house:manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    house = House(name="Simulation House", timezone="Asia/Kolkata")
    db.add(house)
    await db.flush()
    floor = Floor(house_id=house.id, name="Ground Floor", level=0)
    db.add(floor)
    await db.flush()
    living = Room(floor_id=floor.id, name="Living Room", room_type="living_room")
    bedroom = Room(floor_id=floor.id, name="Bedroom", room_type="bedroom")
    kitchen = Room(floor_id=floor.id, name="Kitchen", room_type="kitchen")
    db.add_all([living, bedroom, kitchen])
    await db.flush()

    definitions = [
        ("Living Room Bulb", "light", living.id, ["power", "brightness"], 10),
        ("Living Room Fan", "fan", living.id, ["power", "speed"], 70),
        ("Bedroom AC", "ac", bedroom.id, ["power", "temperature"], 1500),
        ("Bedroom Curtains", "curtain", bedroom.id, ["position"], 40),
        ("Front Door Lock", "lock", living.id, ["lock"], 5),
        ("Kitchen Plug", "smart_plug", kitchen.id, ["power"], 100),
        ("Water Pump", "pump", kitchen.id, ["power"], 750),
        ("Energy Meter", "energy_meter", living.id, ["state"], 1),
    ]
    devices: list[Device] = []
    for name, kind, room_id, capabilities, watts in definitions:
        state: dict[str, Any] = {"power": "off"} if "power" in capabilities else {}
        if kind == "ac":
            state["temperature"] = 24
        device = Device(
            house_id=house.id,
            room_id=room_id,
            name=name,
            device_type=kind,
            driver="simulated",
            state=state,
            capabilities=capabilities,
            availability="online",
            last_seen_at=datetime.now(UTC),
            metadata_json={"rated_power_watts": watts},
        )
        db.add(device)
        devices.append(device)
    await db.flush()

    sensor_definitions = [
        ("Living Temperature", "temperature", living.id, "°C", 25.0),
        ("Living Humidity", "humidity", living.id, "%", 55.0),
        ("Living Motion", "motion", living.id, None, 0.0),
        ("Hallway Smoke", "smoke", living.id, None, 0.0),
        ("Kitchen Water Leak", "water_leak", kitchen.id, None, 0.0),
        ("Whole House Power", "power_w", living.id, "W", 250.0),
    ]
    sensors: list[Sensor] = []
    for index, (name, kind, room_id, unit, baseline) in enumerate(sensor_definitions):
        sensor = Sensor(
            house_id=house.id,
            device_id=devices[min(index, len(devices) - 1)].id,
            room_id=room_id,
            name=name,
            sensor_type=kind,
            unit=unit,
            availability="online",
            last_seen_at=datetime.now(UTC),
            metadata_json={"simulation_baseline": baseline},
        )
        db.add(sensor)
        sensors.append(sensor)
    await db.flush()

    sleep_actions = [
        {"device_id": device.id, "action": "turn_off", "parameters": {}}
        for device in devices
        if "power" in device.capabilities and device.device_type != "ac"
    ]
    sleep_actions.append(
        {
            "device_id": next(device.id for device in devices if device.device_type == "curtain"),
            "action": "close",
            "parameters": {},
        }
    )
    db.add(Scene(house_id=house.id, name="Sleep Mode", mode="sleep", actions=sleep_actions))
    await db.commit()
    return {
        "house_id": house.id,
        "floor_id": floor.id,
        "room_ids": [living.id, bedroom.id, kitchen.id],
        "device_ids": [device.id for device in devices],
        "sensor_ids": [sensor.id for sensor in sensors],
    }


@router.post("/{house_id}/tick")
async def simulation_tick(
    house_id: str,
    user: Annotated[User, Depends(require_permission("telemetry:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    runtime: Annotated[Runtime, Depends(get_runtime)],
) -> dict[str, Any]:
    ensure_house_access(user, house_id)
    sensors = list((await db.scalars(select(Sensor).where(Sensor.house_id == house_id))).all())
    tick = datetime.now(UTC).timestamp()
    published = 0
    for sensor in sensors:
        baseline = float(sensor.metadata_json.get("simulation_baseline", 0))
        if sensor.sensor_type in {"motion", "smoke", "water_leak"}:
            value = 1.0 if random.random() < 0.02 else 0.0
        else:
            value = baseline + math.sin(tick / 60) * baseline * 0.02 + random.uniform(-0.5, 0.5)
        envelope = {
            "timestamp": int(datetime.now(UTC).timestamp() * 1000),
            "sensor_id": sensor.id,
            "device_id": sensor.device_id,
            "metric_type": sensor.sensor_type,
            "value": round(value, 2),
            "unit": sensor.unit or "bool",
            "read_seq": int(tick),
            "status": "VALID",
        }
        if await runtime.bus.publish(
            telemetry_topic(
                house_id,
                "ground",
                sensor.room_id or "unknown",
                sensor.device_id or "unknown",
                sensor.id,
            ),
            envelope,
            qos=1,
        ):
            published += 1
    return {"house_id": house_id, "published": published}
