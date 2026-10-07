import json
import time
from typing import Any

import redis.asyncio as redis
import structlog

logger = structlog.get_logger()


class RedisEventPipeline:
    def __init__(self, url: str | None) -> None:
        self.url = url
        self.client: redis.Redis | None = None
        self.available = False

    async def start(self) -> None:
        if not self.url:
            return
        try:
            self.client = redis.from_url(self.url, decode_responses=True)
            await self.client.ping()
            self.available = True
        except redis.RedisError as exc:
            logger.warning("redis_unavailable", error=str(exc))
            self.available = False

    async def stop(self) -> None:
        if self.client:
            await self.client.aclose()
        self.available = False

    async def telemetry(self, payload: dict[str, Any]) -> None:
        if not self.available or not self.client:
            return
        try:
            await self.client.xadd(
                "stream:telemetry",
                {"payload": json.dumps(payload, separators=(",", ":"))},
                maxlen=100_000,
                approximate=True,
            )
        except redis.RedisError:
            self.available = False

    async def queue_command(self, payload: dict[str, Any], ttl_seconds: int = 60) -> None:
        if not self.available or not self.client:
            return
        item = json.dumps(
            {"enqueued_epoch": time.time(), "ttl_seconds": ttl_seconds, "command": payload},
            separators=(",", ":"),
        )
        try:
            transaction = self.client.pipeline()
            transaction.rpush("queue:mqtt:pending_commands", item)
            transaction.ltrim("queue:mqtt:pending_commands", -5000, -1)
            await transaction.execute()
        except redis.RedisError:
            self.available = False

    async def pop_command(self) -> dict[str, Any] | None:
        if not self.available or not self.client:
            return None
        try:
            value = await self.client.lpop("queue:mqtt:pending_commands")
            return json.loads(value) if value else None
        except (redis.RedisError, json.JSONDecodeError):
            return None
