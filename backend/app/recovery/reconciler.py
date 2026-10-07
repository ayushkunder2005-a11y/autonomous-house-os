import asyncio
import time

from app.mqtt.bus import MessageBus
from app.transport.redis_bus import RedisEventPipeline


class RecoveryReconciler:
    def __init__(self, bus: MessageBus, events: RedisEventPipeline) -> None:
        self.bus = bus
        self.events = events
        self._worker: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._worker = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._worker:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        while True:
            try:
                await asyncio.sleep(1)
                if not self.bus.connected or not self.events.available:
                    continue
                for _ in range(100):
                    item = await self.events.pop_command()
                    if not item:
                        break
                    if time.time() - float(item["enqueued_epoch"]) >= int(item["ttl_seconds"]):
                        continue
                    command = item["command"]
                    await self.bus.publish(
                        command["topic"], command["payload"], qos=int(command.get("qos", 2))
                    )
            except asyncio.CancelledError:
                return
