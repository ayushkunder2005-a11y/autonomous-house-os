from dataclasses import dataclass
from statistics import median


@dataclass(frozen=True)
class AnomalyResult:
    anomalous: bool
    score: float
    reason: str | None


class RobustAnomalyDetector:
    """Median absolute deviation detector resistant to a few extreme readings."""

    def detect(self, history: list[float], current: float, threshold: float = 3.5) -> AnomalyResult:
        if len(history) < 5:
            return AnomalyResult(False, 0.0, "insufficient_history")
        center = median(history)
        mad = median([abs(value - center) for value in history])
        if mad == 0:
            anomalous = current != center
            return AnomalyResult(
                anomalous,
                float("inf") if anomalous else 0.0,
                "constant_baseline" if anomalous else None,
            )
        score = 0.6745 * abs(current - center) / mad
        return AnomalyResult(
            score > threshold,
            round(score, 3),
            "deviation_from_baseline" if score > threshold else None,
        )


anomaly_detector = RobustAnomalyDetector()
