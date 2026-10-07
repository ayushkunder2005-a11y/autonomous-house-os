from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.house import house_analytics
from app.database.session import get_db
from app.events.service import event_service
from app.models.device import Device, DeviceHealth
from app.models.domain import User
from app.models.operations import EnergyReading, MaintenanceRecord, WaterReading
from app.schemas.analytics import DashboardHealth, EnergyReadingCreate, WaterReadingCreate
from app.schemas.domain import MaintenanceCreate, MaintenanceRead, MemoryQuery
from app.security.auth import CurrentUser, ensure_house_access, require_permission

router = APIRouter()


@router.post("/energy/readings", status_code=201)
async def create_energy_reading(
    payload: EnergyReadingCreate,
    user: Annotated[User, Depends(require_permission("telemetry:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    ensure_house_access(user, payload.house_id)
    reading = EnergyReading(
        **payload.model_dump(exclude={"recorded_at"}),
        recorded_at=payload.recorded_at or datetime.now(UTC),
    )
    db.add(reading)
    await db.commit()
    return {"id": reading.id, "recorded_at": reading.recorded_at}


@router.get("/houses/{house_id}/energy")
async def energy_summary(
    house_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    hours: Annotated[int, Query(ge=1, le=8760)] = 24,
) -> dict[str, Any]:
    ensure_house_access(user, house_id)
    return await house_analytics.energy_summary(db, house_id, hours)


@router.post("/water/readings", status_code=201)
async def create_water_reading(
    payload: WaterReadingCreate,
    user: Annotated[User, Depends(require_permission("telemetry:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    ensure_house_access(user, payload.house_id)
    reading = WaterReading(
        **payload.model_dump(exclude={"recorded_at"}),
        recorded_at=payload.recorded_at or datetime.now(UTC),
    )
    db.add(reading)
    if payload.leak_detected:
        await event_service.append(
            db,
            house_id=payload.house_id,
            source="water:meter",
            event_type="emergency.water_leak",
            severity="critical",
            message="Water leak reported by meter",
            data={"sensor_id": payload.sensor_id, "flow_lpm": payload.flow_lpm},
        )
    await db.commit()
    return {"id": reading.id, "recorded_at": reading.recorded_at}


@router.get("/houses/{house_id}/water")
async def water_summary(
    house_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    hours: Annotated[int, Query(ge=1, le=8760)] = 24,
) -> dict[str, Any]:
    ensure_house_access(user, house_id)
    return await house_analytics.water_summary(db, house_id, hours)


@router.get("/houses/{house_id}/health", response_model=DashboardHealth)
async def health_dashboard(
    house_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    ensure_house_access(user, house_id)
    return await house_analytics.house_health(db, house_id)


@router.post("/memory/search")
async def search_memory(
    payload: MemoryQuery,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    ensure_house_access(user, payload.house_id)
    items = await house_analytics.search_memory(db, payload.house_id, payload.query, payload.limit)
    return {"query": payload.query, "items": items}


@router.get("/houses/{house_id}/events")
async def recent_events(
    house_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[dict[str, Any]]:
    ensure_house_access(user, house_id)
    events = await house_analytics.recent_events(db, house_id, limit)
    return [
        {
            "id": item.id,
            "source": item.source,
            "event_type": item.event_type,
            "severity": item.severity,
            "message": item.message,
            "data": item.data,
            "occurred_at": item.occurred_at,
            "correlation_id": item.correlation_id,
            "integrity_hash": item.integrity_hash,
        }
        for item in events
    ]


@router.get("/audit/integrity")
async def verify_event_integrity(
    user: Annotated[User, Depends(require_permission("audit:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    valid, broken_event_id = await event_service.verify_chain(db)
    return {"valid": valid, "broken_event_id": broken_event_id}


@router.get("/devices/{device_id}/health-history")
async def device_health_history(
    device_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[dict[str, Any]]:
    device = await db.get(Device, device_id)
    if device is None:
        return []
    ensure_house_access(user, device.house_id)
    items = list(
        (
            await db.scalars(
                select(DeviceHealth)
                .where(DeviceHealth.device_id == device_id)
                .order_by(DeviceHealth.recorded_at.desc())
                .limit(limit)
            )
        ).all()
    )
    return [
        {
            "status": item.status,
            "score": item.score,
            "response_time_ms": item.response_time_ms,
            "mqtt_connected": item.mqtt_connected,
            "failure_count": item.failure_count,
            "details": item.details,
            "recorded_at": item.recorded_at,
        }
        for item in items
    ]


@router.get("/devices/{device_id}/maintenance", response_model=list[MaintenanceRead])
async def maintenance_history(
    device_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[MaintenanceRecord]:
    device = await db.get(Device, device_id)
    if device is None:
        return []
    ensure_house_access(user, device.house_id)
    return list(
        (
            await db.scalars(
                select(MaintenanceRecord)
                .where(MaintenanceRecord.device_id == device_id)
                .order_by(MaintenanceRecord.created_at.desc())
            )
        ).all()
    )


@router.post("/devices/{device_id}/maintenance", response_model=MaintenanceRead, status_code=201)
async def create_maintenance_record(
    device_id: str,
    payload: MaintenanceCreate,
    user: Annotated[User, Depends(require_permission("device:manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MaintenanceRecord:
    device = await db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    ensure_house_access(user, device.house_id)
    now = datetime.now(UTC)
    record = MaintenanceRecord(
        device_id=device_id,
        **payload.model_dump(),
        recommended_at=now if payload.status == "recommended" else None,
        completed_at=now if payload.status == "completed" else None,
    )
    db.add(record)
    await event_service.append(
        db,
        house_id=device.house_id,
        source=f"user:{user.id}",
        event_type="maintenance.recorded",
        message=f"Maintenance {payload.maintenance_type} recorded for {device.name}",
        data={"device_id": device_id, "status": payload.status},
    )
    await db.commit()
    await db.refresh(record)
    return record
