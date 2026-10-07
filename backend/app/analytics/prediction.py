from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Forecast:
    values: list[float]
    method: str
    confidence: str


class PredictionProvider(Protocol):
    def forecast(self, values: list[float], horizon: int) -> Forecast: ...


class LinearTrendPredictor:
    def forecast(self, values: list[float], horizon: int) -> Forecast:
        if not values:
            return Forecast([0.0] * horizon, "linear_trend", "low")
        if len(values) == 1:
            return Forecast([values[0]] * horizon, "linear_trend", "low")
        window = values[-min(24, len(values)) :]
        slope = (window[-1] - window[0]) / max(1, len(window) - 1)
        predictions = [max(0.0, window[-1] + slope * step) for step in range(1, horizon + 1)]
        confidence = "medium" if len(window) >= 12 else "low"
        return Forecast([round(value, 3) for value in predictions], "linear_trend", confidence)


prediction_provider: PredictionProvider = LinearTrendPredictor()
