import asyncio
import json
import ssl
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

import aiomqtt
import structlog

from app.core.config import Settings
from app.mqtt.topics import topic_matches

MessageHandler = Callable[[str, dict[str, Any]], Awaitable[None]]
logger = structlog.get_logger()


class MessageBus(Protocol):
    connected: bool

    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def publish(self, topic: str, payload: dict[str, Any], qos: int = 1) -> bool: ...
    async def subscribe(self, pattern: str, handler: MessageHandler, qos: int = 1) -> None: ...


class InMemoryBus:
    """MQTT-compatible process-local transport used by simulation and tests."""

    def __init__(self) -> None:
        self.connected = False
        self._handlers: dict[str, list[MessageHandler]] = defaultdict(list)

    async def start(self) -> None:
        self.connected = True

    async def stop(self) -> None:
        self.connected = False

    async def subscribe(self, pattern: str, handler: MessageHandler, qos: int = 1) -> None:
        self._handlers[pattern].append(handler)

    async def publish(self, topic: str, payload: dict[str, Any], qos: int = 1) -> bool:
        if not self.connected:
            return False
        for pattern, handlers in list(self._handlers.items()):
            if topic_matches(pattern, topic):
                for handler in list(handlers):
                    await handler(topic, payload)
        return True


class MQTTBus:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.connected = False
        self._handlers: dict[str, list[MessageHandler]] = defaultdict(list)
        self._subscription_qos: dict[str, int] = {}
        self._client: aiomqtt.Client | None = None
        self._runner: asyncio.Task[None] | None = None
        self._stopping = False

    async def start(self) -> None:
        self._stopping = False
        self._runner = asyncio.create_task(self._connection_loop())

    async def stop(self) -> None:
        self._stopping = True
        if self._runner:
            self._runner.cancel()
            try:
                await self._runner
            except asyncio.CancelledError:
                pass
        self.connected = False

    async def subscribe(self, pattern: str, handler: MessageHandler, qos: int = 1) -> None:
        self._handlers[pattern].append(handler)
        self._subscription_qos[pattern] = max(qos, self._subscription_qos.get(pattern, 0))
        if self.connected and self._client:
            await self._client.subscribe(pattern, qos=qos)

    async def publish(self, topic: str, payload: dict[str, Any], qos: int = 1) -> bool:
        if not self.connected or self._client is None:
            return False
        try:
            await self._client.publish(topic, json.dumps(payload), qos=qos, retain=False)
            return True
        except aiomqtt.MqttError:
            self.connected = False
            return False

    async def _connection_loop(self) -> None:
        attempt = 0
        while not self._stopping:
            tls_context = ssl.create_default_context() if self.settings.mqtt_tls else None
            try:
                async with aiomqtt.Client(
                    hostname=self.settings.mqtt_host,
                    port=self.settings.mqtt_port,
                    username=self.settings.mqtt_username,
                    password=self.settings.mqtt_password,
                    identifier=self.settings.mqtt_client_id,
                    keepalive=self.settings.mqtt_keepalive,
                    tls_context=tls_context,
                ) as client:
                    self._client = client
                    for pattern in self._handlers:
                        await client.subscribe(pattern, qos=self._subscription_qos[pattern])
                    self.connected = True
                    attempt = 0
                    logger.info("mqtt_connection", connected=True)
                    async for message in client.messages:
                        await self._dispatch(str(message.topic), bytes(message.payload))
            except asyncio.CancelledError:
                return
            except aiomqtt.MqttError as exc:
                self.connected = False
                self._client = None
                delay = min(60.0, 2**attempt) + (0.2 * (attempt % 3))
                attempt = min(attempt + 1, 6)
                logger.warning("mqtt_disconnected", error=str(exc), retry_seconds=delay)
                await asyncio.sleep(delay)

    async def _dispatch(self, topic: str, raw_payload: bytes) -> None:
        try:
            payload = json.loads(raw_payload.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("MQTT payload must be an object")
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            logger.warning("mqtt_invalid_payload", topic=topic)
            return
        for pattern, handlers in list(self._handlers.items()):
            if topic_matches(pattern, topic):
                for handler in list(handlers):
                    await handler(topic, payload)
