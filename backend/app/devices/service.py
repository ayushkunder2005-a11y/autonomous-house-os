import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.contracts import (
    CommandDispatch,
    HardwareAck,
    HeartbeatPayload,
    PriorityTier,
    SecurityMode,
    TelemetryPayload,
)
from app.core.config import Settings
from app.devices.safety import safety_validator
from app.engine.priority.arbitrator import priority_arbitrator
from app.events.service import event_service
from app.models.device import Command, Device, DeviceHealth, DeviceState, Sensor, SensorReading
from app.models.domain import House
from app.mqtt.bus import MessageBus
from app.mqtt.topics import command_topic, parse_topic
from app.realtime.manager import realtime_manager
from app.safety.monitor import safety_monitor
from app.security.modes import EmergencyService
from app.transport.redis_bus import RedisEventPipeline


def expected_state_for(action: str, parameters: dict[str, Any]) -> dict[str, Any]:
    normalized = action.lower()
    mappings = {
        "turn_on": {"power": parameters.get("power", "on")},
        "turn_off": {"power": parameters.get("power", "off")},
        "open": {"position": parameters.get("position", "open")},
        "close": {"position": parameters.get("position", "closed")},
        "lock": {"locked": True},
        "unlock": {"locked": False},
        "set_brightness": {"brightness": parameters.get("brightness")},
        "set_temperature": {"temperature": parameters.get("temperature")},
        "set_speed": {"speed": parameters.get("speed")},
        "set_state": parameters.get("state", parameters),
        "set_parameters": parameters,
        "set_position": parameters,
        "force_shutoff": {"power": "off"},
        "force_off": {"power": "off"},
    }
    expected = mappings.get(normalized, parameters)
    return {key: value for key, value in expected.items() if value is not None}


