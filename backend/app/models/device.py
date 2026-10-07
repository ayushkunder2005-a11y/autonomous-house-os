from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utcnow

if TYPE_CHECKING:
    from app.models.domain import House, Room


class Device(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "devices"

    house_id: Mapped[str] = mapped_column(ForeignKey("houses.id", ondelete="CASCADE"), index=True)
    room_id: Mapped[str | None] = mapped_column(
        ForeignKey("rooms.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    device_type: Mapped[str] = mapped_column(String(50), index=True)
    driver: Mapped[str] = mapped_column(String(50), default="mqtt")
    external_id: Mapped[str | None] = mapped_column(String(120), nullable=True, unique=True)
    state: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    capabilities: Mapped[list[str]] = mapped_column(JSON, default=list)
    availability: Mapped[str] = mapped_column(String(30), default="unknown", index=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    health_score: Mapped[float] = mapped_column(Float, default=100.0)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)

    house: Mapped[House] = relationship(back_populates="devices")
    room: Mapped[Room | None] = relationship(back_populates="devices")
    state_history: Mapped[list[DeviceState]] = relationship(
        back_populates="device", cascade="all, delete-orphan"
    )
    health_history: Mapped[list[DeviceHealth]] = relationship(
        back_populates="device", cascade="all, delete-orphan"
    )
    commands: Mapped[list[Command]] = relationship(
        back_populates="device", cascade="all, delete-orphan"
    )


class Sensor(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sensors"

    house_id: Mapped[str] = mapped_column(ForeignKey("houses.id", ondelete="CASCADE"), index=True)
    device_id: Mapped[str | None] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), nullable=True, index=True
    )
    room_id: Mapped[str | None] = mapped_column(
        ForeignKey("rooms.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    sensor_type: Mapped[str] = mapped_column(String(50), index=True)
    unit: Mapped[str | None] = mapped_column(String(30), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(120), nullable=True, unique=True)
    availability: Mapped[str] = mapped_column(String(30), default="unknown")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)

    house: Mapped[House] = relationship(back_populates="sensors")
    room: Mapped[Room | None] = relationship(back_populates="sensors")
    readings: Mapped[list[SensorReading]] = relationship(
        back_populates="sensor", cascade="all, delete-orphan"
    )


class DeviceState(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "device_states"
    __table_args__ = (Index("ix_device_states_device_recorded", "device_id", "recorded_at"),)

    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"))
    state: Mapped[dict[str, Any]] = mapped_column(JSON)
    source: Mapped[str] = mapped_column(String(50))
    correlation_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    device: Mapped[Device] = relationship(back_populates="state_history")


class SensorReading(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "sensor_readings"
    __table_args__ = (Index("ix_sensor_readings_sensor_recorded", "sensor_id", "recorded_at"),)

    sensor_id: Mapped[str] = mapped_column(ForeignKey("sensors.id", ondelete="CASCADE"))
    value: Mapped[float] = mapped_column(Float)
    quality: Mapped[str] = mapped_column(String(30), default="good")
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    sensor: Mapped[Sensor] = relationship(back_populates="readings")


class DeviceHealth(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "device_health"
    __table_args__ = (Index("ix_device_health_device_recorded", "device_id", "recorded_at"),)

    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(30), index=True)
    score: Mapped[float] = mapped_column(Float)
    response_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    mqtt_connected: Mapped[bool | None] = mapped_column(nullable=True)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    device: Mapped[Device] = relationship(back_populates="health_history")


class Command(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "commands"
    __table_args__ = (Index("ix_commands_device_created", "device_id", "created_at"),)

    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"))
    requested_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(80))
    endpoint: Mapped[str] = mapped_column(String(80), default="default")
    priority_tier: Mapped[int] = mapped_column(Integer, default=3)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    correlation_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_state: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    device: Mapped[Device] = relationship(back_populates="commands")
