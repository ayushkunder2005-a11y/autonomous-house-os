from dataclasses import dataclass
from typing import Any

from app.models.device import Device


@dataclass(frozen=True)
class SafetyResult:
    allowed: bool
    reason: str | None = None


class SafetyValidator:
    """Deterministic hardware safety boundary; AI output must also pass here."""

    ACTION_CAPABILITIES = {
        "turn_on": "power",
        "turn_off": "power",
        "set_brightness": "brightness",
        "set_temperature": "temperature",
        "set_speed": "speed",
        "open": "position",
        "close": "position",
        "lock": "lock",
        "unlock": "lock",
        "set_state": "state",
    }

    def validate(self, device: Device, action: str, parameters: dict[str, Any]) -> SafetyResult:
        action = action.lower()
        aliases = {
            "set_parameters": "state",
            "set_position": "position",
            "force_shutoff": "power",
            "force_off": "power",
        }
        required = self.ACTION_CAPABILITIES.get(action) or aliases.get(action)
        if action in {"set_state", "set_parameters"}:
            if "power" in parameters:
                required = "power"
            elif any(key in parameters for key in ("temperature", "setpoint_c", "temp_c")):
                required = "temperature"
        if required is None:
            return SafetyResult(False, f"Unsupported action: {action}")
        if required not in device.capabilities and action not in device.capabilities:
            return SafetyResult(False, f"Device lacks capability: {required}")
        if device.availability == "offline":
            return SafetyResult(False, "Device is offline")
        if action == "set_temperature":
            value = parameters.get("temperature")
            if not isinstance(value, (int, float)) or not 16 <= value <= 30:
                return SafetyResult(False, "Temperature must be between 16 and 30 °C")
        if action in {"set_brightness", "set_speed"}:
            key = "brightness" if action == "set_brightness" else "speed"
            value = parameters.get(key)
            if not isinstance(value, (int, float)) or not 0 <= value <= 100:
                return SafetyResult(False, f"{key} must be between 0 and 100")
        if action == "unlock" and parameters.get("confirmed") is not True:
            return SafetyResult(False, "Unlock requires explicit confirmed=true")
        if device.device_type == "pump" and action == "turn_on":
            if (
                device.state.get("dry_run_detected")
                or device.state.get("tank_level_percent", 100) < 5
            ):
                return SafetyResult(False, "Pump start blocked by dry-run protection")
        return SafetyResult(True)


safety_validator = SafetyValidator()
