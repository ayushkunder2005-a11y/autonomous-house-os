from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.anomaly import anomaly_detector
from app.analytics.prediction import prediction_provider
from app.models.device import Device
from app.models.operations import EnergyReading, Event, HouseMemory, WaterReading


class HouseAnalyticsService:
    async def energy_summary(
        self, db: AsyncSession, house_id: str, hours: int = 24
    ) -> dict[str, Any]:
        since = datetime.now(UTC) - timedelta(hours=hours)
        readings = list(
            (
                await db.scalars(
                    select(EnergyReading)
                    .where(EnergyReading.house_id == house_id, EnergyReading.recorded_at >= since)
                    .order_by(EnergyReading.recorded_at)
                )
            ).all()
        )
        powers = [item.power_watts for item in readings]
        energy = sum(item.energy_kwh for item in readings)
        costs = sum(item.cost or 0 for item in readings)
        anomaly = anomaly_detector.detect(powers[:-1], powers[-1]) if powers else None
        forecast = prediction_provider.forecast(powers, 6)
        by_device: dict[str, float] = {}
        for item in readings:
            key = item.device_id or "whole_house"
            by_device[key] = by_device.get(key, 0.0) + item.energy_kwh
        recommendations: list[str] = []
        if powers and max(powers) > 5000:
            recommendations.append("Stagger high-load appliances to reduce peak demand")
        return {
            "house_id": house_id,
            "period_hours": hours,
            "current_power_watts": powers[-1] if powers else 0,
            "energy_kwh": round(energy, 4),
            "estimated_cost": round(costs, 4),
            "by_device_kwh": {key: round(value, 4) for key, value in by_device.items()},
            "anomaly": anomaly.__dict__ if anomaly else None,
            "forecast_watts": forecast.__dict__,
            "recommendations": recommendations,
        }

    async def water_summary(
        self, db: AsyncSession, house_id: str, hours: int = 24
    ) -> dict[str, Any]:
        since = datetime.now(UTC) - timedelta(hours=hours)
        readings = list(
            (
                await db.scalars(
                    select(WaterReading)
                    .where(WaterReading.house_id == house_id, WaterReading.recorded_at >= since)
                    .order_by(WaterReading.recorded_at)
                )
            ).all()
        )
        volumes = [item.volume_liters for item in readings]
        flows = [item.flow_lpm for item in readings if item.flow_lpm is not None]
        anomaly = anomaly_detector.detect(flows[:-1], flows[-1]) if flows else None
        return {
            "house_id": house_id,
            "period_hours": hours,
            "volume_liters": round(sum(volumes), 3),
            "current_flow_lpm": flows[-1] if flows else 0,
            "tank_level_percent": next(
                (
                    item.tank_level_percent
                    for item in reversed(readings)
                    if item.tank_level_percent is not None
                ),
                None,
            ),
            "leak_detected": any(item.leak_detected for item in readings),
            "anomaly": anomaly.__dict__ if anomaly else None,
        }

    async def house_health(self, db: AsyncSession, house_id: str) -> dict[str, Any]:
        devices = list((await db.scalars(select(Device).where(Device.house_id == house_id))).all())
        now = datetime.now(UTC)
        stale = 0
        scores: list[float] = []
        for device in devices:
            seen = device.last_seen_at
            if seen and seen.tzinfo is None:
                seen = seen.replace(tzinfo=UTC)
            if not seen or now - seen > timedelta(minutes=5):
                stale += 1
                scores.append(min(device.health_score, 40.0))
            else:
                scores.append(device.health_score)
        device_score = sum(scores) / len(scores) if scores else 100.0
        energy_leaks = await db.scalar(
            select(func.count())
            .select_from(WaterReading)
            .where(
                WaterReading.house_id == house_id,
                WaterReading.leak_detected.is_(True),
                WaterReading.recorded_at >= now - timedelta(hours=24),
            )
        )
        water_score = 30.0 if energy_leaks else 100.0
        components = {
            "devices": {
                "score": round(device_score, 1),
                "stale_or_offline": stale,
                "total": len(devices),
            },
            "network": {
                "score": round(100 * (len(devices) - stale) / len(devices), 1) if devices else 100.0
            },
            "water": {"score": water_score, "active_leak": bool(energy_leaks)},
            "security": {"score": 100.0},
            "energy": {"score": 100.0},
            "environment": {"score": 100.0},
            "maintenance": {"score": round(device_score, 1)},
        }
        overall = sum(component["score"] for component in components.values()) / len(components)
        status = "healthy" if overall >= 80 else "degraded" if overall >= 50 else "critical"
        return {
            "house_id": house_id,
            "overall_score": round(overall, 1),
            "status": status,
            "components": components,
            "calculated_at": now,
        }

    async def search_memory(
        self, db: AsyncSession, house_id: str, query: str, limit: int
    ) -> list[dict[str, Any]]:
        tokens = [token for token in query.lower().split() if len(token) > 2][:8]
        statement = select(HouseMemory).where(HouseMemory.house_id == house_id)
        if tokens:
            statement = statement.where(
                or_(*(func.lower(HouseMemory.content).like(f"%{token}%") for token in tokens))
            )
        items = list(
            (
                await db.scalars(statement.order_by(HouseMemory.recorded_at.desc()).limit(limit))
            ).all()
        )
        return [
            {
                "id": item.id,
                "category": item.category,
                "content": item.content,
                "keywords": item.keywords,
                "recorded_at": item.recorded_at,
                "source_event_id": item.source_event_id,
            }
            for item in items
        ]

    async def recent_events(self, db: AsyncSession, house_id: str, limit: int = 100) -> list[Event]:
        return list(
            (
                await db.scalars(
                    select(Event)
                    .where(Event.house_id == house_id)
                    .order_by(Event.occurred_at.desc())
                    .limit(limit)
                )
            ).all()
        )


house_analytics = HouseAnalyticsService()
