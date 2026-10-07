from dataclasses import dataclass


@dataclass(frozen=True)
class SafetyAlert:
    event_type: str
    message: str
    severity: str = "critical"


class SafetyMonitor:
    """Pure, deterministic sensor checks that remain available without any AI service."""

    def evaluate(self, sensor_type: str, value: float) -> SafetyAlert | None:
        normalized = sensor_type.lower()
        if normalized in {"smoke", "water_leak"} and value >= 1:
            return SafetyAlert(
                event_type=f"emergency.{normalized}",
                message=f"{normalized.replace('_', ' ').title()} detected",
            )
        if normalized == "gas" and value >= 1500:
            return SafetyAlert("emergency.gas", f"Emergency gas concentration: {value:.0f} PPM")
        if normalized in {"temperature", "equipment_temperature"} and value >= 65:
            return SafetyAlert("emergency.overheating", f"Overheating detected at {value:.1f} °C")
        if normalized in {"power", "power_w", "power_watts"} and value >= 10_000:
            return SafetyAlert("emergency.electrical", f"Abnormal electrical load: {value:.0f} W")
        return None


safety_monitor = SafetyMonitor()
