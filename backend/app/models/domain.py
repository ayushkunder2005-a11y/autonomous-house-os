from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Column, ForeignKey, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.device import Device, Sensor
    from app.models.operations import Automation, Scene


role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)


class House(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "houses"

    name: Mapped[str] = mapped_column(String(120))
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    security_mode: Mapped[str] = mapped_column(String(20), default="HOME")
    latitude: Mapped[float] = mapped_column(default=0.0)
    longitude: Mapped[float] = mapped_column(default=0.0)

    floors: Mapped[list[Floor]] = relationship(back_populates="house", cascade="all, delete-orphan")
    users: Mapped[list[User]] = relationship(back_populates="house")
    devices: Mapped[list[Device]] = relationship(back_populates="house")
    sensors: Mapped[list[Sensor]] = relationship(back_populates="house")
    automations: Mapped[list[Automation]] = relationship(back_populates="house")
    scenes: Mapped[list[Scene]] = relationship(back_populates="house")


class Floor(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "floors"

    house_id: Mapped[str] = mapped_column(ForeignKey("houses.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    level: Mapped[int] = mapped_column(default=0)

    house: Mapped[House] = relationship(back_populates="floors")
    rooms: Mapped[list[Room]] = relationship(back_populates="floor", cascade="all, delete-orphan")


class Room(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "rooms"

    floor_id: Mapped[str] = mapped_column(ForeignKey("floors.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    room_type: Mapped[str] = mapped_column(String(50), default="general")

    floor: Mapped[Floor] = relationship(back_populates="rooms")
    devices: Mapped[list[Device]] = relationship(back_populates="room")
    sensors: Mapped[list[Sensor]] = relationship(back_populates="room")


class Permission(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    description: Mapped[str] = mapped_column(String(255), default="")

    roles: Mapped[list[Role]] = relationship(
        secondary=role_permissions, back_populates="permissions"
    )


class Role(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    description: Mapped[str] = mapped_column(String(255), default="")

    permissions: Mapped[list[Permission]] = relationship(
        secondary=role_permissions, back_populates="roles", lazy="selectin"
    )
    users: Mapped[list[User]] = relationship(back_populates="role")


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    pin_code_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    house_id: Mapped[str | None] = mapped_column(
        ForeignKey("houses.id", ondelete="SET NULL"), nullable=True, index=True
    )
    role_id: Mapped[str] = mapped_column(ForeignKey("roles.id", ondelete="RESTRICT"), index=True)

    house: Mapped[House | None] = relationship(back_populates="users")
    role: Mapped[Role] = relationship(back_populates="users", lazy="selectin")
