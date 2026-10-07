from datetime import datetime
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.intents import intent_provider
from app.analytics.house import house_analytics
from app.api.dependencies import AutomationEngineDep, DeviceServiceDep
from app.contracts import (
    DigitalTwinSnapshot,
    HouseHealthRadar,
    IntentRequest,
    IntentResponse,
    SecurityMode,
    WhatIfImpact,
)
from app.database.session import get_db
from app.models.device import Device
from app.models.domain import House, User
from app.models.operations import Event, Scene
from app.schemas.domain import SimulationRequest
from app.security.auth import CurrentUser, ensure_house_access, require_permission
from app.security.modes import security_mode_service
from app.services.runtime import Runtime
from app.simulation.service import simulation_service

router = APIRouter()


async def resolve_house(db: AsyncSession, user: User) -> House:
    house = await db.get(House, user.house_id) if user.house_id else None
    if house is None and user.role.name in {"admin", "owner"}:
        house = await db.scalar(select(House).order_by(House.created_at).limit(1))
    if house is None:
        raise HTTPException(status_code=404, detail="No house is assigned")
    ensure_house_access(user, house.id)
    return house


@router.get("/twin/state", response_model=DigitalTwinSnapshot)
async def twin_state(
    request: Request,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    house = await resolve_house(db, user)
    runtime: Runtime = request.app.state.runtime
    snapshot = await runtime.twin.snapshot(house.id)
    if snapshot is None:
        await runtime.twin.load()
        snapshot = await runtime.twin.snapshot(house.id)
    if snapshot is None:
        raise HTTPException(status_code=503, detail="Digital Twin is not ready")
    return snapshot


@router.get("/twin/floors")
async def twin_floors(
    request: Request,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[dict[str, Any]]:
    snapshot = await twin_state(request, user, db)
    return snapshot["floors"]


@router.get("/twin/rooms/{room_id}")
async def twin_room(
    room_id: str,
    request: Request,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    snapshot = await twin_state(request, user, db)
    for floor in snapshot["floors"]:
        for room in floor["rooms"]:
            if room["room_id"] == room_id:
                return room
    raise HTTPException(status_code=404, detail="Room not found")


@router.post("/brain/intent", response_model=IntentResponse)
async def brain_intent(
    payload: IntentRequest,
    request: Request,
    user: Annotated[User, Depends(require_permission("device:control"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    engine: AutomationEngineDep,
) -> IntentResponse:
    house = await resolve_house(db, user)
    parsed = await intent_provider.interpret(payload.query_text)
    actions: list[dict[str, Any]] = []
    scene = None
    if parsed.intent.endswith("_mode"):
        mode = parsed.intent.removesuffix("_mode")
        scene = await db.scalar(
            select(Scene).where(
                Scene.house_id == house.id, Scene.mode == mode, Scene.enabled.is_(True)
            )
        )
        if scene:
            actions = [
                {
                    "target_device": item.get("device_id"),
                    "endpoint": item.get("endpoint", "default"),
                    "action": item.get("action"),
                    "parameters": item.get("parameters", {}),
                    "priority_tier": 4,
                }
                for item in scene.actions
            ]
    rated_delta = 0.0
    snapshot = await request.app.state.runtime.twin.snapshot(house.id)
    device_power: dict[str, float] = {}
    if snapshot:
        for floor in snapshot["floors"]:
            for room in floor["rooms"]:
                for device in room["devices"]:
                    device_power[device["device_id"]] = float(
                        device["current_state"].get("rated_power_watts", 0)
                    )
    for action in actions:
        if str(action["action"]).lower() == "turn_off":
            rated_delta -= device_power.get(action["target_device"], 0)
    if scene and not payload.dry_run and parsed.executable and not parsed.requires_confirmation:
        await engine.execute_scene(db, scene, user.id)
    executable = bool(actions) and parsed.executable
    explanation = parsed.reason or (
        "Validated intent mapped to a configured deterministic scene"
        if executable
        else "No configured execution plan matched this intent"
    )
    return IntentResponse(
        intent_id=f"int_{uuid4()}",
        parsed_intent=parsed.intent.upper(),
        confidence=parsed.confidence,
        requires_confirmation=parsed.requires_confirmation,
        proposed_actions=actions,
        simulation_impact=WhatIfImpact(projected_power_watts_delta=rated_delta),
        explanation=explanation,
    )


@router.get("/health/score", response_model=HouseHealthRadar)
async def contract_health_score(
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> HouseHealthRadar:
    house = await resolve_house(db, user)
    health = await house_analytics.house_health(db, house.id)
    components = health["components"]
    device = round(components["devices"]["score"])
    network = round(components["network"]["score"])
    water = round(components["water"]["score"])
    scores = {
        "safety_score": min(water, 100),
        "security_score": 100,
        "energy_score": 100,
        "water_score": water,
        "device_score": device,
        "sensor_score": device,
        "network_score": network,
        "environment_score": 100,
        "maintenance_score": device,
    }
    return HouseHealthRadar(
        overall_score=round(sum(scores.values()) / len(scores)),
        **scores,
        explanations=[f"{components['devices']['stale_or_offline']} device(s) are stale or offline"]
        if components["devices"]["stale_or_offline"]
        else ["All monitored subsystems are within configured health thresholds"],
    )


class ModeRequest(BaseModel):
    mode: SecurityMode
    pin_code: str | None = Field(default=None, min_length=4, max_length=12)


class EmergencyRequest(BaseModel):
    hazard_type: str = "USER_PANIC"
    source_room: str | None = None


class BrainSimulationRequest(BaseModel):
    scenario_name: str = Field(min_length=1, max_length=120)
    hypothetical_actions: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    duration_hours: float = Field(default=1, gt=0, le=168)


class PumpControlRequest(BaseModel):
    power: bool


@router.get("/security/mode")
async def get_security_mode(
    user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]
) -> dict[str, str]:
    house = await resolve_house(db, user)
    return {"mode": house.security_mode}


@router.post("/security/mode/set")
async def set_security_mode(
    payload: ModeRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    pin_header: Annotated[str | None, Header(alias="X-House-Security-PIN")] = None,
) -> dict[str, str]:
    house = await resolve_house(db, user)
    await security_mode_service.set_mode(
        db, house, user, payload.mode, pin_header or payload.pin_code
    )
    return {"mode": house.security_mode}


@router.post("/emergency/trigger")
async def trigger_emergency(
    payload: EmergencyRequest,
    request: Request,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    house = await resolve_house(db, user)
    runtime: Runtime = request.app.state.runtime
    return await runtime.emergency.trigger(
        db,
        house,
        hazard_type=payload.hazard_type,
        source_room=payload.source_room,
        source=f"user:{user.id}",
    )


@router.post("/emergency/reset")
async def reset_emergency(
    request: Request,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    pin: Annotated[str | None, Header(alias="X-House-Security-PIN")] = None,
) -> dict[str, str]:
    house = await resolve_house(db, user)
    await request.app.state.runtime.emergency.reset(db, house, user, pin)
    return {"mode": house.security_mode}


@router.post("/brain/simulate")
async def brain_simulate(
    payload: BrainSimulationRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    house = await resolve_house(db, user)
    actions = [
        {
            "device_id": item.get("device_id"),
            "action": item.get("action", "set_parameters"),
            "parameters": item.get("parameters", {}),
        }
        for item in payload.hypothetical_actions
    ]
    result = await simulation_service.simulate(
        db,
        SimulationRequest(
            house_id=house.id,
            actions=actions,
            duration_hours=payload.duration_hours,
        ),
    )
    return {"scenario_name": payload.scenario_name, **result}


@router.get("/energy/live")
async def energy_live(
    user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]
) -> dict[str, Any]:
    house = await resolve_house(db, user)
    summary = await house_analytics.energy_summary(db, house.id, 24)
    return {
        "active_power_watts": summary["current_power_watts"],
        "daily_energy_kwh": summary["energy_kwh"],
        "estimated_cost": summary["estimated_cost"],
        "phase_balance": {},
        "top_consumers": sorted(
            summary["by_device_kwh"].items(), key=lambda item: item[1], reverse=True
        )[:5],
        "anomaly": summary["anomaly"],
    }


@router.get("/water/live")
async def water_live(
    user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]
) -> dict[str, Any]:
    house = await resolve_house(db, user)
    return await house_analytics.water_summary(db, house.id, 24)


@router.post("/water/pump/control", status_code=202)
async def control_water_pump(
    payload: PumpControlRequest,
    user: Annotated[User, Depends(require_permission("device:control"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    devices: DeviceServiceDep,
) -> dict[str, Any]:
    house = await resolve_house(db, user)
    pump = await db.scalar(
        select(Device).where(Device.house_id == house.id, Device.device_type == "pump").limit(1)
    )
    if pump is None:
        raise HTTPException(status_code=404, detail="No water pump is registered")
    command = await devices.issue_command(
        db,
        pump,
        action="turn_on" if payload.power else "turn_off",
        parameters={},
        requested_by_id=user.id,
        endpoint="pump_relay",
        reason="Manual water pump control",
    )
    return {"command_id": command.correlation_id, "status": command.status}


@router.get("/blackbox/query")
async def query_blackbox(
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    entity_id: str | None = None,
    severity: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    house = await resolve_house(db, user)
    statement = select(Event).where(Event.house_id == house.id)
    if start_time:
        statement = statement.where(Event.occurred_at >= start_time)
    if end_time:
        statement = statement.where(Event.occurred_at <= end_time)
    if entity_id:
        statement = statement.where(Event.source.contains(entity_id))
    if severity:
        statement = statement.where(Event.severity == severity)
    events = list(
        (
            await db.scalars(statement.order_by(Event.occurred_at.desc()).limit(min(limit, 500)))
        ).all()
    )
    return [
        {
            "recorded_at": event.occurred_at,
            "event_id": event.id,
            "source_type": event.source.split(":", 1)[0],
            "source_identity": event.source,
            "target_entity": event.data.get("device_id", event.house_id),
            "action_verb": event.event_type,
            "previous_state": event.data.get("previous_state"),
            "new_state": event.data.get("new_state", event.data.get("state")),
            "priority_level": event.data.get("priority_tier", 6),
            "status": event.severity,
        }
        for event in events
    ]
