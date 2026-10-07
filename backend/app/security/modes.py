from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contracts import SecurityMode
from app.engine.priority.arbitrator import priority_arbitrator
from app.events.service import event_service
from app.models.device import Device
from app.models.domain import House, User
from app.mqtt.bus import MessageBus
from app.mqtt.topics import emergency_topic
from app.security.auth import verify_password


class SecurityModeService:
    async def set_mode(
        self,
        db: AsyncSession,
        house: House,
        user: User,
        mode: SecurityMode,
        pin: str | None,
    ) -> None:
        if mode in {SecurityMode.AWAY, SecurityMode.VACATION, SecurityMode.EMERGENCY}:
            self.verify_pin(user, pin)
        previous = house.security_mode
        house.security_mode = mode.value
        await event_service.append(
            db,
            house_id=house.id,
            source=f"user:{user.id}",
            event_type="security.mode.changed",
            message=f"Security mode changed from {previous} to {mode.value}",
            data={"previous": previous, "new": mode.value},
        )
        await db.commit()

    @staticmethod
    def verify_pin(user: User, pin: str | None) -> None:
        if not pin or not user.pin_code_hash or not verify_password(pin, user.pin_code_hash):
            raise HTTPException(status_code=403, detail="Valid house security PIN required")


class EmergencyService:
    def __init__(self, bus: MessageBus) -> None:
        self.bus = bus

    async def trigger(
        self,
        db: AsyncSession,
        house: House,
        *,
        hazard_type: str,
        source_room: str | None,
        source: str,
    ) -> dict[str, Any]:
        emergency_id = f"emg_{uuid4()}"
        actions = self._actions(hazard_type)
        payload = {
            "emergency_id": emergency_id,
            "timestamp": int(datetime.now(UTC).timestamp() * 1000),
            "severity": "CRITICAL_LEVEL_0",
            "hazard_type": hazard_type,
            "source_room": source_room,
            "actions_required": actions,
        }
        # Fast path: hardware cutoff broadcast precedes persistence and notifications.
        published = await self.bus.publish(emergency_topic(house.id), payload, qos=2)
        devices = list((await db.scalars(select(Device).where(Device.house_id == house.id))).all())
        await priority_arbitrator.activate_emergency(
            [device.id for device in devices], "SAFETY_MATRIX"
        )
        house.security_mode = SecurityMode.EMERGENCY.value
        await event_service.append(
            db,
            house_id=house.id,
            source=source,
            event_type="emergency.triggered",
            severity="critical",
            message=f"Level 0 emergency triggered: {hazard_type}",
            data=payload,
            correlation_id=emergency_id.removeprefix("emg_")[:36],
        )
        await db.commit()
        return {**payload, "published": published}

    async def reset(self, db: AsyncSession, house: House, user: User, pin: str | None) -> None:
        SecurityModeService.verify_pin(user, pin)
        if user.role.name not in {"admin", "owner"}:
            raise HTTPException(status_code=403, detail="Administrative role required")
        await priority_arbitrator.clear_emergency()
        house.security_mode = SecurityMode.HOME.value
        await event_service.append(
            db,
            house_id=house.id,
            source=f"user:{user.id}",
            event_type="emergency.reset",
            message="Emergency lock reset after physical inspection",
            severity="warning",
        )
        await db.commit()

    @staticmethod
    def _actions(hazard_type: str) -> list[dict[str, str]]:
        hazard = hazard_type.upper()
        if "GAS" in hazard:
            return [
                {"target_device_type": "gas_solenoid", "command": "FORCE_SHUTOFF"},
                {"target_device_type": "exhaust_fan", "command": "FORCE_MAX_EXHAUST"},
                {"target_device_type": "all_relays", "command": "PREVENT_SPARKING_SWITCH"},
            ]
        if "WATER" in hazard or "FLOOD" in hazard:
            return [
                {"target_device_type": "water_main_valve", "command": "CLOSE"},
                {"target_device_type": "pump", "command": "FORCE_OFF"},
            ]
        if "FIRE" in hazard or "SMOKE" in hazard:
            return [
                {"target_device_type": "hvac", "command": "FORCE_OFF"},
                {"target_device_type": "egress_lighting", "command": "FORCE_ON"},
                {"target_device_type": "exterior_lock", "command": "UNLOCK_EGRESS"},
            ]
        return [{"target_device_type": "nonessential_load", "command": "FORCE_OFF"}]


security_mode_service = SecurityModeService()
