import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.automation.engine import AutomationEngine
from app.models.device import Device
from app.schemas.domain import SimulationRequest

DEFAULT_POWER_WATTS = {
    "light": 10.0,
    "fan": 70.0,
    "ac": 1500.0,
    "smart_plug": 100.0,
    "pump": 750.0,
    "entertainment": 150.0,
}


class SimulationService:
    async def simulate(self, db: AsyncSession, request: SimulationRequest) -> dict[str, Any]:
        devices = list(
            (await db.scalars(select(Device).where(Device.house_id == request.house_id))).all()
        )
        by_id = {device.id: device for device in devices}
        actions = list(request.actions)
        if request.text:
            actions.extend(self._parse_hypothesis(request.text, devices))
        AutomationEngine._validate_action_conflicts(actions)

        affected_rooms: set[str] = set()
        conflicts: list[str] = []
        warnings: list[str] = []
        incremental_watts = 0.0
        for action in actions:
            device = by_id.get(str(action.get("device_id")))
            if device is None:
                conflicts.append(f"Unknown device: {action.get('device_id')}")
                continue
            if device.room_id:
                affected_rooms.add(device.room_id)
            rated = float(
                device.metadata_json.get(
                    "rated_power_watts", DEFAULT_POWER_WATTS.get(device.device_type, 0)
                )
            )
            operation = action.get("action")
            if operation == "turn_on" and device.state.get("power") != "on":
                incremental_watts += rated
            elif operation == "turn_off" and device.state.get("power") == "on":
                incremental_watts -= rated
            elif operation == "set_temperature" and device.device_type == "ac":
                current = float(device.state.get("temperature", 24))
                target = float(action.get("parameters", {}).get("temperature", current))
                incremental_watts += max(0, current - target) * rated * 0.05
                if target < 20:
                    warnings.append(f"{device.name}: low set point may increase consumption")
        energy_kwh = incremental_watts * request.duration_hours / 1000
        return {
            "simulation_only": True,
            "actions": actions,
            "affected_rooms": sorted(affected_rooms),
            "device_load_change_watts": round(incremental_watts, 2),
            "energy_impact_kwh": round(energy_kwh, 4),
            "estimated_cost_change": round(energy_kwh * request.tariff_per_kwh, 4),
            "conflicts": conflicts,
            "warnings": warnings,
            "assumptions": [
                "Rated power metadata or conservative device-type defaults",
                "Constant load over requested duration",
            ],
        }

    @staticmethod
    def _parse_hypothesis(text: str, devices: list[Device]) -> list[dict[str, Any]]:
        normalized = text.lower()
        match = re.search(r"(?:all\s+)?(?:ac|air conditioner)s?.*?(\d{2})\s*°?c", normalized)
        if match:
            value = int(match.group(1))
            if not 16 <= value <= 30:
                return []
            return [
                {
                    "device_id": device.id,
                    "action": "set_temperature",
                    "parameters": {"temperature": value},
                }
                for device in devices
                if device.device_type == "ac"
            ]
        return []


simulation_service = SimulationService()
