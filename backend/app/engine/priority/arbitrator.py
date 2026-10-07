import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.contracts import PriorityTier, SecurityMode
from app.models.device import Device
from app.models.operations import ConflictLog


@dataclass(frozen=True)
class ArbitrationDecision:
    approved: bool
    reason: str
    effective_parameters: dict[str, Any]
    preempted_source: str | None = None


@dataclass
class ActiveAuthority:
    tier: PriorityTier
    source: str
    expires_at: datetime | None


class PriorityArbitrator:
    """Immutable rank ordering: lower tier number always has greater authority."""

    def __init__(self) -> None:
        self._authorities: dict[str, ActiveAuthority] = {}
        self._emergency_locked: set[str] = set()
        self._lock = asyncio.Lock()

    async def evaluate(
        self,
        db: AsyncSession,
        *,
        device: Device,
        endpoint: str,
        action: str,
        parameters: dict[str, Any],
        tier: PriorityTier,
        source: str,
        security_mode: SecurityMode = SecurityMode.HOME,
    ) -> ArbitrationDecision:
        now = datetime.now(UTC)
        async with self._lock:
            rejection = self._physical_constraint(device, action, parameters, security_mode)
            if rejection:
                return await self._reject(db, device.id, source, rejection, "PHYSICAL_INTERLOCK")
            if (
                device.id in self._emergency_locked
                and tier != PriorityTier.LEVEL_0_SAFETY_EMERGENCY
            ):
                return await self._reject(
                    db, device.id, source, "LEVEL_0_EMERGENCY_LOCK", "SAFETY_MATRIX"
                )
            authority = self._authorities.get(device.id)
            if authority and authority.expires_at and authority.expires_at <= now:
                authority = None
                self._authorities.pop(device.id, None)
            if authority and authority.tier < tier:
                return await self._reject(
                    db,
                    device.id,
                    source,
                    f"TIER_{authority.tier}_PREEMPTS_TIER_{tier}",
                    authority.source,
                )
            previous = authority.source if authority else None
            expiry = (
                now + timedelta(minutes=120)
                if tier == PriorityTier.LEVEL_3_MANUAL_OVERRIDE
                else None
            )
            self._authorities[device.id] = ActiveAuthority(tier, source, expiry)
            if tier == PriorityTier.LEVEL_0_SAFETY_EMERGENCY:
                self._emergency_locked.add(device.id)
            return ArbitrationDecision(True, "APPROVED", parameters, previous)

    async def clear_emergency(self) -> None:
        async with self._lock:
            self._emergency_locked.clear()
            for device_id, authority in list(self._authorities.items()):
                if authority.tier == PriorityTier.LEVEL_0_SAFETY_EMERGENCY:
                    self._authorities.pop(device_id, None)

    async def activate_emergency(self, device_ids: list[str], source: str) -> None:
        async with self._lock:
            for device_id in device_ids:
                self._emergency_locked.add(device_id)
                self._authorities[device_id] = ActiveAuthority(
                    PriorityTier.LEVEL_0_SAFETY_EMERGENCY, source, None
                )

    @staticmethod
    def _physical_constraint(
        device: Device,
        action: str,
        parameters: dict[str, Any],
        security_mode: SecurityMode,
    ) -> str | None:
        normalized = action.upper()
        if device.device_type == "pump" and normalized in {"TURN_ON", "SET_STATE"}:
            requested_on = normalized == "TURN_ON" or parameters.get("power") in {"ON", "on", True}
            if requested_on and float(device.state.get("tank_level_pct", 100)) < 10:
                return "PUMP_DRY_RUN_LOCKOUT"
        if device.device_type == "lock" and normalized in {"UNLOCK", "SET_STATE"}:
            unlocking = normalized == "UNLOCK" or parameters.get("locked") is False
            if unlocking and security_mode in {SecurityMode.AWAY, SecurityMode.VACATION}:
                return "SECURITY_MODE_LOCKOUT"
        if device.device_type in {"ac", "hvac"}:
            mode = str(parameters.get("mode", "")).upper()
            current_mode = str(device.state.get("mode", "")).upper()
            if {mode, current_mode} == {"HEAT", "COOL"}:
                changed_at = device.state.get("mode_changed_epoch")
                if changed_at and datetime.now(UTC).timestamp() - float(changed_at) < 300:
                    return "HVAC_DUAL_MODE_5_MINUTE_DEADBAND"
            if device.state.get("window_open_seconds", 0) > 180 and mode in {"HEAT", "COOL"}:
                return "THERMAL_ENVELOPE_OPEN"
        return None

    @staticmethod
    async def _reject(
        db: AsyncSession,
        device_id: str,
        source: str,
        basis: str,
        winner: str,
    ) -> ArbitrationDecision:
        db.add(
            ConflictLog(
                target_device_id=device_id,
                competing_rules=[source, winner],
                winning_source=winner,
                resolution_basis=basis,
                preempted_source=source,
            )
        )
        await db.flush()
        return ArbitrationDecision(False, basis, {}, winner)


priority_arbitrator = PriorityArbitrator()
