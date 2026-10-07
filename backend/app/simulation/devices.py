import time
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.contracts import CommandDispatch
from app.models.device import Device
from app.mqtt.bus import MessageBus
from app.mqtt.topics import ack_topic, emergency_topic, parse_topic, state_topic


class SimulatedDeviceManager:
    """High-fidelity contract emulator for devices marked with the simulated driver."""

    def __init__(self, bus: MessageBus, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.bus = bus
        self.session_factory = session_factory

    async def start(self) -> None:
        await self.bus.subscribe("house/+/command/+/+", self._handle_command, qos=2)
        await self.bus.subscribe("house/+/emergency/broadcast", self._handle_emergency, qos=2)

    async def _handle_command(self, topic: str, payload: dict[str, Any]) -> None:
        parsed = parse_topic(topic)
        if parsed is None or parsed.kind != "command" or not parsed.device_id:
            return
        try:
            command = CommandDispatch.model_validate(payload)
        except ValidationError:
            return
        started = time.perf_counter()
        async with self.session_factory() as db:
            device = await db.get(Device, parsed.device_id)
            if device is None or device.driver != "simulated" or device.house_id != parsed.house_id:
                return
            next_state = self._transition(device.state, command.action, command.parameters)
        ack = {
            "command_id": command.command_id,
            "device_id": command.device_id,
            "endpoint": command.endpoint,
            "status": "APPLIED",
            "execution_duration_ms": round((time.perf_counter() - started) * 1000, 3),
            "current_state": next_state,
            "error_code": None,
        }
        await self.bus.publish(
            ack_topic(parsed.house_id, parsed.device_id, command.command_id), ack, qos=2
        )
        await self.bus.publish(
            state_topic(parsed.house_id, parsed.device_id, command.endpoint),
            {
                "device_id": parsed.device_id,
                "endpoint": command.endpoint,
                "timestamp": int(time.time() * 1000),
                "state": next_state,
            },
            qos=1,
        )

    async def _handle_emergency(self, topic: str, payload: dict[str, Any]) -> None:
        parsed = parse_topic(topic)
        if parsed is None or topic != emergency_topic(parsed.house_id):
            return
        async with self.session_factory() as db:
            devices = list(
                (
                    await db.scalars(
                        select(Device).where(
                            Device.house_id == parsed.house_id, Device.driver == "simulated"
                        )
                    )
                ).all()
            )
            for device in devices:
                if device.device_type in {"pump", "ac", "hvac", "smart_plug"}:
                    device.state = {**device.state, "power": "off", "emergency_lock": True}
            await db.commit()

    @staticmethod
    def _transition(
        state: dict[str, Any], action: str, parameters: dict[str, Any]
    ) -> dict[str, Any]:
        result = dict(state)
        normalized = action.lower()
        if normalized == "turn_on":
            result["power"] = "on"
        elif normalized in {"turn_off", "force_off", "force_shutoff"}:
            result["power"] = "off"
        elif normalized == "set_brightness":
            result["brightness"] = parameters["brightness"]
        elif normalized == "set_temperature":
            result["temperature"] = parameters["temperature"]
        elif normalized == "set_speed":
            result["speed"] = parameters["speed"]
        elif normalized == "open":
            result["position"] = "open"
        elif normalized == "close":
            result["position"] = "closed"
        elif normalized == "lock":
            result["locked"] = True
        elif normalized == "unlock":
            result["locked"] = False
        elif normalized in {"set_state", "set_parameters", "set_position"}:
            result.update(parameters.get("state", parameters))
        return result
