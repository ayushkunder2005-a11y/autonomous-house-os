import re
from dataclasses import dataclass

TOPIC_PATTERNS = [
    re.compile(
        r"^house/(?P<house_id>[^/]+)/telemetry/(?P<floor>[^/]+)/(?P<room>[^/]+)/"
        r"(?P<device_id>[^/]+)/(?P<sensor_id>[^/]+)$"
    ),
    re.compile(
        r"^house/(?P<house_id>[^/]+)/(?P<kind>command|state)/(?P<device_id>[^/]+)/"
        r"(?P<endpoint>[^/]+)$"
    ),
    re.compile(r"^house/(?P<house_id>[^/]+)/ack/(?P<device_id>[^/]+)/(?P<command_id>[^/]+)$"),
    re.compile(r"^house/(?P<house_id>[^/]+)/heartbeat/(?P<device_id>[^/]+)$"),
    re.compile(r"^house/(?P<house_id>[^/]+)/emergency/(?P<kind>broadcast)$"),
]


@dataclass(frozen=True)
class ParsedTopic:
    house_id: str
    kind: str
    device_id: str | None = None
    sensor_id: str | None = None
    endpoint: str | None = None
    command_id: str | None = None
    floor: str | None = None
    room: str | None = None


def parse_topic(topic: str) -> ParsedTopic | None:
    for pattern in TOPIC_PATTERNS:
        match = pattern.match(topic)
        if not match:
            continue
        values = match.groupdict()
        kind = values.get("kind") or ("telemetry" if values.get("sensor_id") else "ack")
        if "/ack/" in topic:
            kind = "ack"
        elif "/heartbeat/" in topic:
            kind = "heartbeat"
        return ParsedTopic(
            house_id=values["house_id"],
            kind=kind,
            device_id=values.get("device_id"),
            sensor_id=values.get("sensor_id"),
            endpoint=values.get("endpoint"),
            command_id=values.get("command_id"),
            floor=values.get("floor"),
            room=values.get("room"),
        )
    return None


def command_topic(house_id: str, device_id: str, endpoint: str) -> str:
    return f"house/{house_id}/command/{device_id}/{endpoint}"


def state_topic(house_id: str, device_id: str, endpoint: str) -> str:
    return f"house/{house_id}/state/{device_id}/{endpoint}"


def ack_topic(house_id: str, device_id: str, command_id: str) -> str:
    return f"house/{house_id}/ack/{device_id}/{command_id}"


def heartbeat_topic(house_id: str, device_id: str) -> str:
    return f"house/{house_id}/heartbeat/{device_id}"


def telemetry_topic(house_id: str, floor: str, room: str, device_id: str, sensor_id: str) -> str:
    return f"house/{house_id}/telemetry/{floor}/{room}/{device_id}/{sensor_id}"


def emergency_topic(house_id: str) -> str:
    return f"house/{house_id}/emergency/broadcast"


def topic_matches(pattern: str, topic: str) -> bool:
    expected_parts = pattern.split("/")
    actual_parts = topic.split("/")
    if len(expected_parts) != len(actual_parts):
        return False
    return all(
        expected in {"+", actual}
        for expected, actual in zip(expected_parts, actual_parts, strict=True)
    )
