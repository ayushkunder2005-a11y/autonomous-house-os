import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.operations import Event, HouseMemory


def canonical_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


class EventService:
    async def append(
        self,
        db: AsyncSession,
        *,
        source: str,
        event_type: str,
        message: str,
        house_id: str | None = None,
        severity: str = "info",
        data: dict[str, Any] | None = None,
        correlation_id: str | None = None,
        remember: bool = True,
    ) -> Event:
        previous = await db.scalar(select(Event).order_by(Event.occurred_at.desc()).limit(1))
        occurred_at = datetime.now(UTC)
        event_data = data or {}
        canonical = json.dumps(
            {
                "house_id": house_id,
                "source": source,
                "event_type": event_type,
                "severity": severity,
                "message": message,
                "data": event_data,
                "correlation_id": correlation_id,
                "occurred_at": canonical_timestamp(occurred_at),
                "previous_hash": previous.integrity_hash if previous else None,
            },
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        event = Event(
            house_id=house_id,
            source=source,
            event_type=event_type,
            severity=severity,
            message=message,
            data=event_data,
            correlation_id=correlation_id,
            occurred_at=occurred_at,
            previous_hash=previous.integrity_hash if previous else None,
            integrity_hash=hashlib.sha256(canonical.encode()).hexdigest(),
        )
        db.add(event)
        await db.flush()
        if remember and house_id:
            db.add(
                HouseMemory(
                    house_id=house_id,
                    category=event_type.split(".", 1)[0],
                    content=message,
                    keywords=list({source, event_type, severity}),
                    source_event_id=event.id,
                    recorded_at=occurred_at,
                )
            )
        return event

    async def verify_chain(self, db: AsyncSession) -> tuple[bool, str | None]:
        events = list((await db.scalars(select(Event).order_by(Event.occurred_at))).all())
        expected_previous: str | None = None
        for event in events:
            canonical = json.dumps(
                {
                    "house_id": event.house_id,
                    "source": event.source,
                    "event_type": event.event_type,
                    "severity": event.severity,
                    "message": event.message,
                    "data": event.data,
                    "correlation_id": event.correlation_id,
                    "occurred_at": canonical_timestamp(event.occurred_at),
                    "previous_hash": event.previous_hash,
                },
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            )
            digest = hashlib.sha256(canonical.encode()).hexdigest()
            if event.previous_hash != expected_previous or event.integrity_hash != digest:
                return False, event.id
            expected_previous = event.integrity_hash
        return True, None


event_service = EventService()
