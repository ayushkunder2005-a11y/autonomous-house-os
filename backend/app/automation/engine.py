import asyncio
from datetime import UTC, datetime
from operator import eq, ge, gt, le, lt, ne
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.contracts import PriorityTier
from app.devices.service import DeviceService
from app.events.service import event_service
from app.models.device import Device, SensorReading
from app.models.operations import Automation, Scene
from app.mqtt.bus import MessageBus
from app.mqtt.topics import parse_topic

OPERATORS = {"eq": eq, "ne": ne, "gt": gt, "gte": ge, "lt": lt, "lte": le}


class AutomationEngine:
    def __init__(
        self,
        device_service: DeviceService,
        session_factory: async_sessionmaker[AsyncSession],
        bus: MessageBus,
    ) -> None:
        self.device_service = device_service
        self.session_factory = session_factory
        self.bus = bus
        self._scheduler: asyncio.Task[None] | None = None

    async def start(self) -> None:
        await self.bus.subscribe("house/+/room/+/device/+/state", self._on_event)
        await self.bus.subscribe("house/+/sensor/+/data", self._on_event)
        self._scheduler = asyncio.create_task(self._schedule_loop())

    async def stop(self) -> None:
        if self._scheduler:
            self._scheduler.cancel()
            try:
                await self._scheduler
            except asyncio.CancelledError:
                pass

    async def execute(
        self, db: AsyncSession, automation: Automation, requested_by_id: str | None
    ) -> list[str]:
        if not automation.enabled:
            raise HTTPException(status_code=409, detail="Automation is disabled")
        if not await self._conditions_match(db, automation.conditions):
            await event_service.append(
                db,
                house_id=automation.house_id,
                source=f"automation:{automation.id}",
                event_type="automation.skipped",
                message=f"Automation {automation.name} conditions were not met",
            )
            await db.commit()
            return []
        self._validate_action_conflicts(automation.actions)
        command_ids: list[str] = []
        failures: list[str] = []
        for action in automation.actions:
            try:
                device = await db.get(Device, action.get("device_id"))
                if device is None or device.house_id != automation.house_id:
                    raise ValueError("Device not found in automation house")
                command = await self.device_service.issue_command(
                    db,
                    device,
                    action=str(action.get("action", "")),
                    parameters=action.get("parameters", {}),
                    requested_by_id=requested_by_id,
                    endpoint=str(action.get("endpoint", "default")),
                    priority_tier=PriorityTier(automation.priority),
                    reason=f"Automation: {automation.name}",
                    source=f"automation:{automation.id}",
                )
                command_ids.append(command.id)
            except Exception as exc:
                failures.append(str(exc))
                if automation.failure_policy != "continue":
                    break
        automation.last_run_at = datetime.now(UTC)
        await event_service.append(
            db,
            house_id=automation.house_id,
            source=f"automation:{automation.id}",
            event_type="automation.executed",
            severity="warning" if failures else "info",
            message=f"Automation {automation.name} executed",
            data={"command_ids": command_ids, "failures": failures},
        )
        await db.commit()
        if failures and not command_ids:
            raise HTTPException(status_code=422, detail={"failures": failures})
        return command_ids

    async def execute_scene(
        self, db: AsyncSession, scene: Scene, requested_by_id: str | None
    ) -> list[str]:
        if not scene.enabled:
            raise HTTPException(status_code=409, detail="Scene is disabled")
        self._validate_action_conflicts(scene.actions)
        command_ids: list[str] = []
        for action in scene.actions:
            device = await db.get(Device, action.get("device_id"))
            if device is None or device.house_id != scene.house_id:
                raise HTTPException(status_code=422, detail="Scene contains an invalid device")
            command = await self.device_service.issue_command(
                db,
                device,
                action=str(action.get("action", "")),
                parameters=action.get("parameters", {}),
                requested_by_id=requested_by_id,
                endpoint=str(action.get("endpoint", "default")),
                priority_tier=PriorityTier.LEVEL_4_SCHEDULE_INTENT,
                reason=f"Scene: {scene.name}",
                source=f"scene:{scene.id}",
            )
            command_ids.append(command.id)
        await event_service.append(
            db,
            house_id=scene.house_id,
            source=f"scene:{scene.id}",
            event_type="scene.executed",
            message=f"Scene {scene.name} executed",
            data={"command_ids": command_ids},
        )
        await db.commit()
        return command_ids

    async def _conditions_match(self, db: AsyncSession, conditions: list[dict[str, Any]]) -> bool:
        for condition in conditions:
            operator = OPERATORS.get(str(condition.get("operator", "eq")))
            if operator is None:
                return False
            actual: Any = None
            if condition.get("source") == "device":
                device = await db.get(Device, condition.get("device_id"))
                actual = device.state.get(condition.get("field")) if device else None
            elif condition.get("source") == "sensor":
                reading = await db.scalar(
                    select(SensorReading)
                    .where(SensorReading.sensor_id == condition.get("sensor_id"))
                    .order_by(SensorReading.recorded_at.desc())
                    .limit(1)
                )
                actual = reading.value if reading else None
            else:
                return False
            try:
                if not operator(actual, condition.get("value")):
                    return False
            except TypeError:
                return False
        return True

    @staticmethod
    def _validate_action_conflicts(actions: list[dict[str, Any]]) -> None:
        targets: dict[str, tuple[str, str]] = {}
        for action in actions:
            device_id = str(action.get("device_id", ""))
            signature = (str(action.get("action", "")), repr(action.get("parameters", {})))
            if device_id in targets and targets[device_id] != signature:
                raise HTTPException(
                    status_code=409, detail=f"Conflicting actions target device {device_id}"
                )
            targets[device_id] = signature

    async def _on_event(self, topic: str, payload: dict[str, Any]) -> None:
        parsed = parse_topic(topic)
        if parsed is None:
            return
        async with self.session_factory() as db:
            automations = list(
                (
                    await db.scalars(
                        select(Automation).where(
                            Automation.house_id == parsed.house_id,
                            Automation.enabled.is_(True),
                            Automation.trigger_type == "event",
                        )
                    )
                ).all()
            )
            for automation in automations:
                config = automation.trigger_config
                if config.get("device_id") and config["device_id"] != parsed.device_id:
                    continue
                if config.get("sensor_id") and config["sensor_id"] != parsed.sensor_id:
                    continue
                cooldown = max(1, int(config.get("cooldown_seconds", 5)))
                last_run = automation.last_run_at
                if last_run:
                    if last_run.tzinfo is None:
                        last_run = last_run.replace(tzinfo=UTC)
                    if (datetime.now(UTC) - last_run).total_seconds() < cooldown:
                        continue
                try:
                    await self.execute(db, automation, None)
                except HTTPException:
                    continue

    async def _schedule_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(1)
                now = datetime.now(UTC)
                async with self.session_factory() as db:
                    automations = list(
                        (
                            await db.scalars(
                                select(Automation).where(
                                    Automation.enabled.is_(True),
                                    Automation.trigger_type == "schedule",
                                )
                            )
                        ).all()
                    )
                    for automation in automations:
                        interval = int(automation.trigger_config.get("interval_seconds", 0))
                        if interval < 5:
                            continue
                        last_run = automation.last_run_at
                        if last_run and last_run.tzinfo is None:
                            last_run = last_run.replace(tzinfo=UTC)
                        if last_run is None or (now - last_run).total_seconds() >= interval:
                            try:
                                await self.execute(db, automation, None)
                            except HTTPException:
                                continue
            except asyncio.CancelledError:
                return