def state_contains(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    def equivalent(left: Any, right: Any) -> bool:
        if isinstance(left, str) and isinstance(right, str):
            return left.lower() == right.lower()
        return left == right

    return all(equivalent(actual.get(key), value) for key, value in expected.items())


class DeviceService:
    def __init__(
        self,
        bus: MessageBus,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        event_pipeline: RedisEventPipeline | None = None,
        emergency_service: EmergencyService | None = None,
    ) -> None:
        self.bus = bus
        self.session_factory = session_factory
        self.settings = settings
        self.event_pipeline = event_pipeline
        self.emergency_service = emergency_service
        self._timeouts: dict[str, asyncio.Task[None]] = {}

    async def start(self) -> None:
        await self.bus.subscribe("house/+/state/+/+", self.handle_message)
        await self.bus.subscribe("house/+/ack/+/+", self.handle_message, qos=2)
        await self.bus.subscribe("house/+/heartbeat/+", self.handle_message)
        await self.bus.subscribe("house/+/telemetry/+/+/+/+", self.handle_message)

    async def stop(self) -> None:
        for task in self._timeouts.values():
            task.cancel()
        self._timeouts.clear()

    async def issue_command(
        self,
        db: AsyncSession,
        device: Device,
        *,
        action: str,
        parameters: dict[str, Any],
        requested_by_id: str | None,
        endpoint: str = "default",
        priority_tier: PriorityTier = PriorityTier.LEVEL_3_MANUAL_OVERRIDE,
        reason: str | None = None,
        source: str | None = None,
    ) -> Command:
        verdict = safety_validator.validate(device, action, parameters)
        if not verdict.allowed:
            raise HTTPException(status_code=422, detail=verdict.reason)
        house = await db.get(House, device.house_id)
        mode = SecurityMode(house.security_mode) if house else SecurityMode.HOME
        authority = source or (f"user:{requested_by_id}" if requested_by_id else "automation")
        arbitration = await priority_arbitrator.evaluate(
            db,
            device=device,
            endpoint=endpoint,
            action=action,
            parameters=parameters,
            tier=priority_tier,
            source=authority,
            security_mode=mode,
        )
        if not arbitration.approved:
            await db.commit()
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "COMMAND_PREEMPTED",
                    "reason": arbitration.reason,
                    "winning_source": arbitration.preempted_source,
                },
            )
        command_id = str(uuid4())
        command = Command(
            device_id=device.id,
            requested_by_id=requested_by_id,
            action=action,
            endpoint=endpoint,
            priority_tier=int(priority_tier),
            reason=reason,
            parameters=arbitration.effective_parameters,
            expected_state=expected_state_for(action, arbitration.effective_parameters),
            correlation_id=command_id,
            status="pending",
        )
        db.add(command)
        await event_service.append(
            db,
            house_id=device.house_id,
            source=authority,
            event_type="device.command.requested",
            message=f"Command {action} requested for {device.name}",
            data={
                "device_id": device.id,
                "endpoint": endpoint,
                "action": action,
                "parameters": parameters,
                "priority_tier": int(priority_tier),
                "reason": reason,
            },
            correlation_id=command_id,
        )
        await db.commit()
        await self._publish_attempt(command, device)
        self._schedule_timeout(command.id, command_id)
        await db.refresh(command)
        return command

    async def _publish_attempt(self, command: Command, device: Device) -> None:
        command.attempt_count += 1
        payload = CommandDispatch(
            command_id=command.correlation_id,
            timestamp=int(datetime.now(UTC).timestamp() * 1000),
            device_id=device.id,
            endpoint=command.endpoint,
            action=command.action,
            parameters=command.parameters,
            priority_tier=PriorityTier(command.priority_tier),
            timeout_ms=max(100, int(self.settings.command_timeout_seconds * 1000)),
            reason=command.reason,
        ).model_dump(mode="json")
        topic = command_topic(device.house_id, device.id, command.endpoint)
        published = await self.bus.publish(topic, payload, qos=2)
        if not published and self.event_pipeline:
            await self.event_pipeline.queue_command({"topic": topic, "payload": payload, "qos": 2})
        async with self.session_factory() as db:
            stored = await db.get(Command, command.id)
            if stored:
                stored.attempt_count = command.attempt_count
                if not published:
                    stored.status = "transport_unavailable"
                    stored.error = "Message bus is not connected"
                elif stored.status in {"pending", "retrying", "transport_unavailable"}:
                    stored.status = "sent"
                await db.commit()

    def _schedule_timeout(self, command_id: str, correlation_id: str) -> None:
        old = self._timeouts.pop(correlation_id, None)
        if old:
            old.cancel()
        self._timeouts[correlation_id] = asyncio.create_task(
            self._handle_timeout(command_id, correlation_id)
        )

    async def _handle_timeout(self, command_id: str, correlation_id: str) -> None:
        try:
            await asyncio.sleep(self.settings.command_timeout_seconds)
            async with self.session_factory() as db:
                command = await db.get(Command, command_id)
                if command is None or command.status in {"completed", "failed", "rejected"}:
                    return
                device = await db.get(Device, command.device_id)
                if device is None:
                    return
                if command.attempt_count <= self.settings.command_max_retries:
                    command.status = "retrying"
                    await db.commit()
                    await self._publish_attempt(command, device)
                    self._schedule_timeout(command.id, correlation_id)
                    return
                command.status = "failed"
                command.error = "Hardware acknowledgement/state verification timed out"
                device.health_score = max(0, device.health_score - 10)
                await event_service.append(
                    db,
                    house_id=device.house_id,
                    source=f"device:{device.id}",
                    event_type="device.command.failed",
                    severity="warning",
                    message=f"Command {command.action} timed out for {device.name}",
                    correlation_id=correlation_id,
                )
                await db.commit()
        except asyncio.CancelledError:
            return
        finally:
            if self._timeouts.get(correlation_id) is asyncio.current_task():
                self._timeouts.pop(correlation_id, None)

    async def handle_message(self, topic: str, payload: dict[str, Any]) -> None:
        parsed = parse_topic(topic)
        if parsed is None:
            return
        try:
            if parsed.kind == "state" and parsed.device_id:
                await self.ingest_state(parsed.house_id, parsed.device_id, payload)
            elif parsed.kind == "ack" and parsed.device_id:
                await self.ingest_ack(parsed.house_id, parsed.device_id, payload)
            elif parsed.kind == "heartbeat" and parsed.device_id:
                await self.ingest_heartbeat(parsed.house_id, payload)
            elif parsed.kind == "telemetry" and parsed.sensor_id:
                await self.ingest_sensor(parsed.house_id, TelemetryPayload.model_validate(payload))
        except ValidationError:
            return

    async def ingest_state(self, house_id: str, device_id: str, payload: dict[str, Any]) -> None:
        state = payload.get("state")
        if not isinstance(state, dict) or payload.get("device_id") != device_id:
            return
        await self._record_state(house_id, device_id, state, None, "mqtt_state")

    async def ingest_ack(self, house_id: str, device_id: str, payload: dict[str, Any]) -> None:
        ack = HardwareAck.model_validate(payload)
        if ack.device_id != device_id:
            return
        async with self.session_factory() as db:
            command = await db.scalar(
                select(Command).where(Command.correlation_id == ack.command_id)
            )
            if command is None or command.device_id != device_id:
                return
            command.acknowledged_at = datetime.now(UTC)
            if ack.status != "APPLIED":
                command.status = "rejected" if ack.status == "REJECTED_LOCAL_FAULT" else "failed"
                command.error = ack.error_code or ack.status
            elif state_contains(ack.current_state, command.expected_state):
                command.status = "completed"
                command.completed_at = datetime.now(UTC)
            else:
                command.status = "state_mismatch"
                command.error = "Acknowledged physical state does not match requested state"
            device = await db.get(Device, device_id)
            if device and device.house_id == house_id:
                device.state = ack.current_state
                device.availability = "online"
                device.last_seen_at = datetime.now(UTC)
                db.add(
                    DeviceState(
                        device_id=device_id,
                        state=ack.current_state,
                        source="hardware_ack",
                        correlation_id=ack.command_id,
                    )
                )
                await event_service.append(
                    db,
                    house_id=house_id,
                    source=f"device:{device_id}",
                    event_type="device.command.acknowledged",
                    message=f"Hardware returned {ack.status} for {command.action}",
                    data={"state": ack.current_state, "execution_ms": ack.execution_duration_ms},
                    correlation_id=ack.command_id,
                )
            await db.commit()
        if command.status in {"completed", "failed", "rejected"}:
            task = self._timeouts.pop(ack.command_id, None)
            if task:
                task.cancel()
        await realtime_manager.broadcast(
            house_id,
            {
                "channel": f"twin:devices:{device_id}",
                "event": "STATE_DELTA",
                "timestamp": int(datetime.now(UTC).timestamp() * 1000),
                "payload": {"device_id": device_id, "new_state": ack.current_state},
            },
        )

    async def _record_state(
        self,
        house_id: str,
        device_id: str,
        state: dict[str, Any],
        correlation_id: str | None,
        source: str,
    ) -> None:
        async with self.session_factory() as db:
            device = await db.get(Device, device_id)
            if device is None or device.house_id != house_id:
                return
            previous = dict(device.state)
            device.state = state
            device.availability = "online"
            device.last_seen_at = datetime.now(UTC)
            db.add(
                DeviceState(
                    device_id=device_id, state=state, source=source, correlation_id=correlation_id
                )
            )
            await event_service.append(
                db,
                house_id=house_id,
                source=f"device:{device_id}",
                event_type="device.state.changed",
                message=f"{device.name} reported physical state",
                data={"previous_state": previous, "new_state": state},
                correlation_id=correlation_id,
            )
            await db.commit()

    async def ingest_heartbeat(self, house_id: str, payload: dict[str, Any]) -> None:
        heartbeat = HeartbeatPayload.model_validate(payload)
        async with self.session_factory() as db:
            device = await db.get(Device, heartbeat.device_id)
            if device is None or device.house_id != house_id:
                return
            online = heartbeat.status == "ONLINE"
            device.availability = "online" if online else "offline"
            device.last_seen_at = datetime.now(UTC)
            failures = 0 if online else 1
            wifi_penalty = max(0, (-heartbeat.rssi_dbm - 65) * 0.5) if heartbeat.rssi_dbm else 0
            score = max(0.0, 100 - wifi_penalty - failures * 20)
            device.health_score = score
            db.add(
                DeviceHealth(
                    device_id=device.id,
                    status="healthy" if score >= 80 else "degraded",
                    score=score,
                    mqtt_connected=online,
                    failure_count=failures,
                    details=heartbeat.model_dump(mode="json"),
                )
            )
            await db.commit()

    async def ingest_sensor(self, house_id: str, telemetry: TelemetryPayload) -> None:
        if self.event_pipeline:
            await self.event_pipeline.telemetry(telemetry.model_dump(mode="json"))
        async with self.session_factory() as db:
            sensor = await db.get(Sensor, telemetry.sensor_id)
            if sensor is None or sensor.house_id != house_id or telemetry.status != "VALID":
                return
            sensor.availability = "online"
            sensor.last_seen_at = datetime.now(UTC)
            db.add(
                SensorReading(
                    sensor_id=sensor.id,
                    value=telemetry.value,
                    quality="good",
                    recorded_at=datetime.fromtimestamp(telemetry.timestamp / 1000, UTC),
                    raw_payload=telemetry.model_dump(mode="json"),
                )
            )
            await event_service.append(
                db,
                house_id=house_id,
                source=f"sensor:{sensor.id}",
                event_type="sensor.reading",
                message=f"{sensor.name} reported {telemetry.value} {telemetry.unit}",
                data=telemetry.model_dump(mode="json"),
            )
            alert = safety_monitor.evaluate(sensor.sensor_type, telemetry.value)
            if alert:
                await event_service.append(
                    db,
                    house_id=house_id,
                    source=f"safety:{sensor.id}",
                    event_type=alert.event_type,
                    severity=alert.severity,
                    message=alert.message,
                    data={"sensor_id": sensor.id, "value": telemetry.value},
                )
                if self.emergency_service:
                    house = await db.get(House, house_id)
                    if house:
                        await self.emergency_service.trigger(
                            db,
                            house,
                            hazard_type=alert.event_type.upper().replace(".", "_"),
                            source_room=sensor.room_id,
                            source=f"safety:{sensor.id}",
                        )
            await db.commit()
        await realtime_manager.broadcast(
            house_id,
            {
                "channel": f"twin:rooms:{sensor.room_id}",
                "event": "STATE_DELTA",
                "timestamp": telemetry.timestamp,
                "payload": {"sensor_id": sensor.id, "new_val": telemetry.value},
            },
        )
        if alert:
            await realtime_manager.broadcast(
                house_id,
                {
                    "channel": "emergency:alerts",
                    "event": "EMERGENCY_CUTOFF_ACTIVE",
                    "timestamp": telemetry.timestamp,
                    "payload": {"hazard_type": alert.event_type, "location": sensor.room_id},
                },
            )
