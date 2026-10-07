from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import DeviceServiceDep
from app.contracts import CommandProposal
from app.database.session import get_db
from app.events.service import event_service
from app.models.device import Command, Device, Sensor, SensorReading
from app.models.domain import Floor, House, Room, User
from app.safety.monitor import safety_monitor
from app.schemas.domain import (
    CommandRead,
    DeviceCommandRequest,
    DeviceCreate,
    DevicePatch,
    DeviceRead,
    SensorCreate,
    SensorRead,
    SensorReadingCreate,
    SensorReadingRead,
)
from app.security.auth import CurrentUser, ensure_house_access, require_permission

router = APIRouter()


@router.get("/houses/{house_id}/devices", response_model=list[DeviceRead])
async def list_devices(
    house_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    room_id: str | None = None,
    device_type: str | None = None,
) -> list[Device]:
    ensure_house_access(user, house_id)
    statement = select(Device).where(Device.house_id == house_id)
    if room_id:
        statement = statement.where(Device.room_id == room_id)
    if device_type:
        statement = statement.where(Device.device_type == device_type)
    return list((await db.scalars(statement.order_by(Device.name))).all())


@router.post("/devices", response_model=DeviceRead, status_code=201)
async def register_device(
    payload: DeviceCreate,
    user: Annotated[User, Depends(require_permission("device:manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Device:
    ensure_house_access(user, payload.house_id)
    if await db.get(House, payload.house_id) is None:
        raise HTTPException(status_code=404, detail="House not found")
    if payload.room_id:
        room = await db.get(Room, payload.room_id)
        floor = await db.get(Floor, room.floor_id) if room else None
        if room is None or floor is None or floor.house_id != payload.house_id:
            raise HTTPException(status_code=422, detail="Room is not part of the house")
    device = Device(
        house_id=payload.house_id,
        room_id=payload.room_id,
        name=payload.name,
        device_type=payload.device_type,
        driver=payload.driver,
        external_id=payload.external_id,
        capabilities=payload.capabilities,
        metadata_json=payload.metadata,
        state={},
        availability="online" if payload.driver == "simulated" else "unknown",
        last_seen_at=datetime.now(UTC) if payload.driver == "simulated" else None,
    )
    db.add(device)
    await db.flush()
    await event_service.append(
        db,
        house_id=device.house_id,
        source=f"user:{user.id}",
        event_type="device.registered",
        message=f"Device {device.name} registered",
        data={"device_id": device.id, "driver": device.driver},
    )
    await db.commit()
    await db.refresh(device)
    return device


@router.patch("/devices/{device_id}", response_model=DeviceRead)
async def update_device(
    device_id: str,
    payload: DevicePatch,
    user: Annotated[User, Depends(require_permission("device:manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Device:
    device = await db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    ensure_house_access(user, device.house_id)
    values = payload.model_dump(exclude_unset=True)
    if "metadata" in values:
        values["metadata_json"] = values.pop("metadata")
    for key, value in values.items():
        setattr(device, key, value)
    await db.commit()
    await db.refresh(device)
    return device


@router.post("/devices/{device_id}/commands", response_model=CommandRead, status_code=202)
async def command_device(
    device_id: str,
    payload: DeviceCommandRequest,
    user: Annotated[User, Depends(require_permission("device:control"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    service: DeviceServiceDep,
) -> Command:
    device = await db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    ensure_house_access(user, device.house_id)
    return await service.issue_command(
        db,
        device,
        action=payload.action,
        parameters=payload.parameters,
        requested_by_id=user.id,
    )


@router.post("/devices/{device_id}/command", response_model=CommandRead, status_code=202)
async def dispatch_device_command(
    device_id: str,
    payload: CommandProposal,
    user: Annotated[User, Depends(require_permission("device:control"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    service: DeviceServiceDep,
) -> Command:
    """Authoritative conflict-engine command endpoint from contracts/openapi.json."""
    device = await db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    ensure_house_access(user, device.house_id)
    return await service.issue_command(
        db,
        device,
        action=payload.action,
        parameters=payload.parameters,
        requested_by_id=user.id,
        endpoint=payload.endpoint,
        priority_tier=payload.priority_tier,
        reason=payload.reason,
    )


@router.get("/commands/{command_id}", response_model=CommandRead)
async def get_command(
    command_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Command:
    command = await db.get(Command, command_id)
    if command is None:
        raise HTTPException(status_code=404, detail="Command not found")
    device = await db.get(Device, command.device_id)
    ensure_house_access(user, device.house_id)
    return command


@router.get("/houses/{house_id}/sensors", response_model=list[SensorRead])
async def list_sensors(
    house_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[Sensor]:
    ensure_house_access(user, house_id)
    return list((await db.scalars(select(Sensor).where(Sensor.house_id == house_id))).all())


@router.post("/sensors", response_model=SensorRead, status_code=201)
async def register_sensor(
    payload: SensorCreate,
    user: Annotated[User, Depends(require_permission("device:manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Sensor:
    ensure_house_access(user, payload.house_id)
    sensor = Sensor(
        house_id=payload.house_id,
        device_id=payload.device_id,
        room_id=payload.room_id,
        name=payload.name,
        sensor_type=payload.sensor_type,
        unit=payload.unit,
        external_id=payload.external_id,
        metadata_json=payload.metadata,
    )
    db.add(sensor)
    await db.commit()
    await db.refresh(sensor)
    return sensor


@router.post("/sensors/{sensor_id}/readings", response_model=SensorReadingRead, status_code=201)
async def ingest_sensor_reading(
    sensor_id: str,
    payload: SensorReadingCreate,
    user: Annotated[User, Depends(require_permission("telemetry:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SensorReading:
    sensor = await db.get(Sensor, sensor_id)
    if sensor is None:
        raise HTTPException(status_code=404, detail="Sensor not found")
    ensure_house_access(user, sensor.house_id)
    reading = SensorReading(
        sensor_id=sensor.id,
        value=payload.value,
        quality=payload.quality,
        recorded_at=payload.recorded_at or datetime.now(UTC),
        raw_payload=payload.raw_payload,
    )
    sensor.last_seen_at = datetime.now(UTC)
    sensor.availability = "online"
    db.add(reading)
    alert = safety_monitor.evaluate(sensor.sensor_type, payload.value)
    if alert:
        await event_service.append(
            db,
            house_id=sensor.house_id,
            source=f"safety:{sensor.id}",
            event_type=alert.event_type,
            severity=alert.severity,
            message=alert.message,
            data={"sensor_id": sensor.id, "value": payload.value},
        )
    await db.commit()
    await db.refresh(reading)
    return reading


@router.get("/sensors/{sensor_id}/readings", response_model=list[SensorReadingRead])
async def sensor_history(
    sensor_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> list[SensorReading]:
    sensor = await db.get(Sensor, sensor_id)
    if sensor is None:
        raise HTTPException(status_code=404, detail="Sensor not found")
    ensure_house_access(user, sensor.house_id)
    return list(
        (
            await db.scalars(
                select(SensorReading)
                .where(SensorReading.sensor_id == sensor_id)
                .order_by(SensorReading.recorded_at.desc())
                .limit(limit)
            )
        ).all()
    )
