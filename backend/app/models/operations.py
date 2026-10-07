from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utcnow

if TYPE_CHECKING:
    from app.models.domain import House


class Automation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "automations"

    house_id: Mapped[str] = mapped_column(ForeignKey("houses.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    trigger_type: Mapped[str] = mapped_column(String(30))
    trigger_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    conditions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    actions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    failure_policy: Mapped[str] = mapped_column(String(30), default="stop")
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    house: Mapped[House] = relationship(back_populates="automations")


class Scene(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "scenes"

    house_id: Mapped[str] = mapped_column(ForeignKey("houses.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    mode: Mapped[str | None] = mapped_column(String(50), nullable=True)
    actions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    house: Mapped[House] = relationship(back_populates="scenes")


class Event(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_house_occurred", "house_id", "occurred_at"),
        Index("ix_events_type_occurred", "event_type", "occurred_at"),
    )

    house_id: Mapped[str | None] = mapped_column(
        ForeignKey("houses.id", ondelete="SET NULL"), nullable=True
    )
    source: Mapped[str] = mapped_column(String(100), index=True)
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    severity: Mapped[str] = mapped_column(String(20), default="info")
    message: Mapped[str] = mapped_column(Text)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    correlation_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    previous_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    integrity_hash: Mapped[str] = mapped_column(String(64), unique=True)


class SecurityEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "security_events"

    house_id: Mapped[str | None] = mapped_column(
        ForeignKey("houses.id", ondelete="SET NULL"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    severity: Mapped[str] = mapped_column(String(20))
    actor: Mapped[str | None] = mapped_column(String(320), nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EnergyReading(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "energy_readings"
    __table_args__ = (Index("ix_energy_house_recorded", "house_id", "recorded_at"),)

    house_id: Mapped[str] = mapped_column(ForeignKey("houses.id", ondelete="CASCADE"))
    device_id: Mapped[str | None] = mapped_column(
        ForeignKey("devices.id", ondelete="SET NULL"), nullable=True
    )
    power_watts: Mapped[float] = mapped_column(Float)
    energy_kwh: Mapped[float] = mapped_column(Float, default=0.0)
    voltage: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_amps: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WaterReading(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "water_readings"
    __table_args__ = (Index("ix_water_house_recorded", "house_id", "recorded_at"),)

    house_id: Mapped[str] = mapped_column(ForeignKey("houses.id", ondelete="CASCADE"))
    sensor_id: Mapped[str | None] = mapped_column(
        ForeignKey("sensors.id", ondelete="SET NULL"), nullable=True
    )
    flow_lpm: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume_liters: Mapped[float] = mapped_column(Float, default=0.0)
    tank_level_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    pressure_kpa: Mapped[float | None] = mapped_column(Float, nullable=True)
    leak_detected: Mapped[bool] = mapped_column(Boolean, default=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MaintenanceRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "maintenance_records"

    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="recommended")
    maintenance_type: Mapped[str] = mapped_column(String(80))
    notes: Mapped[str] = mapped_column(Text, default="")
    operating_hours: Mapped[float] = mapped_column(Float, default=0.0)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    health_score: Mapped[float] = mapped_column(Float, default=100.0)
    recommended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AIDecision(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "ai_decisions"

    house_id: Mapped[str] = mapped_column(ForeignKey("houses.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(80))
    model: Mapped[str] = mapped_column(String(120))
    input_summary: Mapped[str] = mapped_column(Text)
    structured_intent: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    validation_status: Mapped[str] = mapped_column(String(30))
    executed: Mapped[bool] = mapped_column(Boolean, default=False)
    rationale: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class HouseMemory(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "house_memory"
    __table_args__ = (Index("ix_house_memory_house_recorded", "house_id", "recorded_at"),)

    house_id: Mapped[str] = mapped_column(ForeignKey("houses.id", ondelete="CASCADE"))
    category: Mapped[str] = mapped_column(String(50), index=True)
    content: Mapped[str] = mapped_column(Text)
    keywords: Mapped[list[str]] = mapped_column(JSON, default=list)
    source_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("events.id", ondelete="SET NULL"), nullable=True
    )
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Experiment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "experiments"

    house_id: Mapped[str] = mapped_column(ForeignKey("houses.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    hypothesis: Mapped[str] = mapped_column(Text)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    results: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="draft")
    started_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    ended_on: Mapped[date | None] = mapped_column(Date, nullable=True)


class AuditLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_actor_created", "actor_id", "created_at"),)

    actor_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(100), index=True)
    resource_type: Mapped[str] = mapped_column(String(80))
    resource_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ConflictLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "conflict_logs"

    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    target_device_id: Mapped[str] = mapped_column(String(64), index=True)
    competing_rules: Mapped[list[str]] = mapped_column(JSON)
    winning_source: Mapped[str] = mapped_column(String(100))
    resolution_basis: Mapped[str] = mapped_column(String(100))
    preempted_source: Mapped[str] = mapped_column(String(100))
